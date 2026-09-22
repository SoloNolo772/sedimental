"""
grain_clustering.py – Standalone k-means clustering analysis for sediment grain data.

Usage:
    python grain_clustering.py <csv_path> [--output-dir DIR] [--dimensions DIM ...]

This script is entirely self-contained: it imports only from the Python standard
library and from numpy, pandas, scikit-learn, and matplotlib.  It has no dependency
on or coupling to the main Sedimental application codebase.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import warnings

from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_DIMENSIONS = [
    "area",
    "perimeter",
    "circularity",
    "roundness",
    "feret_diameter",
    "major_axis",
    "minor_axis",
]

K_VALUES = [2, 3, 4, 5]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse and validate command-line arguments.

    Returns a validated Namespace.  Exits with code 2 on argument errors.
    """
    parser = argparse.ArgumentParser(
        description="K-means clustering analysis for sediment grain data."
    )

    parser.add_argument(
        "csv_path",
        help="Path to the input CSV file containing grain measurements.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Directory to write output files. Defaults to the directory of csv_path.",
    )
    parser.add_argument(
        "--dimensions",
        nargs="+",
        default=None,
        help=(
            "Subset of dimension names to use for clustering. "
            "Valid names: " + ", ".join(VALID_DIMENSIONS)
        ),
    )

    args = parser.parse_args()

    # Remember whether --output-dir was explicitly supplied before we set the default.
    user_supplied_output_dir = args.output_dir is not None

    # Resolve dimensions: default to all seven.
    if args.dimensions is None:
        args.dimensions = list(VALID_DIMENSIONS)
    else:
        # Validate each supplied dimension name.
        invalid = [d for d in args.dimensions if d not in VALID_DIMENSIONS]
        if invalid:
            parser.error(
                f"Invalid dimension name(s): {', '.join(invalid)}. "
                f"Valid names are: {', '.join(VALID_DIMENSIONS)}"
            )

        # Require at least two dimensions.
        if len(args.dimensions) < 2:
            parser.error("at least two dimensions required")

    # Resolve output directory.
    csv_path = Path(args.csv_path)
    if args.output_dir is not None:
        args.output_dir = Path(args.output_dir)
    else:
        parent = csv_path.parent
        # A bare filename has parent == Path('.') which resolves to cwd.
        if parent == Path("."):
            args.output_dir = Path.cwd()
        else:
            args.output_dir = parent

    # Validate the output directory only when explicitly supplied by the user.
    if user_supplied_output_dir:
        supplied_dir = args.output_dir
        if not supplied_dir.exists():
            print(
                f"Error: output directory does not exist: {supplied_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not os.access(supplied_dir, os.W_OK):
            print(
                f"Error: output directory is not writable: {supplied_dir}",
                file=sys.stderr,
            )
            sys.exit(1)

    return args


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_and_load(csv_path: str, dimensions: list[str]) -> pd.DataFrame:
    """Load the CSV and run all validation checks.

    Validation order (per spec):
      1. Column presence check
      2. Minimum row count check (on raw data, before NaN removal)
      3. NaN row removal (with optional >20 % warning)
      4. Post-NaN minimum row count check
      5. Non-finite / non-numeric check

    Returns the cleaned DataFrame (NaN rows removed, original index preserved).
    Exits with code 1 on fatal errors, printing to stderr.
    """
    # --- Step 0: File existence and readability ---
    try:
        df_raw = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(
            f"Error: input file not found: {csv_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    except PermissionError:
        print(
            f"Error: permission denied reading file: {csv_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    except pd.errors.EmptyDataError:
        print(
            f"Error: input file is empty or contains no parseable columns: {csv_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Step 1: Column presence check ---
    missing_cols = [col for col in dimensions if col not in df_raw.columns]
    if missing_cols:
        print(
            f"Error: missing dimension column(s): {', '.join(missing_cols)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Step 2: Minimum row count check (on raw data, before NaN removal) ---
    MIN_ROWS = 10
    raw_row_count = len(df_raw)
    if raw_row_count < MIN_ROWS:
        print(
            f"Error: input file has {raw_row_count} row(s) but at least {MIN_ROWS} are required.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Step 3: NaN row removal with optional >20% warning ---
    # Only consider NaN in the selected dimension columns.
    df_clean = df_raw.dropna(subset=dimensions)
    dropped_count = raw_row_count - len(df_clean)
    if dropped_count > 0:
        fraction = dropped_count / raw_row_count
        if fraction > 0.20:
            percentage = fraction * 100.0
            print(
                f"Warning: {dropped_count} row(s) ({percentage:.1f}%) were dropped "
                f"due to missing values in dimension columns.",
                file=sys.stderr,
            )

    # --- Step 4: Post-NaN minimum row count check ---
    post_nan_count = len(df_clean)
    if post_nan_count < MIN_ROWS:
        print(
            f"Error: after removing rows with missing values, {post_nan_count} row(s) remain "
            f"but at least {MIN_ROWS} are required.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Step 5: Non-finite / non-numeric check ---
    # At this point NaN rows have been dropped; check for inf/-inf and non-castable values.
    invalid_entries: list[tuple[str, int]] = []
    for col in dimensions:
        series = df_clean[col]
        for idx, value in series.items():
            try:
                fval = float(value)
            except (TypeError, ValueError):
                # 1-based CSV line number = original 0-based index + 2 (header row)
                invalid_entries.append((col, int(idx) + 2))
                continue
            if not np.isfinite(fval):
                invalid_entries.append((col, int(idx) + 2))

    if invalid_entries:
        lines = [
            f"Error: non-finite or non-numeric values found in dimension columns:"
        ]
        for col, line_num in invalid_entries:
            lines.append(f"  column '{col}', row {line_num}")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)

    return df_clean


# ---------------------------------------------------------------------------
# Feature matrix assembly
# ---------------------------------------------------------------------------


def build_feature_matrix(df: pd.DataFrame, dimensions: list[str]) -> np.ndarray:
    """Extract selected dimension columns and return a float64 NumPy array.

    Shape: (n_valid_grains, n_dimensions).
    """
    return df[dimensions].to_numpy(dtype=np.float64)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def fit_scaler(
    X: np.ndarray,
    dimensions: Optional[list[str]] = None,
) -> tuple[StandardScaler, np.ndarray]:
    """Fit a StandardScaler on X and return (fitted_scaler, X_scaled).

    Parameters
    ----------
    X:
        Raw feature matrix of shape (n_grains, n_dimensions).
    dimensions:
        Optional list of column names corresponding to columns in X.
        When provided, the error message for zero-variance columns names
        the offending column; otherwise a positional index is used.

    Exits with code 1 if any column has zero variance (all values identical).
    """
    # --- Zero-variance check ---
    col_stds = np.std(X, axis=0)
    zero_variance_cols = np.where(col_stds == 0)[0]
    if zero_variance_cols.size > 0:
        # Name the first offending column (or all, for clarity).
        bad_names: list[str] = []
        for col_idx in zero_variance_cols:
            if dimensions is not None and col_idx < len(dimensions):
                bad_names.append(dimensions[col_idx])
            else:
                bad_names.append(f"column index {col_idx}")
        print(
            f"Error: the following dimension column(s) have zero variance "
            f"(all values are identical): {', '.join(bad_names)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Fit and transform ---
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    return scaler, X_scaled


# ---------------------------------------------------------------------------
# Dimensionality reduction
# ---------------------------------------------------------------------------


def fit_pca(X_scaled: np.ndarray) -> tuple[PCA, np.ndarray]:
    """Fit PCA(n_components=2) on X_scaled and return (fitted_pca, X_pca)."""
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X_scaled)
    return pca, X_pca


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def run_kmeans(X_scaled: np.ndarray, k: int) -> tuple[np.ndarray, float]:
    """Run KMeans(n_clusters=k, n_init=10, random_state=42).

    Returns (labels, silhouette_score).
    Exits with code 1 if K >= number of valid grains or on convergence failure.
    """
    n_grains = len(X_scaled)

    # Requirement 4.6: K must be strictly less than the number of valid grains.
    if k >= n_grains:
        print(
            f"Error: K={k} is greater than or equal to the number of valid grains "
            f"({n_grains}). K must be less than the grain count.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run KMeans, treating ConvergenceWarning as a hard error.
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", category=ConvergenceWarning)
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            km.fit(X_scaled)
    except ConvergenceWarning as exc:
        print(
            f"Error: k-means did not converge for K={k}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(
            f"Error: k-means failed for K={k}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    labels = km.labels_
    score = silhouette_score(X_scaled, labels)
    return labels, score


# ---------------------------------------------------------------------------
# Silhouette analysis
# ---------------------------------------------------------------------------


def select_recommended_k(scores: dict[int, float]) -> int:
    """Return the K with the highest silhouette score.

    Ties broken by smallest K.  Comparison is performed to four decimal places.
    Pure function — no side effects.
    """
    best_score = max(round(s, 4) for s in scores.values())
    candidates = [k for k, s in scores.items() if round(s, 4) == best_score]
    return min(candidates)


def print_silhouette_table(scores: dict[int, float], recommended_k: int) -> None:
    """Print a summary table of silhouette scores to stdout.

    Lists each K in ascending order with its Silhouette_Score rounded to four
    decimal places and a ``*`` marker in a separate column for the recommended K.

    Example output::

        K  Silhouette_Score  Recommended
        2  0.4213
        3  0.5817            *
        4  0.4901
        5  0.4100

    Requirements: 5.3
    """
    header = f"{'K':<4} {'Silhouette_Score':<20} {'Recommended'}"
    print(header)
    for k in sorted(scores.keys()):
        score_str = f"{round(scores[k], 4):.4f}"
        marker = "*" if k == recommended_k else ""
        print(f"{k:<4} {score_str:<20} {marker}")


# ---------------------------------------------------------------------------
# Output: labelled CSV
# ---------------------------------------------------------------------------


def write_labelled_csv(
    df_original: pd.DataFrame,
    valid_mask: pd.Series,
    labels: np.ndarray,
    k: int,
    output_dir: Path,
    input_stem: str,
) -> Path:
    """Write the Labelled_CSV for a given K.

    All original columns are preserved in their original order.  A new
    ``cluster_k{K}`` column (int64) is appended; rows excluded by valid_mask
    receive the value -1.

    Returns the output path.  Exits with code 1 on write failure.
    """
    # 1. Copy to avoid mutating the caller's DataFrame.
    df = df_original.copy()

    # 2. Create the cluster column, initialised to -1 (int64).
    col_name = f"cluster_k{k}"
    df[col_name] = np.int64(-1)

    # 3. Assign cluster labels to the rows that were included in clustering.
    df.loc[valid_mask, col_name] = labels

    # Ensure int64 dtype (loc assignment with a numpy array may upcast).
    df[col_name] = df[col_name].astype("int64")

    # 4. Build the output path.
    filename = f"{input_stem}_clusters_k{k}.csv"
    output_path = Path(output_dir) / filename

    # 5 & 6. Write, catching OS-level errors.
    try:
        df.to_csv(output_path, index=False)
    except OSError as exc:
        print(
            f"Error: could not write labelled CSV to {output_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 7. Return the path.
    return output_path


# ---------------------------------------------------------------------------
# Output: scatter SVG
# ---------------------------------------------------------------------------


def write_scatter_svg(
    X_pca: np.ndarray,
    labels: np.ndarray,
    k: int,
    silhouette: float,
    output_dir: Path,
    input_stem: str,
) -> Path:
    """Produce a PCA scatter SVG with tab10 colours, legend, title, and axis labels.

    Title format: f"k={k} | Silhouette: {silhouette:.4f}"
    Axis labels: x = "PC1", y = "PC2"

    Returns the output path.  Exits with code 1 on write failure.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Build the output path.
    filename = f"{input_stem}_clusters_k{k}.svg"
    output_path = Path(output_dir) / filename

    # Use the tab10 colour palette — provides up to 10 qualitatively distinct colours.
    # matplotlib.colormaps[] is the correct API from 3.5+; cm.get_cmap() was removed in 3.9.
    cmap = matplotlib.colormaps["tab10"]

    fig, ax = plt.subplots()

    # Plot each cluster separately so matplotlib builds a legend entry per cluster.
    for cluster_id in range(k):
        mask = labels == cluster_id
        ax.scatter(
            X_pca[mask, 0],
            X_pca[mask, 1],
            color=cmap(cluster_id / 10.0),
            label=str(cluster_id),
            s=20,
        )

    # Legend with exactly K entries (labels 0 … K−1).
    ax.legend(title="Cluster")

    # Title, axis labels.
    ax.set_title(f"k={k} | Silhouette: {silhouette:.4f}")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")

    # Save as SVG, catch write failures.
    try:
        fig.savefig(output_path, format="svg")
    except OSError as exc:
        print(
            f"Error: could not write scatter SVG to {output_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        plt.close(fig)

    return output_path


# ---------------------------------------------------------------------------
# Output: silhouette report CSV
# ---------------------------------------------------------------------------


def write_silhouette_csv(
    scores: dict[int, float],
    recommended_k: int,
    output_dir: Path,
    input_stem: str,
) -> Path:
    """Write the Silhouette_Report CSV.

    Columns: k, silhouette_score (rounded to 4 dp), recommended ("true"/"false").
    Four data rows in ascending K order.

    Returns the output path.  Exits with code 1 on write failure.
    """
    # Build the output path.
    filename = f"{input_stem}_silhouette.csv"
    output_path = Path(output_dir) / filename

    # Build CSV rows in ascending K order.
    rows = []
    for k in sorted(scores.keys()):
        rounded_score = round(scores[k], 4)
        recommended_str = "true" if k == recommended_k else "false"
        rows.append(f"{k},{rounded_score:.4f},{recommended_str}")

    csv_content = "k,silhouette_score,recommended\n" + "\n".join(rows) + "\n"

    # Write, catching OS-level errors.
    try:
        output_path.write_text(csv_content, encoding="utf-8")
    except OSError as exc:
        print(
            f"Error: could not write silhouette report to {output_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    return output_path


# ---------------------------------------------------------------------------
# Output: silhouette summary SVG
# ---------------------------------------------------------------------------


def write_silhouette_svg(
    scores: dict[int, float],
    recommended_k: int,
    output_dir: Path,
    input_stem: str,
) -> Path:
    """Produce the silhouette bar-chart SVG.

    Fixed y-axis range [-1, 1]; each bar annotated with score to 4 dp.
    Recommended-k bar uses highlight colour #2196F3; others use #90CAF9.
    Title: "Silhouette Scores by k"

    Returns the output path.  Exits with code 1 on write failure or empty scores.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Requirement 9.5: exit if scores are unavailable.
    if not scores:
        print(
            "Error: silhouette scores are unavailable; cannot produce silhouette bar chart.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build the output path.
    filename = f"{input_stem}_silhouette.svg"
    output_path = Path(output_dir) / filename

    # Colours per design: highlight for recommended k, neutral for others.
    HIGHLIGHT_COLOUR = "#2196F3"
    NEUTRAL_COLOUR = "#90CAF9"

    # Sort k values ascending for consistent bar order.
    k_values = sorted(scores.keys())
    bar_scores = [scores[k] for k in k_values]
    bar_colours = [HIGHLIGHT_COLOUR if k == recommended_k else NEUTRAL_COLOUR for k in k_values]

    fig, ax = plt.subplots()

    bars = ax.bar(
        [str(k) for k in k_values],
        bar_scores,
        color=bar_colours,
    )

    # Fixed y-axis range [-1, 1].
    ax.set_ylim(-1.0, 1.0)

    # Axis labels.
    ax.set_xlabel("k")
    ax.set_ylabel("Silhouette Score")

    # Title.
    ax.set_title("Silhouette Scores by k")

    # Annotate each bar with its score to 4 decimal places.
    for bar, score in zip(bars, bar_scores):
        annotation = f"{round(score, 4):.4f}"
        # Place the annotation just above or below the bar top.
        bar_height = bar.get_height()
        if bar_height >= 0:
            y_pos = bar_height + 0.02
            va = "bottom"
        else:
            y_pos = bar_height - 0.02
            va = "top"
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            y_pos,
            annotation,
            ha="center",
            va=va,
            fontsize=9,
        )

    # Save as SVG, catch write failures.
    try:
        fig.savefig(output_path, format="svg")
    except OSError as exc:
        print(
            f"Error: could not write silhouette SVG to {output_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        plt.close(fig)

    return output_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate the full analysis pipeline.

    Pipeline order (per design):
      parse → validate → build matrix → scale → PCA →
      k-loop (kmeans + silhouette + labelled CSV + scatter SVG) →
      select recommended k → silhouette CSV + summary SVG →
      summary table + completion message
    """
    # --- 1. Parse CLI arguments ---
    args = parse_args()
    csv_path: Path = Path(args.csv_path)
    output_dir: Path = args.output_dir
    dimensions: list[str] = args.dimensions
    input_stem: str = csv_path.stem

    # --- 2. Load and validate ---
    df_clean = validate_and_load(str(csv_path), dimensions)

    # Requirement 10.1: print valid grain count, skipped count, and dimensions.
    # The skipped count is the difference between the original row count and the
    # cleaned row count.  We can compute it by reloading the raw count cheaply
    # via the length of the raw file — but validate_and_load already consumed it.
    # Instead, we compute skipped as: total_in_file − len(df_clean).
    # To get total_in_file without re-parsing, count lines in the CSV minus the
    # header row.
    try:
        with open(csv_path, encoding="utf-8", errors="replace") as _f:
            raw_row_count = sum(1 for _ in _f) - 1  # subtract header
    except OSError:
        raw_row_count = len(df_clean)  # fallback: treat as no skips

    n_valid = len(df_clean)
    n_skipped = max(0, raw_row_count - n_valid)
    print(
        f"Loaded {n_valid} valid grain(s), {n_skipped} skipped. "
        f"Dimensions: {', '.join(dimensions)}"
    )

    # --- 3. Build feature matrix ---
    X = build_feature_matrix(df_clean, dimensions)

    # --- 4. Scale (fitted once, shared across all k runs) ---
    _scaler, X_scaled = fit_scaler(X, dimensions)

    # --- 5. PCA (fitted once, shared across all k runs) ---
    _pca, X_pca = fit_pca(X_scaled)

    # valid_mask: boolean Series aligned with df_clean's index (all True for
    # clean rows).  We need this to pass into write_labelled_csv so it knows
    # which rows in the *original* DataFrame received real cluster labels.
    # df_clean preserves the original index after NaN-row removal; we load the
    # original DataFrame to build the mask.
    try:
        df_original = pd.read_csv(csv_path)
    except OSError:
        df_original = df_clean.copy()
    valid_mask: pd.Series = df_original.index.isin(df_clean.index)
    # Convert to a boolean Series indexed like df_original.
    valid_mask_series = pd.Series(valid_mask, index=df_original.index)

    # --- 6. k-loop ---
    scores: dict[int, float] = {}
    all_labels: dict[int, np.ndarray] = {}
    output_paths: list[Path] = []

    for k in K_VALUES:
        labels, score = run_kmeans(X_scaled, k)
        scores[k] = score
        all_labels[k] = labels

        # Requirement 10.2: print K and silhouette score to 4 dp after each run.
        print(f"k={k}: silhouette = {score:.4f}")

        # Write per-k outputs.
        csv_out = write_labelled_csv(
            df_original, valid_mask_series, labels, k, output_dir, input_stem
        )
        output_paths.append(csv_out)

        svg_out = write_scatter_svg(X_pca, labels, k, score, output_dir, input_stem)
        output_paths.append(svg_out)

    # --- 7. Select recommended k ---
    recommended_k = select_recommended_k(scores)

    # --- 8. Write aggregate outputs ---
    sil_csv = write_silhouette_csv(scores, recommended_k, output_dir, input_stem)
    output_paths.append(sil_csv)

    sil_svg = write_silhouette_svg(scores, recommended_k, output_dir, input_stem)
    output_paths.append(sil_svg)

    # --- 9. Print silhouette summary table ---
    print_silhouette_table(scores, recommended_k)

    # --- 10. Completion message: all output file paths, one per line ---
    # Requirement 10.3
    print("Output files:")
    for path in output_paths:
        print(str(path))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
