"""
Tests for validate_and_load() input validation.

Covers requirements 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5.

Properties implemented:
  - Property 3: Missing columns are detected and named
  - Property 4: Row count below minimum is rejected with observed count
  - Property 5: NaN fraction warning fires exactly at the >20% boundary
  - Property 6: Non-finite/non-numeric values are reported with exact location
"""

from __future__ import annotations

import io
import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from analysis.grain_clustering import VALID_DIMENSIONS, validate_and_load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIMENSIONS = list(VALID_DIMENSIONS)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to a CSV file."""
    df.to_csv(path, index=False)


def _make_valid_df(n_rows: int = 12, seed: int = 0) -> pd.DataFrame:
    """Return a DataFrame with all seven dimensions and no invalid values."""
    rng = np.random.default_rng(seed=seed)
    return pd.DataFrame({
        "area": rng.uniform(0.5, 50.0, n_rows),
        "perimeter": rng.uniform(2.0, 40.0, n_rows),
        "circularity": rng.uniform(0.3, 1.0, n_rows),
        "roundness": rng.uniform(0.3, 1.0, n_rows),
        "feret_diameter": rng.uniform(1.0, 15.0, n_rows),
        "major_axis": rng.uniform(1.0, 12.0, n_rows),
        "minor_axis": rng.uniform(0.5, 8.0, n_rows),
    })


# ---------------------------------------------------------------------------
# Requirement 1.4 – FileNotFoundError
# ---------------------------------------------------------------------------


def test_file_not_found_exits_with_code_1(tmp_path: Path) -> None:
    """validate_and_load exits with code 1 when the file does not exist."""
    missing = str(tmp_path / "nonexistent.csv")
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc:
            validate_and_load(missing, DIMENSIONS)
    assert exc.value.code == 1


def test_file_not_found_stderr_message(tmp_path: Path) -> None:
    """Error message for missing file should mention the file path."""
    missing = str(tmp_path / "nonexistent.csv")
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(missing, DIMENSIONS)
    assert str(missing) in mock_err.getvalue()


# ---------------------------------------------------------------------------
# Requirement 1.5 – PermissionError
# ---------------------------------------------------------------------------


def test_permission_error_exits_with_code_1(tmp_path: Path) -> None:
    """validate_and_load exits with code 1 when file cannot be read due to permissions."""
    csv_path = tmp_path / "grains.csv"
    _write_csv(_make_valid_df(), csv_path)
    with patch("pandas.read_csv", side_effect=PermissionError("denied")):
        with patch("sys.stderr", new_callable=io.StringIO):
            with pytest.raises(SystemExit) as exc:
                validate_and_load(str(csv_path), DIMENSIONS)
    assert exc.value.code == 1


def test_permission_error_stderr_message(tmp_path: Path) -> None:
    """Error message for permission error should mention the file path."""
    csv_path = tmp_path / "grains.csv"
    _write_csv(_make_valid_df(), csv_path)
    with patch("pandas.read_csv", side_effect=PermissionError("denied")):
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with pytest.raises(SystemExit):
                validate_and_load(str(csv_path), DIMENSIONS)
    assert str(csv_path) in mock_err.getvalue()


# ---------------------------------------------------------------------------
# Requirement 2.2 – Missing dimension columns
# ---------------------------------------------------------------------------


def test_missing_column_exits_with_code_1(tmp_path: Path) -> None:
    """validate_and_load exits with code 1 when a selected dimension column is absent."""
    df = _make_valid_df()
    df = df.drop(columns=["area"])
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)
    assert exc.value.code == 1


def test_missing_column_names_in_stderr(tmp_path: Path) -> None:
    """Error message must name the missing columns."""
    df = _make_valid_df().drop(columns=["area", "roundness"])
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    assert "area" in stderr
    assert "roundness" in stderr


# ---------------------------------------------------------------------------
# Requirement 2.1 – Validation order: column check before row count check
# ---------------------------------------------------------------------------


def test_column_check_before_row_count(tmp_path: Path) -> None:
    """Column presence error fires before minimum row count error.

    A CSV with only 3 rows AND a missing column should error on the missing column.
    """
    # 3 rows < 10 minimum, and 'area' column missing — column error should fire first.
    df = _make_valid_df(n_rows=3).drop(columns=["area"])
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    # Must mention missing column, not row count
    assert "area" in stderr or "missing" in stderr.lower()


# ---------------------------------------------------------------------------
# Requirement 2.3 – Minimum row count (raw, before NaN removal)
# ---------------------------------------------------------------------------


def test_fewer_than_10_rows_exits_with_code_1(tmp_path: Path) -> None:
    """validate_and_load exits with code 1 when raw row count < 10."""
    df = _make_valid_df(n_rows=9)
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)
    assert exc.value.code == 1


def test_row_count_error_states_observed_count_and_threshold(tmp_path: Path) -> None:
    """Error message for low row count must state both observed count and threshold (10)."""
    df = _make_valid_df(n_rows=7)
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    # Observed count
    assert "7" in stderr, f"Expected '7' in stderr; got:\n{stderr}"
    # Threshold
    assert "10" in stderr, f"Expected '10' in stderr; got:\n{stderr}"


def test_exactly_10_rows_accepted(tmp_path: Path) -> None:
    """A CSV with exactly 10 rows passes the minimum row count check."""
    df = _make_valid_df(n_rows=10)
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    result = validate_and_load(str(csv_path), DIMENSIONS)
    assert len(result) == 10


def test_row_count_check_uses_raw_count(tmp_path: Path) -> None:
    """The raw (pre-NaN) row count is used for the minimum row check.

    A CSV with 10 raw rows where 2 have NaNs should NOT fail the minimum-row check
    on the raw data even though post-NaN count is 8.
    This verifies the check fires on raw data (step 2 in spec order), not after NaN removal.
    """
    df = _make_valid_df(n_rows=10)
    # Inject NaNs in 2 rows (so post-NaN will be 8, below minimum)
    df.loc[0, "area"] = np.nan
    df.loc[1, "area"] = np.nan
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)
    # Should fail — but on the POST-NaN check (step 4), not the raw check (step 2).
    # The raw check passes (10 >= 10). The post-NaN check (8 < 10) fails.
    assert exc.value.code == 1
    stderr = mock_err.getvalue()
    assert "8" in stderr, f"Expected post-NaN count '8' in stderr; got:\n{stderr}"


# ---------------------------------------------------------------------------
# Requirement 2.4 – NaN row removal and >20% warning
# ---------------------------------------------------------------------------


def test_nan_rows_dropped_from_result(tmp_path: Path) -> None:
    """Rows with NaN in dimension columns are not returned."""
    df = _make_valid_df(n_rows=12)
    df.loc[0, "area"] = np.nan
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    result = validate_and_load(str(csv_path), DIMENSIONS)
    assert 0 not in result.index


def test_nan_warning_not_emitted_at_20_percent(tmp_path: Path) -> None:
    """No warning when exactly 20% of rows are NaN (≤20% threshold is safe)."""
    # 10 rows, 2 NaN = exactly 20%
    df = _make_valid_df(n_rows=10)
    df.loc[0, "area"] = np.nan
    df.loc[1, "area"] = np.nan
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    # 8 remaining rows < 10 minimum will cause an exit, but the NaN warning check
    # (step 3) happens before the post-NaN minimum check (step 4).
    # We capture stderr and verify no NaN-warning line appears before the row-count error.
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    # The warning mentions "dropped" if it fired
    assert "dropped" not in stderr.lower(), (
        f"Unexpected NaN warning at exactly 20%; stderr:\n{stderr}"
    )


def test_nan_warning_emitted_above_20_percent(tmp_path: Path) -> None:
    """Warning IS emitted when >20% of rows are dropped due to NaN."""
    # 20 rows, 5 NaN = 25% > 20%
    df = _make_valid_df(n_rows=20)
    for i in range(5):
        df.loc[i, "area"] = np.nan
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        result = validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    assert "dropped" in stderr.lower() or "warning" in stderr.lower(), (
        f"Expected NaN warning at 25%; stderr:\n{stderr}"
    )
    assert "5" in stderr


def test_nan_warning_contains_count_and_percentage(tmp_path: Path) -> None:
    """NaN warning message states count and percentage of dropped rows."""
    # 20 rows, 6 NaN = 30%
    df = _make_valid_df(n_rows=20)
    for i in range(6):
        df.loc[i, "area"] = np.nan
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    assert "6" in stderr
    # percentage should appear (30.0%)
    assert "30" in stderr


def test_nan_removal_preserves_original_index(tmp_path: Path) -> None:
    """Returned DataFrame preserves the original index (not reset)."""
    df = _make_valid_df(n_rows=12)
    df.loc[3, "area"] = np.nan
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    result = validate_and_load(str(csv_path), DIMENSIONS)
    # Row 3 should be gone, row 4 should still be at index 4
    assert 3 not in result.index
    assert 4 in result.index


# ---------------------------------------------------------------------------
# Requirement 2.5 – Non-finite / non-numeric check
# ---------------------------------------------------------------------------


def test_infinite_value_exits_with_code_1(tmp_path: Path) -> None:
    """validate_and_load exits with code 1 when a dimension contains inf."""
    df = _make_valid_df(n_rows=12)
    df.loc[2, "area"] = float("inf")
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)
    assert exc.value.code == 1


def test_negative_infinite_value_exits_with_code_1(tmp_path: Path) -> None:
    """validate_and_load exits with code 1 when a dimension contains -inf."""
    df = _make_valid_df(n_rows=12)
    df.loc[5, "perimeter"] = float("-inf")
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO):
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)
    assert exc.value.code == 1


def test_non_finite_error_names_column(tmp_path: Path) -> None:
    """Error message for non-finite value must name the affected column."""
    df = _make_valid_df(n_rows=12)
    df.loc[4, "circularity"] = float("inf")
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    assert "circularity" in stderr


def test_non_finite_error_states_1based_row_index(tmp_path: Path) -> None:
    """Error message must state 1-based row index (CSV line = original_index + 2)."""
    df = _make_valid_df(n_rows=12)
    # Row at 0-based index 4 → CSV line = 4 + 2 = 6
    df.loc[4, "area"] = float("inf")
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit):
            validate_and_load(str(csv_path), DIMENSIONS)
    stderr = mock_err.getvalue()
    assert "6" in stderr, f"Expected '6' (1-based row) in stderr; got:\n{stderr}"


def test_valid_data_returns_dataframe(tmp_path: Path) -> None:
    """validate_and_load returns a DataFrame for fully valid input."""
    df = _make_valid_df(n_rows=12)
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    result = validate_and_load(str(csv_path), DIMENSIONS)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 12


def test_valid_data_returned_df_has_all_original_columns(tmp_path: Path) -> None:
    """Returned DataFrame contains all original columns including extras."""
    df = _make_valid_df(n_rows=12)
    df["extra_col"] = "foo"
    csv_path = tmp_path / "grains.csv"
    _write_csv(df, csv_path)
    result = validate_and_load(str(csv_path), DIMENSIONS)
    assert "extra_col" in result.columns


# ---------------------------------------------------------------------------
# Property 3: Missing columns are detected and named
# Feature: grain-clustering-analysis, Property 3: Missing columns are detected and named
# ---------------------------------------------------------------------------


@given(
    missing_subset=st.lists(
        st.sampled_from(DIMENSIONS),
        min_size=1,
        max_size=len(DIMENSIONS) - 1,  # keep at least 1 col so pandas can parse
        unique=True,
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_missing_columns_detected_and_named(
    missing_subset: list[str],
) -> None:
    """Property 3: Missing columns are detected and named.
    **Validates: Requirements 2.2**

    For any subset of dimensions absent from the CSV, validate_and_load must
    exit with non-zero code and name exactly the missing columns in stderr.
    At least one non-missing column must remain so pandas can read the file.
    """
    df = _make_valid_df(n_rows=12)
    df = df.drop(columns=missing_subset)
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / f"missing_{'_'.join(missing_subset)}.csv"
        _write_csv(df, csv_path)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with pytest.raises(SystemExit) as exc:
                validate_and_load(str(csv_path), DIMENSIONS)

    assert exc.value.code != 0
    stderr = mock_err.getvalue()
    for col in missing_subset:
        assert col in stderr, (
            f"Expected missing column '{col}' in stderr; got:\n{stderr}"
        )


# ---------------------------------------------------------------------------
# Property 4: Row count below minimum is rejected with observed count
# Feature: grain-clustering-analysis, Property 4: Row count below minimum
# ---------------------------------------------------------------------------


@given(n_rows=st.integers(min_value=0, max_value=9))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_below_minimum_row_count_rejected(n_rows: int) -> None:
    """Property 4: Row count below minimum is rejected with observed count.
    **Validates: Requirements 2.3**

    For any CSV with fewer than 10 grain rows, validate_and_load must exit with
    a non-zero code and the error message must state both the observed count and
    the minimum threshold of 10.
    """
    df = _make_valid_df(n_rows=max(n_rows, 1)) if n_rows > 0 else pd.DataFrame(
        columns=DIMENSIONS
    )
    # Truncate to exactly n_rows
    df = df.iloc[:n_rows]
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / f"rows_{n_rows}.csv"
        _write_csv(df, csv_path)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with pytest.raises(SystemExit) as exc:
                validate_and_load(str(csv_path), DIMENSIONS)

    assert exc.value.code != 0
    stderr = mock_err.getvalue()
    assert str(n_rows) in stderr, (
        f"Expected observed count '{n_rows}' in stderr; got:\n{stderr}"
    )
    assert "10" in stderr, f"Expected threshold '10' in stderr; got:\n{stderr}"


# ---------------------------------------------------------------------------
# Property 5: NaN fraction warning fires exactly at the >20% boundary
# Feature: grain-clustering-analysis, Property 5: NaN warning at >20% boundary
# ---------------------------------------------------------------------------


@given(
    total_rows=st.integers(min_value=20, max_value=50),
    nan_count=st.integers(min_value=0, max_value=15),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_nan_fraction_warning_boundary(
    total_rows: int, nan_count: int,
) -> None:
    """Property 5: NaN fraction warning fires exactly at the >20% boundary.
    **Validates: Requirements 2.4**

    For any input DataFrame:
    - NaN fraction <= 20%: no warning emitted
    - NaN fraction > 20%: warning emitted with count and percentage
    """
    # Ensure nan_count doesn't exceed total and post-NaN count >= 10
    nan_count = min(nan_count, total_rows - 10)
    assume(nan_count >= 0)
    assume(total_rows - nan_count >= 10)  # so we don't trigger post-NaN row failure

    df = _make_valid_df(n_rows=total_rows, seed=total_rows)
    for i in range(nan_count):
        df.loc[i, "area"] = np.nan

    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / f"nan_{total_rows}_{nan_count}.csv"
        _write_csv(df, csv_path)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            try:
                validate_and_load(str(csv_path), DIMENSIONS)
            except SystemExit:
                pass
    stderr = mock_err.getvalue()

    fraction = nan_count / total_rows if total_rows > 0 else 0.0
    warning_fired = "dropped" in stderr.lower()

    if fraction > 0.20:
        assert warning_fired, (
            f"Expected NaN warning for {nan_count}/{total_rows} "
            f"({fraction*100:.1f}%); got stderr:\n{stderr}"
        )
        assert str(nan_count) in stderr
    else:
        assert not warning_fired, (
            f"Unexpected NaN warning for {nan_count}/{total_rows} "
            f"({fraction*100:.1f}%); got stderr:\n{stderr}"
        )


# ---------------------------------------------------------------------------
# Property 6: Non-finite/non-numeric values reported with exact location
# Feature: grain-clustering-analysis, Property 6: Non-finite/non-numeric values are reported with exact location
# ---------------------------------------------------------------------------


@given(
    row_idx=st.integers(min_value=0, max_value=9),
    col_name=st.sampled_from(DIMENSIONS),
    bad_value=st.one_of(
        st.just(float("inf")),
        st.just(float("-inf")),
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_non_finite_values_reported_with_location(
    row_idx: int, col_name: str, bad_value: float,
) -> None:
    """Property 6: Non-finite values are reported with exact location.
    **Validates: Requirements 2.5**

    For any position of inf/-inf values in the feature columns, the error
    message must name the column and the 1-based row index (original_index + 2),
    and the exit code must be non-zero.

    Note: inf/-inf survive dropna (step 3) and are caught by the isfinite check
    in step 5.  NaN values are handled separately by the dropna path (step 3).
    """
    df = _make_valid_df(n_rows=12, seed=row_idx)
    df.loc[row_idx, col_name] = bad_value
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / f"bad_{row_idx}_{col_name}.csv"
        _write_csv(df, csv_path)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with pytest.raises(SystemExit) as exc:
                validate_and_load(str(csv_path), DIMENSIONS)

    assert exc.value.code != 0
    stderr = mock_err.getvalue()

    assert col_name in stderr, (
        f"Expected column '{col_name}' in stderr; got:\n{stderr}"
    )
    expected_line = row_idx + 2  # 1-based CSV line number (header + 1-based)
    assert str(expected_line) in stderr, (
        f"Expected 1-based row {expected_line} in stderr; got:\n{stderr}"
    )


# Non-numeric strings that cannot be cast to float.
# These must not contain characters that pandas interprets as NaN (empty, "NA", "nan", etc.)
_NON_NUMERIC_STRINGS = [
    "not_a_number",
    "abc",
    "1e999x",
    "??",
    "true",
    "N/A_text",
    "#VALUE!",
]


@given(
    row_idx=st.integers(min_value=0, max_value=9),
    col_name=st.sampled_from(DIMENSIONS),
    bad_str=st.sampled_from(_NON_NUMERIC_STRINGS),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_non_numeric_strings_reported_with_location(
    row_idx: int, col_name: str, bad_str: str,
) -> None:
    """Property 6 (non-numeric string variant): Non-numeric string values are reported with exact location.
    **Validates: Requirements 2.5**

    For any position of a non-castable string in a feature column, validate_and_load
    must exit with a non-zero code, and stderr must contain the column name and the
    1-based CSV row index (original_index + 2).

    Non-numeric strings survive dropna (they are not NaN) and are caught by the
    float() cast in step 5 of validate_and_load.
    """
    df = _make_valid_df(n_rows=12, seed=row_idx)
    # Inject the non-numeric string; the column becomes object dtype.
    df[col_name] = df[col_name].astype(object)
    df.loc[row_idx, col_name] = bad_str

    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = Path(tmp_dir) / f"bad_str_{row_idx}_{col_name}.csv"
        _write_csv(df, csv_path)

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with pytest.raises(SystemExit) as exc:
                validate_and_load(str(csv_path), DIMENSIONS)

    assert exc.value.code != 0
    stderr = mock_err.getvalue()

    assert col_name in stderr, (
        f"Expected column '{col_name}' in stderr; got:\n{stderr}"
    )
    expected_line = row_idx + 2  # 1-based CSV line number (header + 1-based)
    assert str(expected_line) in stderr, (
        f"Expected 1-based row {expected_line} in stderr; got:\n{stderr}"
    )


# ===========================================================================
# Task 3.6 – Unit tests for validation edge cases
# Requirements: 1.4, 1.5, 2.1, 2.3, 2.4
# ===========================================================================


# ---------------------------------------------------------------------------
# test_validation_order – multiple constraints violated simultaneously
# ---------------------------------------------------------------------------


def test_validation_order_column_error_fires_first(tmp_path: Path) -> None:
    """Requirement 2.1: column presence check fires before minimum row count check.

    Craft a CSV that simultaneously violates:
      - missing column ('area' absent)
      - fewer than 10 rows (only 3 rows present)
      - NaN values in existing rows

    Assert:
      - SystemExit is raised (some error fired)
      - stderr mentions the missing column name ('area')
      - stderr does NOT mention the row-count error message
        (i.e. the "3 row(s) but at least 10" message is absent)
    """
    # Build a 3-row DataFrame missing 'area'; inject a NaN too.
    df = _make_valid_df(n_rows=3).drop(columns=["area"])
    df.loc[0, "perimeter"] = np.nan

    csv_path = tmp_path / "multi_violation.csv"
    _write_csv(df, csv_path)

    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)

    assert exc.value.code == 1
    stderr = mock_err.getvalue()

    # First error (column check) must mention the missing column.
    assert "area" in stderr, (
        f"Expected 'area' (missing column) in stderr; got:\n{stderr}"
    )
    # Second error (row count) must NOT appear — it should have been short-circuited.
    assert "3 row" not in stderr, (
        f"Row-count error should not appear (column check fired first); got:\n{stderr}"
    )


# ---------------------------------------------------------------------------
# Exactly 9 rows fails; exactly 10 rows passes
# ---------------------------------------------------------------------------


def test_exactly_9_rows_exits_with_code_1(tmp_path: Path) -> None:
    """A CSV with exactly 9 rows triggers exit(1).

    The error message must include both the observed count (9) and the
    minimum threshold (10). — Requirements 2.3
    """
    df = _make_valid_df(n_rows=9)
    csv_path = tmp_path / "nine_rows.csv"
    _write_csv(df, csv_path)

    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        with pytest.raises(SystemExit) as exc:
            validate_and_load(str(csv_path), DIMENSIONS)

    assert exc.value.code == 1
    stderr = mock_err.getvalue()
    assert "9" in stderr, f"Expected observed count '9' in stderr; got:\n{stderr}"
    assert "10" in stderr, f"Expected threshold '10' in stderr; got:\n{stderr}"


def test_exactly_10_complete_rows_passes(tmp_path: Path) -> None:
    """A CSV with exactly 10 fully-valid rows succeeds with no exit and returns all rows.

    — Requirements 2.3
    """
    df = _make_valid_df(n_rows=10)
    csv_path = tmp_path / "ten_rows.csv"
    _write_csv(df, csv_path)

    # Should not raise.
    result = validate_and_load(str(csv_path), DIMENSIONS)
    assert len(result) == 10, f"Expected 10 rows back, got {len(result)}"


# ---------------------------------------------------------------------------
# NaN fraction boundary: exactly 20% → no warning; just over 20% → warning
# ---------------------------------------------------------------------------


def test_nan_exactly_20_percent_no_warning(tmp_path: Path) -> None:
    """Exactly 20% NaN rows must NOT trigger a warning.  — Requirement 2.4

    Setup: 50 total rows, 10 NaN rows = exactly 20%.
    Post-NaN count is 40 (≥ 10), so no exit is expected.
    Assert 'dropped' / 'warning' does not appear in stderr.
    """
    total = 50
    nan_count = 10  # 10/50 = 20.0%
    df = _make_valid_df(n_rows=total, seed=7)
    for i in range(nan_count):
        df.loc[i, "area"] = np.nan

    csv_path = tmp_path / "nan_20pct.csv"
    _write_csv(df, csv_path)

    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        result = validate_and_load(str(csv_path), DIMENSIONS)

    stderr = mock_err.getvalue()
    assert "dropped" not in stderr.lower(), (
        f"No NaN warning expected at exactly 20%; stderr:\n{stderr}"
    )
    assert len(result) == total - nan_count


def test_nan_just_over_20_percent_warning_fires(tmp_path: Path) -> None:
    """Just over 20% NaN rows MUST trigger a warning.  — Requirement 2.4

    Setup: 30 total rows, 7 NaN rows = 23.3…% > 20%.
    Post-NaN count is 23 (≥ 10), so the function succeeds after printing the warning.
    Assert stderr mentions 'dropped' (or 'warning'), the count (7), and a percentage > 20.
    """
    total = 30
    nan_count = 7  # 7/30 ≈ 23.3%
    df = _make_valid_df(n_rows=total, seed=8)
    for i in range(nan_count):
        df.loc[i, "area"] = np.nan

    csv_path = tmp_path / "nan_23pct.csv"
    _write_csv(df, csv_path)

    with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
        result = validate_and_load(str(csv_path), DIMENSIONS)

    stderr = mock_err.getvalue()
    assert "dropped" in stderr.lower() or "warning" in stderr.lower(), (
        f"Expected NaN warning at ~23.3%; stderr:\n{stderr}"
    )
    assert "7" in stderr, f"Expected dropped count '7' in stderr; got:\n{stderr}"
    assert len(result) == total - nan_count
