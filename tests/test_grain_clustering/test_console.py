"""
Tests for grain_clustering console progress output (main() stdout).

Covers:
  - Property 17: Console progress output reflects actual pipeline results
    (Feature: grain-clustering-analysis, Property 17)
    Validates: Requirements 10.1, 10.2, 10.3
"""

from __future__ import annotations

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# Make the analysis package importable from inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))

from grain_clustering import (  # noqa: E402
    VALID_DIMENSIONS,
    build_feature_matrix,
    fit_scaler,
    run_kmeans,
    main,
)

# ---------------------------------------------------------------------------
# Strategy: generate a valid grain DataFrame for the full pipeline
# ---------------------------------------------------------------------------

# Realistic per-dimension value ranges (same as conftest.py).
_DIM_RANGES: dict[str, tuple[float, float]] = {
    "area": (0.5, 50.0),
    "perimeter": (2.0, 40.0),
    "circularity": (0.3, 1.0),
    "roundness": (0.3, 1.0),
    "feret_diameter": (1.0, 15.0),
    "major_axis": (1.0, 12.0),
    "minor_axis": (0.5, 8.0),
}


@st.composite
def valid_grain_dataframe(draw: st.DrawFn) -> pd.DataFrame:
    """Generate a valid DataFrame suitable for the full grain-clustering pipeline.

    Guarantees:
    - All 7 dimension columns present.
    - At least 10 rows (pipeline minimum).
    - No NaN values in any dimension column.
    - No zero-variance columns (each column has multiple distinct values because
      we sample from a continuous uniform distribution over a non-trivial range).
    - All values finite float64.
    """
    n_rows = draw(st.integers(min_value=10, max_value=50))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))

    rng = np.random.default_rng(seed=seed)

    data: dict[str, np.ndarray] = {}
    for dim in VALID_DIMENSIONS:
        lo, hi = _DIM_RANGES[dim]
        values = rng.uniform(lo, hi, n_rows)
        data[dim] = values

    df = pd.DataFrame(data)

    # Safety: ensure no zero-variance columns (extremely unlikely but guarded).
    for dim in VALID_DIMENSIONS:
        assume(df[dim].nunique() > 1)

    return df


# ---------------------------------------------------------------------------
# Property 17 — Console progress output reflects actual pipeline results
# Feature: grain-clustering-analysis, Property 17: Console progress output
# reflects actual pipeline results
# Validates: Requirements 10.1, 10.2, 10.3
# ---------------------------------------------------------------------------


@given(df=valid_grain_dataframe())
@settings(
    max_examples=10,
    # A full pipeline run (4 k-means fits, 10 file writes, 5 SVG renders) easily
    # takes 500–800 ms, well above the default 200 ms deadline.  Disable the
    # deadline entirely so hypothesis does not falsify valid runs.
    deadline=None,
    # capsys is a function-scoped fixture; suppress the health-check because we
    # call capsys.readouterr() after every main() invocation which clears its
    # internal buffer, so it is safe to reuse across hypothesis examples.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_console_progress_output_reflects_pipeline_results(
    df: pd.DataFrame,
    capsys: pytest.CaptureFixture,
) -> None:
    """
    **Validates: Requirements 10.1, 10.2, 10.3**

    Property 17: Console progress output reflects actual pipeline results.

    For any valid input DataFrame, the text printed to stdout by main() must
    accurately reflect:
      (a) the actual count of valid grains and skipped grains (Req 10.1),
      (b) the correct K and silhouette score to 4 dp for each k run (Req 10.2),
      (c) all 10 output file paths, one per line (Req 10.3).

    Strategy:
    1. Write the DataFrame to a temporary CSV (managed by tempfile so hypothesis
       can generate multiple examples with fresh directories).
    2. Patch sys.argv to simulate CLI invocation.
    3. Call main() and capture stdout via capsys.readouterr().
    4. Independently compute expected counts and silhouette scores.
    5. Assert all three groups of assertions.
    """
    # Feature: grain-clustering-analysis, Property 17: Console progress output reflects actual pipeline results

    with tempfile.TemporaryDirectory() as _tmpdir:
        tmp = Path(_tmpdir)
        csv_path = tmp / "grains.csv"
        df.to_csv(csv_path, index=False)

        output_dir = tmp / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------ #
        # 2. Compute expected values independently                            #
        # ------------------------------------------------------------------ #

        # All rows are valid (strategy produces no NaN rows).
        n_total = len(df)
        n_valid_expected = len(df.dropna(subset=VALID_DIMENSIONS))
        n_skipped_expected = n_total - n_valid_expected  # 0 for our strategy

        # Independently compute silhouette scores using the same functions main() uses.
        df_clean = df.dropna(subset=VALID_DIMENSIONS)
        X = build_feature_matrix(df_clean, VALID_DIMENSIONS)
        _scaler, X_scaled = fit_scaler(X)

        expected_scores: dict[int, float] = {}
        for k in [2, 3, 4, 5]:
            _labels, score = run_kmeans(X_scaled, k)
            expected_scores[k] = score

        # Expected output file paths (10 files: 4 labelled CSVs + 4 scatter SVGs +
        # 1 silhouette CSV + 1 silhouette SVG).
        stem = csv_path.stem  # "grains"
        expected_paths: list[str] = []
        for k in [2, 3, 4, 5]:
            expected_paths.append(str(output_dir / f"{stem}_clusters_k{k}.csv"))
            expected_paths.append(str(output_dir / f"{stem}_clusters_k{k}.svg"))
        expected_paths.append(str(output_dir / f"{stem}_silhouette.csv"))
        expected_paths.append(str(output_dir / f"{stem}_silhouette.svg"))

        # ------------------------------------------------------------------ #
        # 3. Invoke main() with patched sys.argv                             #
        # ------------------------------------------------------------------ #
        test_argv = [
            "grain_clustering.py",
            str(csv_path),
            "--output-dir", str(output_dir),
        ]

        with patch.object(sys, "argv", test_argv):
            main()

        stdout = capsys.readouterr().out

        # ------------------------------------------------------------------ #
        # 4a. Assert: valid grain count and skipped count (Req 10.1)         #
        # ------------------------------------------------------------------ #
        assert str(n_valid_expected) in stdout, (
            f"stdout must report the valid grain count ({n_valid_expected}), "
            f"but it was not found in:\n{stdout}"
        )
        assert str(n_skipped_expected) in stdout, (
            f"stdout must report the skipped grain count ({n_skipped_expected}), "
            f"but it was not found in:\n{stdout}"
        )

        # ------------------------------------------------------------------ #
        # 4b. Assert: K and silhouette score to 4 dp for each k (Req 10.2)  #
        # ------------------------------------------------------------------ #
        for k, score in expected_scores.items():
            score_str = f"{score:.4f}"
            assert f"k={k}" in stdout, (
                f"stdout must contain 'k={k}' but it was not found in:\n{stdout}"
            )
            assert score_str in stdout, (
                f"stdout must contain silhouette score '{score_str}' for k={k}, "
                f"but it was not found in:\n{stdout}"
            )

        # ------------------------------------------------------------------ #
        # 4c. Assert: all 10 output file paths appear in stdout (Req 10.3)  #
        # ------------------------------------------------------------------ #
        for path_str in expected_paths:
            assert path_str in stdout, (
                f"Output path '{path_str}' must appear in stdout completion listing, "
                f"but it was not found in:\n{stdout}"
            )
