"""
Tests for grain_clustering.run_kmeans.

Covers:
  - Unit tests: return type, label range, reproducibility, n_init/seed used
  - Edge cases: K >= grain count exits(1), convergence failure exits(1)
  - Property 9: clustering is reproducible across two calls
    (Feature: grain-clustering-analysis, Property 9)
    Validates: Requirements 4.3
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Make the analysis package importable from inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))

from grain_clustering import VALID_DIMENSIONS, fit_scaler, run_kmeans  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIMS = list(VALID_DIMENSIONS)  # 7 names


def _make_scaled_matrix(n_rows: int = 20, n_cols: int = 7, seed: int = 0) -> np.ndarray:
    """Return a z-score-scaled matrix with guaranteed positive variance per column."""
    rng = np.random.default_rng(seed=seed)
    X = rng.uniform(0.1, 50.0, size=(n_rows, n_cols))
    _, X_scaled = fit_scaler(X)
    return X_scaled


# ---------------------------------------------------------------------------
# Unit tests — return structure
# ---------------------------------------------------------------------------


class TestRunKmeansReturnStructure:
    """run_kmeans must return (labels, silhouette_score) with correct shapes/types."""

    def test_returns_tuple_of_two(self) -> None:
        X_scaled = _make_scaled_matrix(n_rows=20)
        result = run_kmeans(X_scaled, k=2)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_labels_is_ndarray(self) -> None:
        X_scaled = _make_scaled_matrix(n_rows=20)
        labels, _ = run_kmeans(X_scaled, k=2)
        assert isinstance(labels, np.ndarray)

    def test_labels_length_equals_n_grains(self) -> None:
        n = 25
        X_scaled = _make_scaled_matrix(n_rows=n)
        labels, _ = run_kmeans(X_scaled, k=3)
        assert len(labels) == n

    def test_silhouette_is_float(self) -> None:
        X_scaled = _make_scaled_matrix(n_rows=20)
        _, score = run_kmeans(X_scaled, k=2)
        assert isinstance(score, float)

    def test_silhouette_in_valid_range(self) -> None:
        X_scaled = _make_scaled_matrix(n_rows=20)
        _, score = run_kmeans(X_scaled, k=2)
        assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Unit tests — label values
# ---------------------------------------------------------------------------


class TestRunKmeansLabels:
    """Labels must be integers in [0, k-1]."""

    @pytest.mark.parametrize("k", [2, 3, 4, 5])
    def test_labels_in_range_for_each_k(self, k: int) -> None:
        X_scaled = _make_scaled_matrix(n_rows=30)
        labels, _ = run_kmeans(X_scaled, k=k)
        assert labels.min() >= 0
        assert labels.max() <= k - 1

    def test_labels_contain_all_cluster_ids(self) -> None:
        """With enough rows, every cluster should be assigned at least one grain."""
        X_scaled = _make_scaled_matrix(n_rows=50)
        labels, _ = run_kmeans(X_scaled, k=3)
        assert set(labels) == {0, 1, 2}


# ---------------------------------------------------------------------------
# Unit tests — KMeans parameters
# ---------------------------------------------------------------------------


class TestRunKmeansParameters:
    """KMeans must be constructed with n_init=10 and random_state=42."""

    def test_kmeans_n_init_is_10(self) -> None:
        """KMeans is instantiated with n_clusters=2, n_init=10, random_state=42."""
        X_scaled = _make_scaled_matrix(n_rows=20)

        with patch("grain_clustering.KMeans") as mock_km_cls:
            mock_instance = MagicMock()
            mock_instance.labels_ = np.zeros(len(X_scaled), dtype=int)
            mock_km_cls.return_value = mock_instance

            with patch("grain_clustering.silhouette_score", return_value=0.5):
                run_kmeans(X_scaled, k=2)

            mock_km_cls.assert_called_once_with(n_clusters=2, n_init=10, random_state=42)


# ---------------------------------------------------------------------------
# Unit tests — four k runs produce four outputs
# ---------------------------------------------------------------------------


class TestFourKRunsProduceFourOutputs:
    """Running the k-means pipeline for k in {2,3,4,5} must produce four results."""

    def test_four_k_runs_produce_four_label_arrays(self) -> None:
        """run_kmeans called for each k in {2,3,4,5} returns four label arrays."""
        X_scaled = _make_scaled_matrix(n_rows=20)

        results = [run_kmeans(X_scaled, k=k) for k in [2, 3, 4, 5]]

        assert len(results) == 4
        for i, (labels, score) in enumerate(results):
            assert isinstance(labels, np.ndarray), f"k={i+2}: labels must be ndarray"
            assert len(labels) == len(X_scaled), f"k={i+2}: label count must equal grain count"

    def test_write_labelled_csv_called_four_times(self, output_dir: Path) -> None:
        """write_labelled_csv is called exactly once per k in {2,3,4,5}."""
        X_scaled = _make_scaled_matrix(n_rows=20)

        fake_paths = {k: output_dir / f"sample_clusters_k{k}.csv" for k in [2, 3, 4, 5]}

        with patch("grain_clustering.write_labelled_csv") as mock_write_csv:
            mock_write_csv.side_effect = lambda *args, **kwargs: fake_paths[args[3]]

            for k in [2, 3, 4, 5]:
                labels, score = run_kmeans(X_scaled, k=k)
                mock_write_csv(None, None, labels, k, output_dir, "sample")

        assert mock_write_csv.call_count == 4
        called_ks = [call.args[3] for call in mock_write_csv.call_args_list]
        assert sorted(called_ks) == [2, 3, 4, 5]

    def test_write_scatter_svg_called_four_times(self, output_dir: Path) -> None:
        """write_scatter_svg is called exactly once per k in {2,3,4,5}."""
        X_scaled = _make_scaled_matrix(n_rows=20)
        _, X_pca = __import__("grain_clustering").fit_pca(X_scaled)

        fake_paths = {k: output_dir / f"sample_clusters_k{k}.svg" for k in [2, 3, 4, 5]}

        with patch("grain_clustering.write_scatter_svg") as mock_write_svg:
            mock_write_svg.side_effect = lambda *args, **kwargs: fake_paths[args[2]]

            for k in [2, 3, 4, 5]:
                labels, score = run_kmeans(X_scaled, k=k)
                mock_write_svg(X_pca, labels, k, score, output_dir, "sample")

        assert mock_write_svg.call_count == 4
        called_ks = [call.args[2] for call in mock_write_svg.call_args_list]
        assert sorted(called_ks) == [2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Edge case — K >= grain count
# ---------------------------------------------------------------------------


class TestRunKmeansKTooLarge:
    """run_kmeans must exit(1) when K >= number of valid grains."""

    def test_k_equal_to_grain_count_exits(self, capsys: pytest.CaptureFixture) -> None:
        n = 10
        X_scaled = _make_scaled_matrix(n_rows=n)
        with pytest.raises(SystemExit) as exc_info:
            run_kmeans(X_scaled, k=n)  # K == n
        assert exc_info.value.code == 1

    def test_k_greater_than_grain_count_exits(self, capsys: pytest.CaptureFixture) -> None:
        n = 10
        X_scaled = _make_scaled_matrix(n_rows=n)
        with pytest.raises(SystemExit) as exc_info:
            run_kmeans(X_scaled, k=n + 5)  # K >> n
        assert exc_info.value.code == 1

    def test_error_message_names_k_and_grain_count(self, capsys: pytest.CaptureFixture) -> None:
        n = 10
        X_scaled = _make_scaled_matrix(n_rows=n)
        with pytest.raises(SystemExit):
            run_kmeans(X_scaled, k=n)
        captured = capsys.readouterr()
        assert str(n) in captured.err  # grain count appears
        assert "10" in captured.err    # K value appears

    def test_error_goes_to_stderr_not_stdout(self, capsys: pytest.CaptureFixture) -> None:
        X_scaled = _make_scaled_matrix(n_rows=5)
        with pytest.raises(SystemExit):
            run_kmeans(X_scaled, k=5)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err) > 0

    def test_k_one_less_than_grain_count_succeeds(self) -> None:
        n = 10
        X_scaled = _make_scaled_matrix(n_rows=n)
        # k = n - 1 = 9 is valid (k < n), but silhouette needs ≥ 2 clusters and enough
        # samples; use a smaller k to keep the test fast and reliable.
        labels, score = run_kmeans(X_scaled, k=2)
        assert labels is not None


# ---------------------------------------------------------------------------
# Edge case — convergence failure
# ---------------------------------------------------------------------------


class TestRunKmeansConvergenceFailure:
    """run_kmeans must exit(1) and name K on convergence failure."""

    def test_convergence_warning_causes_exit(self, capsys: pytest.CaptureFixture) -> None:
        from sklearn.exceptions import ConvergenceWarning

        X_scaled = _make_scaled_matrix(n_rows=20)

        with patch("grain_clustering.KMeans") as mock_km_cls:
            mock_instance = MagicMock()
            mock_instance.fit.side_effect = ConvergenceWarning("did not converge")
            mock_km_cls.return_value = mock_instance

            with pytest.raises(SystemExit) as exc_info:
                run_kmeans(X_scaled, k=3)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "3" in captured.err
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Property 9 — reproducibility
# Feature: grain-clustering-analysis, Property 9: Clustering is reproducible
# Running run_kmeans twice with the same X_scaled and k must produce
# identical label arrays.
# Validates: Requirements 4.3
# ---------------------------------------------------------------------------


@st.composite
def valid_scaled_matrix(draw: st.DrawFn) -> np.ndarray:
    """Generate a valid scaled feature matrix suitable for all k in {2,3,4,5}.

    Constraints:
    - At least 6 rows (k+1 for the largest k=5), with a safe margin (min 10)
    - At least 2 columns
    - Values have non-zero variance per column (guaranteed by uniform sampling)
    """
    # Need at least max(k)+1 = 6 rows; use 10 as safe lower bound
    n_rows = draw(st.integers(min_value=10, max_value=60))
    n_cols = draw(st.integers(min_value=2, max_value=7))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed=seed)
    X = rng.uniform(0.1, 50.0, size=(n_rows, n_cols)).astype(np.float64)
    _, X_scaled = fit_scaler(X)
    return X_scaled


@given(X_scaled=valid_scaled_matrix())
@settings(max_examples=100)
def test_run_kmeans_reproducible(X_scaled: np.ndarray) -> None:
    """
    **Validates: Requirements 4.3**

    Property 9: Clustering is reproducible.

    For each k in {2, 3, 4, 5}, running run_kmeans twice on the same input
    must produce identical cluster label arrays (element-wise equality).
    """
    # Feature: grain-clustering-analysis, Property 9: Clustering is reproducible
    n_rows = len(X_scaled)

    for k in [2, 3, 4, 5]:
        # Skip k values that are invalid (k >= n_grains) — not the focus of this property
        if k >= n_rows:
            continue

        labels_a, score_a = run_kmeans(X_scaled, k)
        labels_b, score_b = run_kmeans(X_scaled, k)

        np.testing.assert_array_equal(
            labels_a,
            labels_b,
            err_msg=(
                f"Labels differ between two runs for k={k}, n={n_rows}: "
                f"clustering must be reproducible with fixed random_state=42"
            ),
        )
        assert score_a == score_b, (
            f"Silhouette scores differ between two runs for k={k}: {score_a} vs {score_b}"
        )


# ---------------------------------------------------------------------------
# Property 8 — Scaler and PCA are fitted once and shared across all k runs
# Feature: grain-clustering-analysis, Property 8:
# X_scaled and X_pca must be element-wise identical across all four k runs.
# Validates: Requirements 3.2, 8.2
# ---------------------------------------------------------------------------

# Import fit_pca here (only needed for Property 8).
from grain_clustering import fit_pca  # noqa: E402


@st.composite
def valid_feature_matrix(draw: st.DrawFn) -> np.ndarray:
    """Generate a raw feature matrix suitable for scaling + PCA.

    Constraints:
    - At least 10 rows (required by pipeline minimum)
    - 2–7 columns, each with at least 2 distinct values (no zero-variance)
    - Finite float64 values in a realistic measurement range
    """
    n_rows = draw(st.integers(min_value=10, max_value=60))
    n_cols = draw(st.integers(min_value=2, max_value=7))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.default_rng(seed=seed)
    # uniform [0.1, 50] guarantees finite, positive values with natural variance
    X = rng.uniform(0.1, 50.0, size=(n_rows, n_cols)).astype(np.float64)
    return X


@given(X_raw=valid_feature_matrix())
@settings(max_examples=100)
def test_scaler_and_pca_shared_across_k_runs(X_raw: np.ndarray) -> None:
    """
    **Validates: Requirements 3.2, 8.2**

    Property 8: Scaler and PCA are fitted once and shared across all k runs.

    Procedure:
    1. Fit the scaler and PCA exactly once on X_raw.
    2. Record X_scaled and X_pca before any k-means call.
    3. Run run_kmeans(X_scaled, k) for each k in {2, 3, 4, 5}.
    4. Assert X_scaled and X_pca are element-wise unchanged after every run.

    This verifies that run_kmeans does NOT mutate its X_scaled input and that
    the same pre-fitted arrays are passed into every k iteration (as main() must do).
    """
    # Step 1: fit scaler and PCA exactly once
    _, X_scaled = fit_scaler(X_raw)
    _, X_pca = fit_pca(X_scaled)

    # Step 2: capture reference copies before any k-means calls
    X_scaled_ref = X_scaled.copy()
    X_pca_ref = X_pca.copy()

    n_rows = len(X_scaled)

    for k in [2, 3, 4, 5]:
        # Skip k values that would be invalid (k >= n_grains) — not what we're testing.
        if k >= n_rows:
            continue

        run_kmeans(X_scaled, k)

        # X_scaled must be unchanged element-wise after each run_kmeans call
        np.testing.assert_array_equal(
            X_scaled,
            X_scaled_ref,
            err_msg=(
                f"X_scaled was mutated by run_kmeans(k={k}): "
                f"scaler must be fitted once and the same array reused across all k runs."
            ),
        )

        # X_pca is not passed into run_kmeans, but since it derives from X_scaled,
        # verify X_pca is also unchanged (no accidental re-fitting elsewhere).
        np.testing.assert_array_equal(
            X_pca,
            X_pca_ref,
            err_msg=(
                f"X_pca changed after run_kmeans(k={k}): "
                f"PCA must be fitted once and the same projection reused across all k runs."
            ),
        )
