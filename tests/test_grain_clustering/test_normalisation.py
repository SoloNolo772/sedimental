"""
Tests for grain_clustering.fit_scaler.

Covers:
  - Property 7: zero-mean, unit-variance per column after scaling
    (Feature: grain-clustering-analysis, Property 7)
  - Edge cases: zero-variance column detection (Req 3.3)
  - Unit tests: basic scaling behaviour, return types, multiple columns
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

# Make the analysis package importable from inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))

from grain_clustering import VALID_DIMENSIONS, fit_scaler  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIMS = list(VALID_DIMENSIONS)  # 7 names


def _make_nonzero_variance_matrix(
    n_rows: int,
    n_cols: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return a float64 matrix where every column has positive variance."""
    while True:
        X = rng.uniform(-100.0, 100.0, size=(n_rows, n_cols))
        if np.all(np.std(X, axis=0) > 0):
            return X


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestFitScalerBasic:
    """Concrete unit tests for fit_scaler."""

    def test_returns_tuple_of_two(self) -> None:
        rng = np.random.default_rng(42)
        X = rng.uniform(1.0, 10.0, size=(15, 3))
        result = fit_scaler(X)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_scaler_is_standard_scaler(self) -> None:
        from sklearn.preprocessing import StandardScaler

        rng = np.random.default_rng(42)
        X = rng.uniform(1.0, 10.0, size=(15, 3))
        scaler, _ = fit_scaler(X)
        assert isinstance(scaler, StandardScaler)

    def test_scaled_array_shape_matches_input(self) -> None:
        rng = np.random.default_rng(42)
        X = rng.uniform(1.0, 10.0, size=(20, 7))
        _, X_scaled = fit_scaler(X)
        assert X_scaled.shape == X.shape

    def test_single_column_mean_near_zero(self) -> None:
        X = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
        _, X_scaled = fit_scaler(X)
        assert abs(np.mean(X_scaled[:, 0])) < 1e-10

    def test_single_column_std_near_one(self) -> None:
        X = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
        _, X_scaled = fit_scaler(X)
        assert abs(np.std(X_scaled[:, 0]) - 1.0) < 1e-10

    def test_all_seven_columns_scaled(self) -> None:
        rng = np.random.default_rng(0)
        X = rng.uniform(0.1, 100.0, size=(12, 7))
        _, X_scaled = fit_scaler(X)
        for col_idx in range(7):
            assert abs(np.mean(X_scaled[:, col_idx])) < 1e-9, (
                f"column {col_idx} mean not near zero"
            )
            assert abs(np.std(X_scaled[:, col_idx]) - 1.0) < 1e-9, (
                f"column {col_idx} std not near 1"
            )

    def test_scaler_fitted_once_produces_same_transform(self) -> None:
        """The same fitted scaler must reproduce the same X_scaled."""
        rng = np.random.default_rng(7)
        X = rng.uniform(0.5, 50.0, size=(15, 4))
        scaler, X_scaled_first = fit_scaler(X)
        X_scaled_again = scaler.transform(X)
        np.testing.assert_array_equal(X_scaled_first, X_scaled_again)


# ---------------------------------------------------------------------------
# Zero-variance / error-handling unit tests
# ---------------------------------------------------------------------------


class TestFitScalerZeroVariance:
    """fit_scaler must exit(1) when any column is constant."""

    def test_single_constant_column_exits(self) -> None:
        X = np.ones((15, 3))  # all three columns are constant
        with pytest.raises(SystemExit) as exc_info:
            fit_scaler(X)
        assert exc_info.value.code == 1

    def test_one_constant_among_valid_columns_exits(self) -> None:
        rng = np.random.default_rng(1)
        X = rng.uniform(1.0, 10.0, size=(15, 3))
        X[:, 1] = 5.0  # make column 1 constant
        with pytest.raises(SystemExit) as exc_info:
            fit_scaler(X)
        assert exc_info.value.code == 1

    def test_error_message_names_constant_column_by_dimension(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        rng = np.random.default_rng(2)
        X = rng.uniform(1.0, 10.0, size=(15, 3))
        X[:, 2] = 7.0  # column index 2
        dims = ["area", "perimeter", "circularity"]
        with pytest.raises(SystemExit):
            fit_scaler(X, dimensions=dims)
        captured = capsys.readouterr()
        assert "circularity" in captured.err

    def test_error_message_names_constant_column_by_index_when_no_dims(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        rng = np.random.default_rng(3)
        X = rng.uniform(1.0, 10.0, size=(15, 2))
        X[:, 0] = 3.14  # column index 0
        with pytest.raises(SystemExit):
            fit_scaler(X)
        captured = capsys.readouterr()
        assert "column index 0" in captured.err

    def test_error_message_goes_to_stderr(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        X = np.full((12, 2), 1.0)
        with pytest.raises(SystemExit):
            fit_scaler(X)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err) > 0

    def test_no_exit_when_all_columns_have_variance(self) -> None:
        rng = np.random.default_rng(99)
        X = rng.uniform(0.1, 50.0, size=(12, 7))
        # Should not raise
        scaler, X_scaled = fit_scaler(X, dimensions=DIMS)
        assert X_scaled is not None


# ---------------------------------------------------------------------------
# Property-based test — Property 7
# Feature: grain-clustering-analysis, Property 7:
# For any feature matrix X with at least two distinct values per column,
# after applying fit_scaler, each column of X_scaled must have mean ≈ 0
# and std ≈ 1 (within floating-point tolerance).
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------


@st.composite
def nonzero_variance_matrix(draw: st.DrawFn) -> np.ndarray:
    """Generate a float64 matrix where every column has at least 2 distinct values."""
    n_rows = draw(st.integers(min_value=10, max_value=100))
    n_cols = draw(st.integers(min_value=1, max_value=7))

    # Draw each column ensuring at least two distinct finite values.
    cols: list[np.ndarray] = []
    for _ in range(n_cols):
        # Draw a column; ensure it has positive variance by forcing the first
        # two values to differ from each other.
        base = draw(
            arrays(
                dtype=np.float64,
                shape=n_rows,
                elements=st.floats(
                    min_value=-1e6,
                    max_value=1e6,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            )
        )
        # Guarantee variance: set first element to one extreme, second to another.
        base[0] = draw(st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False))
        base[1] = base[0] + draw(st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False))
        cols.append(base)

    return np.column_stack(cols)


@given(X=nonzero_variance_matrix())
@settings(max_examples=100)
def test_fit_scaler_zero_mean_unit_variance(X: np.ndarray) -> None:
    """
    **Validates: Requirements 3.1**

    Property 7: For any feature matrix X with at least two distinct values per
    column, each column of the returned X_scaled has mean ≈ 0 and std ≈ 1.
    """
    _, X_scaled = fit_scaler(X)

    n_cols = X.shape[1]
    for col_idx in range(n_cols):
        col = X_scaled[:, col_idx]
        mean = np.mean(col)
        std = np.std(col)
        assert abs(mean) < 1e-9, (
            f"Column {col_idx}: mean={mean} is not near zero"
        )
        assert abs(std - 1.0) < 1e-9, (
            f"Column {col_idx}: std={std} is not near 1.0"
        )
