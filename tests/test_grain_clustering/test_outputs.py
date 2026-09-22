"""
Tests for grain_clustering output functions.

Covers:
  - Property 10: Labelled_CSV structure invariant
    (Feature: grain-clustering-analysis, Property 10)
    Validates: Requirements 6.2, 6.3, 6.4, 4.4, 4.5
  - Unit tests: write failure exits(1), overwrite behaviour
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Make the analysis package importable from inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))

from grain_clustering import (  # noqa: E402
    VALID_DIMENSIONS,
    select_recommended_k,
    write_labelled_csv,
    write_silhouette_csv,
)

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Use all seven VALID_DIMENSIONS for these tests.
DIMS = list(VALID_DIMENSIONS)

# Realistic value ranges per dimension (matching conftest factory).
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
def labelled_csv_inputs(draw: st.DrawFn) -> dict:
    """Generate (df_original, valid_mask, labels, k, dimensions) tuples.

    Constraints:
    - df_original has >= 10 rows total
    - Some rows may have NaN in one dimension column (those get label -1)
    - At least k valid (non-NaN) rows exist for each k in {2,3,4,5}
    - May include extra non-dimension columns to test column preservation
    - valid_mask = df_original[dimensions].notna().all(axis=1)
    - labels has length == valid_mask.sum(), values in [0, k-1]
    """
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed=seed)

    # Choose k for this example.
    k = draw(st.integers(min_value=2, max_value=5))

    # Number of total rows: need at least k valid rows + some NaN rows.
    # We want >= 10 total. Valid rows must be >= k.
    n_valid = draw(st.integers(min_value=k, max_value=40))
    n_nan = draw(st.integers(min_value=0, max_value=10))
    n_total = n_valid + n_nan

    # Enforce the >= 10 minimum total rows requirement.
    if n_total < 10:
        n_nan = 10 - n_valid
        n_total = n_valid + n_nan

    # Whether to include extra (non-dimension) columns.
    include_extra = draw(st.booleans())
    n_extra = draw(st.integers(min_value=1, max_value=3)) if include_extra else 0

    # Build the DataFrame column by column.
    data: dict[str, object] = {}

    # Dimension columns: all valid rows have finite values.
    for dim in DIMS:
        lo, hi = _DIM_RANGES[dim]
        col_values = rng.uniform(lo, hi, n_total)
        data[dim] = col_values

    df = pd.DataFrame(data)

    # Inject NaN: for each NaN row, blank out a random dimension column.
    if n_nan > 0:
        nan_row_indices = rng.choice(n_total, size=n_nan, replace=False)
        for row_idx in nan_row_indices:
            nan_col = DIMS[int(rng.integers(0, len(DIMS)))]
            df.at[int(row_idx), nan_col] = np.nan

    # Add extra non-dimension columns after dimensions.
    for i in range(n_extra):
        col_name = f"extra_col_{i}"
        df[col_name] = rng.uniform(0.0, 1.0, n_total)

    # Build valid_mask from the dimension columns.
    valid_mask: pd.Series = df[DIMS].notna().all(axis=1)

    # Recount actual valid rows (may differ from n_valid if NaN rows were
    # randomly placed in valid positions too — using rng.choice with replace=False
    # guarantees they're distinct, but we re-derive the mask from actual data).
    n_actual_valid = int(valid_mask.sum())

    # If fewer valid rows than k, skip by returning a minimal safe example.
    # (Hypothesis shrinking may create edge cases; we handle gracefully.)
    if n_actual_valid < k:
        # Force all rows valid, no NaN injection fallback.
        for dim in DIMS:
            lo, hi = _DIM_RANGES[dim]
            df[dim] = rng.uniform(lo, hi, n_total)
        valid_mask = df[DIMS].notna().all(axis=1)
        n_actual_valid = int(valid_mask.sum())

    # Generate labels for valid rows: integer values in [0, k-1].
    labels = rng.integers(0, k, size=n_actual_valid).astype(np.int64)

    return {
        "df_original": df,
        "valid_mask": valid_mask,
        "labels": labels,
        "k": k,
    }


# ---------------------------------------------------------------------------
# Property 10 — Labelled_CSV structure invariant
# Feature: grain-clustering-analysis, Property 10
# ---------------------------------------------------------------------------


@given(inputs=labelled_csv_inputs())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_labelled_csv_structure_invariant(inputs: dict) -> None:
    """
    **Validates: Requirements 6.2, 6.3, 6.4, 4.4, 4.5**

    Property 10: Labelled_CSV structure invariant.

    For any valid input DataFrame, the Labelled_CSV written for a given K must
    simultaneously satisfy all five sub-invariants:

    1. Contains all rows from the input in their original order (row count preserved).
    2. Contains all original columns in their original order.
    3. Has exactly one appended column named `cluster_k{K}` with int64 dtype.
    4. For every row with complete (non-NaN) dimension values, the `cluster_k{K}`
       value is an integer in [0, K−1].
    5. For every row excluded due to missing dimension values, the `cluster_k{K}`
       value is −1.
    """
    # Feature: grain-clustering-analysis, Property 10: Labelled_CSV structure invariant
    df_original: pd.DataFrame = inputs["df_original"]
    valid_mask: pd.Series = inputs["valid_mask"]
    labels: np.ndarray = inputs["labels"]
    k: int = inputs["k"]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_path = write_labelled_csv(
            df_original=df_original,
            valid_mask=valid_mask,
            labels=labels,
            k=k,
            output_dir=tmp_path,
            input_stem="test_sample",
        )

        # Read the CSV back.
        df_out = pd.read_csv(output_path)

        col_name = f"cluster_k{k}"
        original_cols = list(df_original.columns)

        # --- Sub-invariant 1: row count preserved ---
        assert len(df_out) == len(df_original), (
            f"Row count mismatch: expected {len(df_original)}, got {len(df_out)}"
        )

        # --- Sub-invariant 2: all original columns present in original order ---
        output_cols = list(df_out.columns)
        assert output_cols[: len(original_cols)] == original_cols, (
            f"Original columns not preserved in order.\n"
            f"  Expected first {len(original_cols)} cols: {original_cols}\n"
            f"  Got: {output_cols[:len(original_cols)]}"
        )

        # --- Sub-invariant 3: exactly one appended cluster column with int64 dtype ---
        assert output_cols == original_cols + [col_name], (
            f"Output columns do not match exactly [original_cols + cluster_col].\n"
            f"  Expected: {original_cols + [col_name]}\n"
            f"  Got: {output_cols}"
        )
        assert df_out[col_name].dtype == np.int64, (
            f"cluster column dtype expected int64, got {df_out[col_name].dtype}"
        )

        # --- Sub-invariant 4: valid rows have cluster label in [0, k-1] ---
        valid_indices = df_original.index[valid_mask]
        # After reading CSV with default RangeIndex, use positional alignment.
        valid_positions = [df_original.index.get_loc(idx) for idx in valid_indices]
        if len(valid_positions) > 0:
            valid_labels = df_out[col_name].iloc[valid_positions].to_numpy()
            assert (valid_labels >= 0).all() and (valid_labels <= k - 1).all(), (
                f"Valid row cluster labels out of range [0, {k - 1}].\n"
                f"  Got values: {valid_labels}"
            )

        # --- Sub-invariant 5: excluded (NaN) rows have cluster label == -1 ---
        invalid_indices = df_original.index[~valid_mask]
        invalid_positions = [df_original.index.get_loc(idx) for idx in invalid_indices]
        if len(invalid_positions) > 0:
            invalid_labels = df_out[col_name].iloc[invalid_positions].to_numpy()
            assert (invalid_labels == -1).all(), (
                f"Excluded rows must have cluster label -1.\n"
                f"  Got values: {invalid_labels}"
            )


# ---------------------------------------------------------------------------
# Unit tests — task 8.3 companion tests
# ---------------------------------------------------------------------------


class TestWriteLabelledCsvWriteFailure:
    """write_labelled_csv must exit(1) with a descriptive stderr on write failure."""

    def test_write_failure_exits_with_code_1(
        self, capsys: pytest.CaptureFixture, tmp_path: Path
    ) -> None:
        """Mocking builtins.open to raise OSError must cause sys.exit(1)."""
        rng = np.random.default_rng(seed=0)
        n = 12
        df = pd.DataFrame(
            {dim: rng.uniform(0.1, 10.0, n) for dim in VALID_DIMENSIONS}
        )
        valid_mask = df[list(VALID_DIMENSIONS)].notna().all(axis=1)
        labels = np.zeros(int(valid_mask.sum()), dtype=np.int64)

        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(SystemExit) as exc_info:
                write_labelled_csv(df, valid_mask, labels, 2, tmp_path, "sample")

        assert exc_info.value.code == 1

    def test_write_failure_prints_to_stderr(
        self, capsys: pytest.CaptureFixture, tmp_path: Path
    ) -> None:
        """On OSError, descriptive error message must go to stderr, not stdout."""
        rng = np.random.default_rng(seed=1)
        n = 12
        df = pd.DataFrame(
            {dim: rng.uniform(0.1, 10.0, n) for dim in VALID_DIMENSIONS}
        )
        valid_mask = df[list(VALID_DIMENSIONS)].notna().all(axis=1)
        labels = np.zeros(int(valid_mask.sum()), dtype=np.int64)

        with patch("builtins.open", side_effect=OSError("permission denied")):
            with pytest.raises(SystemExit):
                write_labelled_csv(df, valid_mask, labels, 3, tmp_path, "sample")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err) > 0
        # The error message should reference the output path or describe the failure.
        assert "Error" in captured.err or "error" in captured.err


class TestWriteLabelledCsvOverwritesExistingFile:
    """write_labelled_csv must overwrite an existing file (Requirement 6.5)."""

    def test_second_write_succeeds(self, tmp_path: Path) -> None:
        """Calling write_labelled_csv twice must not fail on the second call."""
        rng = np.random.default_rng(seed=2)
        n = 12
        df = pd.DataFrame(
            {dim: rng.uniform(0.1, 10.0, n) for dim in VALID_DIMENSIONS}
        )
        valid_mask = df[list(VALID_DIMENSIONS)].notna().all(axis=1)
        labels_first = np.zeros(int(valid_mask.sum()), dtype=np.int64)
        labels_second = np.ones(int(valid_mask.sum()), dtype=np.int64)

        path1 = write_labelled_csv(df, valid_mask, labels_first, 2, tmp_path, "sample")
        path2 = write_labelled_csv(df, valid_mask, labels_second, 2, tmp_path, "sample")

        assert path1 == path2

    def test_second_write_has_new_content(self, tmp_path: Path) -> None:
        """The second write must overwrite the first; file reflects new labels."""
        rng = np.random.default_rng(seed=3)
        n = 12
        df = pd.DataFrame(
            {dim: rng.uniform(0.1, 10.0, n) for dim in VALID_DIMENSIONS}
        )
        valid_mask = df[list(VALID_DIMENSIONS)].notna().all(axis=1)
        n_valid = int(valid_mask.sum())

        # First write: all labels = 0.
        labels_first = np.zeros(n_valid, dtype=np.int64)
        write_labelled_csv(df, valid_mask, labels_first, 2, tmp_path, "sample")

        # Second write: all labels = 1.
        labels_second = np.ones(n_valid, dtype=np.int64)
        path = write_labelled_csv(df, valid_mask, labels_second, 2, tmp_path, "sample")

        df_out = pd.read_csv(path)
        valid_positions = [df.index.get_loc(idx) for idx in df.index[valid_mask]]
        new_labels = df_out["cluster_k2"].iloc[valid_positions].to_numpy()

        assert (new_labels == 1).all(), (
            "Second write should overwrite with new labels (all 1), "
            f"but got: {new_labels}"
        )


# ---------------------------------------------------------------------------
# Property 12 — Silhouette report has correct structure and values
# Feature: grain-clustering-analysis, Property 12
# ---------------------------------------------------------------------------


# Feature: grain-clustering-analysis, Property 12: Silhouette report has correct structure and values
@given(
    scores=st.fixed_dictionaries({
        2: st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        3: st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        4: st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        5: st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    })
)
@settings(max_examples=100)
def test_property_12_silhouette_report_structure_and_values(scores):
    """
    **Validates: Requirements 7.2, 7.3, 7.4**

    Property 12: Silhouette report has correct structure and values.

    For any valid score dict over k in {2,3,4,5}, the written Silhouette_Report
    CSV must contain exactly four data rows with k values [2,3,4,5] in ascending
    order, each silhouette_score equal to round(actual_score, 4), and exactly one
    row with recommended == "true" corresponding to the recommended k.
    """
    recommended_k = select_recommended_k(scores)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_path = write_silhouette_csv(scores, recommended_k, tmp_path, "test")

        df = pd.read_csv(output_path)

        # 1. Exactly 4 data rows.
        assert len(df) == 4, f"Expected 4 rows, got {len(df)}"

        # 2. k column values are [2, 3, 4, 5] in ascending order.
        assert list(df["k"]) == [2, 3, 4, 5], (
            f"k column expected [2, 3, 4, 5], got {list(df['k'])}"
        )

        # 3. Each silhouette_score equals round(scores[k], 4) for that row's k.
        for _, row in df.iterrows():
            k_val = int(row["k"])
            expected_score = round(scores[k_val], 4)
            actual_score = float(row["silhouette_score"])
            assert actual_score == expected_score, (
                f"For k={k_val}: expected silhouette_score={expected_score}, got {actual_score}"
            )

        # 4. Exactly one row has recommended == True (pandas parses "true"/"false" as bool).
        true_rows = df[df["recommended"] == True]  # noqa: E712
        assert len(true_rows) == 1, (
            f"Expected exactly one 'true' row, got {len(true_rows)}"
        )

        # 5. The "true" row's k matches recommended_k.
        true_k = int(true_rows["k"].iloc[0])
        assert true_k == recommended_k, (
            f"'true' row has k={true_k}, expected recommended_k={recommended_k}"
        )


# ---------------------------------------------------------------------------
# Unit tests — task 9.3: silhouette CSV edge cases
# ---------------------------------------------------------------------------


class TestWriteSilhouetteCsvWriteFailure:
    """write_silhouette_csv must exit(1) with a descriptive stderr on write failure.

    Validates: Requirements 7.6
    """

    def test_write_failure_exits_with_code_1(
        self, capsys: pytest.CaptureFixture, tmp_path: Path
    ) -> None:
        """Patching Path.write_text to raise OSError must cause sys.exit(1)."""
        scores = {2: 0.4, 3: 0.5, 4: 0.45, 5: 0.42}
        recommended_k = select_recommended_k(scores)

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            with pytest.raises(SystemExit) as exc_info:
                write_silhouette_csv(scores, recommended_k, tmp_path, "sample")

        assert exc_info.value.code == 1

    def test_write_failure_prints_descriptive_message_to_stderr(
        self, capsys: pytest.CaptureFixture, tmp_path: Path
    ) -> None:
        """On OSError, a descriptive error message must go to stderr, not stdout."""
        scores = {2: 0.4, 3: 0.5, 4: 0.45, 5: 0.42}
        recommended_k = select_recommended_k(scores)

        with patch("pathlib.Path.write_text", side_effect=OSError("no space left")):
            with pytest.raises(SystemExit):
                write_silhouette_csv(scores, recommended_k, tmp_path, "sample")

        captured = capsys.readouterr()
        assert captured.out == "", "Nothing should be written to stdout on error"
        assert len(captured.err) > 0, "Error message must appear on stderr"
        assert "Error" in captured.err or "error" in captured.err, (
            "stderr message must contain a descriptive error indicator"
        )


class TestWriteSilhouetteCsvTieBreaking:
    """Tie-breaking rule: smallest k gets recommended='true' when scores are tied.

    Validates: Requirements 7.4
    """

    def test_smallest_tied_k_gets_true(self, tmp_path: Path) -> None:
        """When two k values share the highest score (to 4 dp), the smallest k
        must have recommended='true' in the written CSV."""
        # k=2 and k=3 both have the highest score (identical to 4 dp).
        # k=4 and k=5 have lower scores.
        tied_score = 0.6000
        scores = {2: tied_score, 3: tied_score, 4: 0.45, 5: 0.42}

        recommended_k = select_recommended_k(scores)
        assert recommended_k == 2, (
            f"select_recommended_k should return 2 for tied scores, got {recommended_k}"
        )

        output_path = write_silhouette_csv(scores, recommended_k, tmp_path, "tie_test")

        df = pd.read_csv(output_path)

        # Pandas reads "true"/"false" strings as booleans.
        true_rows = df[df["recommended"] == True]  # noqa: E712
        assert len(true_rows) == 1, (
            f"Exactly one row should be recommended='true', got {len(true_rows)}"
        )
        true_k = int(true_rows["k"].iloc[0])
        assert true_k == 2, (
            f"The smallest tied k (2) must be 'true', but got k={true_k}"
        )

    def test_all_tied_k_values_smallest_wins(self, tmp_path: Path) -> None:
        """When all four k values are tied, k=2 must have recommended='true'."""
        tied_score = 0.3333
        scores = {2: tied_score, 3: tied_score, 4: tied_score, 5: tied_score}

        recommended_k = select_recommended_k(scores)
        assert recommended_k == 2

        output_path = write_silhouette_csv(scores, recommended_k, tmp_path, "all_tied")

        df = pd.read_csv(output_path)
        true_rows = df[df["recommended"] == True]  # noqa: E712
        assert len(true_rows) == 1
        assert int(true_rows["k"].iloc[0]) == 2, (
            "When all k values tie, k=2 (smallest) must be marked 'true'"
        )

    def test_non_tied_highest_k_is_not_overridden(self, tmp_path: Path) -> None:
        """When there is a clear winner (no tie), that k gets 'true' regardless
        of whether it is the smallest."""
        scores = {2: 0.40, 3: 0.50, 4: 0.75, 5: 0.60}

        recommended_k = select_recommended_k(scores)
        assert recommended_k == 4

        output_path = write_silhouette_csv(scores, recommended_k, tmp_path, "no_tie")

        df = pd.read_csv(output_path)
        true_rows = df[df["recommended"] == True]  # noqa: E712
        assert len(true_rows) == 1
        assert int(true_rows["k"].iloc[0]) == 4, (
            "The clear winner (k=4) must be 'true', tie-breaking must not override it"
        )
