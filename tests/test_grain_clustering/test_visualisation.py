"""
Tests for grain_clustering visualisation functions.

Covers:
  - Property 13: Scatter SVG legend has exactly K entries
    (Feature: grain-clustering-analysis, Property 13)
    Validates: Requirements 8.4
  - Property 14: Scatter SVG title matches format string
    (Feature: grain-clustering-analysis, Property 14)
    Validates: Requirements 8.5
  - Property 15: Silhouette bar chart y-axis is always fixed at [-1, 1]
    (Feature: grain-clustering-analysis, Property 15)
    Validates: Requirements 9.1
  - Property 16: Bar annotations match scores rounded to 4 decimal places
    (Feature: grain-clustering-analysis, Property 16)
    Validates: Requirements 9.2
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis import HealthCheck

# Make the analysis package importable from inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from grain_clustering import write_scatter_svg, write_silhouette_svg  # noqa: E402


# ---------------------------------------------------------------------------
# Property 13 — Scatter SVG legend has exactly K entries
# Feature: grain-clustering-analysis, Property 13: Scatter SVG legend has exactly K entries
# Validates: Requirements 8.4
# ---------------------------------------------------------------------------


@given(k=st.integers(min_value=2, max_value=5))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_scatter_svg_legend_has_exactly_k_entries(k: int) -> None:
    """
    **Validates: Requirements 8.4**

    # Feature: grain-clustering-analysis, Property 13: Scatter SVG legend has exactly K entries

    For each k ∈ {2, 3, 4, 5}, the matplotlib figure produced by write_scatter_svg
    must contain a legend with exactly k handles — one per cluster label in [0, k-1].
    """
    rng = np.random.default_rng(seed=k * 17)
    n = k + 20  # always > k, guarantees all k clusters can be represented

    X_pca = rng.uniform(-10.0, 10.0, size=(n, 2)).astype(np.float64)

    # Ensure all labels 0..k-1 appear at least once
    labels = np.empty(n, dtype=int)
    labels[:k] = np.arange(k)
    labels[k:] = rng.integers(0, k, size=n - k)
    rng.shuffle(labels)

    silhouette = 0.5  # arbitrary valid silhouette score
    input_stem = "test_grains"

    # Use a real temporary directory (context manager avoids function-scoped fixture
    # conflict with Hypothesis health checks)
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)

        # Capture the figure before write_scatter_svg closes it via monkey-patching.
        captured_fig: list = []
        original_savefig = plt.Figure.savefig

        def _capture_savefig(self, *args, **kwargs):
            captured_fig.append(self)
            original_savefig(self, *args, **kwargs)

        plt.Figure.savefig = _capture_savefig
        try:
            write_scatter_svg(X_pca, labels, k, silhouette, output_dir, input_stem)
        finally:
            plt.Figure.savefig = original_savefig

    assert len(captured_fig) == 1, "write_scatter_svg must produce exactly one figure"
    fig = captured_fig[0]

    # Retrieve legend handles from the figure's axes
    assert len(fig.axes) >= 1, "figure must have at least one axes"
    ax = fig.axes[0]
    assert ax.get_legend() is not None, f"axes must have a legend for k={k}"

    handles, _ = ax.get_legend_handles_labels()
    assert len(handles) == k, (
        f"Expected legend to have exactly {k} entries for k={k}, "
        f"but found {len(handles)}"
    )

    plt.close("all")


# ---------------------------------------------------------------------------
# Property 14 — Scatter SVG title matches format string
# Feature: grain-clustering-analysis, Property 14: Scatter SVG title matches format string
# Validates: Requirements 8.5
# ---------------------------------------------------------------------------


@given(
    k=st.integers(min_value=2, max_value=5),
    score=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_scatter_svg_title_matches_format_string(k: int, score: float) -> None:
    """
    **Validates: Requirements 8.5**

    # Feature: grain-clustering-analysis, Property 14: Scatter SVG title matches format string

    For any k value and silhouette score, the title of the scatter SVG figure must
    equal the string f"k={k} | Silhouette: {score:.4f}".
    """
    rng = np.random.default_rng(seed=k * 31)
    n = k + 20  # always > k, guarantees all k clusters can be represented

    X_pca = rng.uniform(-10.0, 10.0, size=(n, 2)).astype(np.float64)

    # Ensure all labels 0..k-1 appear at least once
    labels = np.empty(n, dtype=int)
    labels[:k] = np.arange(k)
    labels[k:] = rng.integers(0, k, size=n - k)
    rng.shuffle(labels)

    input_stem = "test_grains"
    expected_title = f"k={k} | Silhouette: {score:.4f}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)

        # Capture the figure before write_scatter_svg closes it via monkey-patching.
        captured_fig: list = []
        original_savefig = plt.Figure.savefig

        def _capture_savefig(self, *args, **kwargs):
            captured_fig.append(self)
            original_savefig(self, *args, **kwargs)

        plt.Figure.savefig = _capture_savefig
        try:
            write_scatter_svg(X_pca, labels, k, score, output_dir, input_stem)
        finally:
            plt.Figure.savefig = original_savefig

    assert len(captured_fig) == 1, "write_scatter_svg must produce exactly one figure"
    fig = captured_fig[0]

    assert len(fig.axes) >= 1, "figure must have at least one axes"
    ax = fig.axes[0]
    actual_title = ax.get_title()

    assert actual_title == expected_title, (
        f"Expected title {expected_title!r} but got {actual_title!r} "
        f"for k={k}, score={score}"
    )

    plt.close("all")


# ---------------------------------------------------------------------------
# Unit tests — axis labels (Requirement 8.6) and SVG write failure (Requirement 8.8)
# ---------------------------------------------------------------------------


def _make_scatter_inputs(k: int = 3, n: int = 30, seed: int = 0):
    """Return (X_pca, labels) suitable for write_scatter_svg."""
    rng = np.random.default_rng(seed=seed)
    X_pca = rng.uniform(-10.0, 10.0, size=(n, 2)).astype(np.float64)
    labels = np.empty(n, dtype=int)
    labels[:k] = np.arange(k)          # guarantee every cluster is represented
    labels[k:] = rng.integers(0, k, size=n - k)
    rng.shuffle(labels)
    return X_pca, labels


def test_scatter_svg_axis_labels(tmp_path: Path) -> None:
    """
    Validates: Requirements 8.6

    write_scatter_svg must label the x-axis "PC1" and the y-axis "PC2".
    """
    k = 3
    X_pca, labels = _make_scatter_inputs(k=k)

    captured_fig: list = []
    original_savefig = plt.Figure.savefig

    def _capture(self, *args, **kwargs):
        captured_fig.append(self)
        original_savefig(self, *args, **kwargs)

    plt.Figure.savefig = _capture
    try:
        write_scatter_svg(X_pca, labels, k, 0.42, tmp_path, "grains")
    finally:
        plt.Figure.savefig = original_savefig

    assert len(captured_fig) == 1, "write_scatter_svg must produce exactly one figure"
    ax = captured_fig[0].axes[0]

    assert ax.get_xlabel() == "PC1", (
        f"Expected x-axis label 'PC1' but got {ax.get_xlabel()!r}"
    )
    assert ax.get_ylabel() == "PC2", (
        f"Expected y-axis label 'PC2' but got {ax.get_ylabel()!r}"
    )

    plt.close("all")


def test_scatter_svg_write_failure(tmp_path: Path, capsys) -> None:
    """
    Validates: Requirements 8.8

    When writing the SVG file fails (OSError from savefig), write_scatter_svg
    must print a descriptive error message to stderr and exit with code 1.
    """
    from unittest.mock import patch

    k = 2
    X_pca, labels = _make_scatter_inputs(k=k)

    with patch("matplotlib.figure.Figure.savefig", side_effect=OSError("disk full")):
        with pytest.raises(SystemExit) as exc_info:
            write_scatter_svg(X_pca, labels, k, 0.35, tmp_path, "grains")

    assert exc_info.value.code == 1, (
        f"Expected exit code 1 on SVG write failure, got {exc_info.value.code}"
    )

    captured = capsys.readouterr()
    assert captured.err, "Expected a descriptive error message on stderr"
    assert "error" in captured.err.lower() or "Error" in captured.err, (
        f"Expected 'error' in stderr message, got: {captured.err!r}"
    )

    plt.close("all")


# ---------------------------------------------------------------------------
# Property 15 — Silhouette bar chart y-axis is always fixed at [-1, 1]
# Feature: grain-clustering-analysis, Property 15: Silhouette bar chart y-axis is always fixed at [-1, 1]
# Validates: Requirements 9.1
# ---------------------------------------------------------------------------


@given(
    s2=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    s3=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    s4=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    s5=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    recommended_k=st.sampled_from([2, 3, 4, 5]),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property15_silhouette_bar_chart_ylim_fixed_at_minus1_to_1(
    s2: float, s3: float, s4: float, s5: float, recommended_k: int
) -> None:
    """
    **Validates: Requirements 9.1**

    # Feature: grain-clustering-analysis, Property 15: Silhouette bar chart y-axis is always fixed at [-1, 1]

    For any set of silhouette scores (for k=2,3,4,5), the y-axis limits of the
    silhouette summary bar chart produced by write_silhouette_svg must be exactly
    (-1.0, 1.0), regardless of the actual score values.
    """
    scores = {2: s2, 3: s3, 4: s4, 5: s5}

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)

        # Capture the figure before write_silhouette_svg closes it.
        captured_fig: list = []
        original_savefig = plt.Figure.savefig

        def _capture_savefig(self, *args, **kwargs):
            captured_fig.append(self)
            original_savefig(self, *args, **kwargs)

        plt.Figure.savefig = _capture_savefig
        try:
            write_silhouette_svg(scores, recommended_k, output_dir, "test")
        finally:
            plt.Figure.savefig = original_savefig
            plt.close("all")

    assert len(captured_fig) == 1, "write_silhouette_svg must produce exactly one figure"
    fig = captured_fig[0]

    assert len(fig.axes) >= 1, "figure must have at least one axes"
    ax = fig.axes[0]

    ylim = ax.get_ylim()
    assert ylim == (-1.0, 1.0), (
        f"Expected y-axis limits (-1.0, 1.0) but got {ylim} "
        f"for scores={scores}, recommended_k={recommended_k}"
    )


# ---------------------------------------------------------------------------
# Property 16 — Bar annotations match scores rounded to 4 decimal places
# Feature: grain-clustering-analysis, Property 16: Bar annotations match scores rounded to 4 dp
# Validates: Requirements 9.2
# ---------------------------------------------------------------------------


@given(
    s2=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    s3=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    s4=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    s5=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    recommended_k=st.sampled_from([2, 3, 4, 5]),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property16_bar_annotations_match_scores_rounded_to_4dp(
    s2: float, s3: float, s4: float, s5: float, recommended_k: int
) -> None:
    """
    **Validates: Requirements 9.2**

    # Feature: grain-clustering-analysis, Property 16: Bar annotations match scores rounded to 4 dp

    For any set of silhouette scores, each bar in the silhouette summary chart must
    be annotated with a text string equal to the score formatted to 4 decimal places
    (i.e., f"{round(score, 4):.4f}").
    """
    scores = {2: s2, 3: s3, 4: s4, 5: s5}

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)

        # Capture the figure before write_silhouette_svg closes it.
        captured_fig: list = []
        original_savefig = plt.Figure.savefig

        def _capture_savefig(self, *args, **kwargs):
            captured_fig.append(self)
            original_savefig(self, *args, **kwargs)

        plt.Figure.savefig = _capture_savefig
        try:
            write_silhouette_svg(scores, recommended_k, output_dir, "test")
        finally:
            plt.Figure.savefig = original_savefig
            plt.close("all")

    assert len(captured_fig) == 1, "write_silhouette_svg must produce exactly one figure"
    fig = captured_fig[0]

    assert len(fig.axes) >= 1, "figure must have at least one axes"
    ax = fig.axes[0]

    # Collect all Text annotations added by ax.text() (excludes axis labels and title).
    # Bar annotations are added as ax.texts; filter to those with non-empty strings.
    bar_annotation_texts = [t.get_text() for t in ax.texts if t.get_text().strip()]

    # We expect exactly one annotation per bar (4 bars for k ∈ {2, 3, 4, 5}).
    k_values = sorted(scores.keys())
    assert len(bar_annotation_texts) == len(k_values), (
        f"Expected {len(k_values)} bar annotations but found {len(bar_annotation_texts)}: "
        f"{bar_annotation_texts!r}"
    )

    # Each annotation must equal the score formatted to 4 decimal places.
    # Bars are rendered in ascending k order (sorted).
    for k, annotation in zip(k_values, bar_annotation_texts):
        expected = f"{round(scores[k], 4):.4f}"
        assert annotation == expected, (
            f"Bar annotation for k={k} is {annotation!r}, "
            f"expected {expected!r} (score={scores[k]})"
        )


# ---------------------------------------------------------------------------
# Unit tests — silhouette chart title (Requirement 9.3) and SVG write failure (Requirement 9.5)
# ---------------------------------------------------------------------------


def _make_silhouette_scores(recommended_k: int = 3) -> dict[int, float]:
    """Return a valid scores dict for write_silhouette_svg."""
    return {2: 0.32, 3: 0.51, 4: 0.45, 5: 0.38}


def test_silhouette_chart_title(tmp_path: Path) -> None:
    """
    Validates: Requirements 9.3

    write_silhouette_svg must set the axes title to "Silhouette Scores by k".
    """
    scores = _make_silhouette_scores()
    recommended_k = 3

    captured_fig: list = []
    original_savefig = plt.Figure.savefig

    def _capture(self, *args, **kwargs):
        captured_fig.append(self)
        original_savefig(self, *args, **kwargs)

    plt.Figure.savefig = _capture
    try:
        write_silhouette_svg(scores, recommended_k, tmp_path, "grains")
    finally:
        plt.Figure.savefig = original_savefig

    assert len(captured_fig) == 1, "write_silhouette_svg must produce exactly one figure"
    ax = captured_fig[0].axes[0]

    actual_title = ax.get_title()
    assert actual_title == "Silhouette Scores by k", (
        f"Expected title 'Silhouette Scores by k' but got {actual_title!r}"
    )

    plt.close("all")


def test_silhouette_svg_write_failure(tmp_path: Path, capsys) -> None:
    """
    Validates: Requirements 9.5

    When writing the silhouette SVG fails (OSError from savefig),
    write_silhouette_svg must print a descriptive error message to stderr
    and exit with code 1.
    """
    from unittest.mock import patch

    scores = _make_silhouette_scores()

    with patch("matplotlib.figure.Figure.savefig", side_effect=OSError("disk full")):
        with pytest.raises(SystemExit) as exc_info:
            write_silhouette_svg(scores, 3, tmp_path, "grains")

    assert exc_info.value.code == 1, (
        f"Expected exit code 1 on SVG write failure, got {exc_info.value.code}"
    )

    captured = capsys.readouterr()
    assert captured.err, "Expected a descriptive error message on stderr"
    assert "error" in captured.err.lower(), (
        f"Expected 'error' in stderr message, got: {captured.err!r}"
    )

    plt.close("all")
