"""
Tests for grain_clustering.select_recommended_k and print_silhouette_table.

Covers:
  - Property 11: Recommended k is the highest-silhouette k, ties broken by smallest k
    (Feature: grain-clustering-analysis, Property 11)
    Validates: Requirements 5.2, 7.4
  - Unit tests for print_silhouette_table stdout output
    Validates: Requirements 5.3
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Make the analysis package importable from inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "analysis"))

from grain_clustering import print_silhouette_table, select_recommended_k  # noqa: E402


# ---------------------------------------------------------------------------
# Strategy: generate a mapping of k ∈ {2, 3, 4, 5} → silhouette score
# ---------------------------------------------------------------------------

# Silhouette scores are in [-1, 1]; allow_nan=False, allow_infinity=False is safe.
_silhouette_score = st.floats(
    min_value=-1.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

_score_mapping = st.fixed_dictionaries(
    {
        2: _silhouette_score,
        3: _silhouette_score,
        4: _silhouette_score,
        5: _silhouette_score,
    }
)


# ---------------------------------------------------------------------------
# Property 11 — Recommended k is the highest-silhouette k, ties broken by smallest k
# Feature: grain-clustering-analysis, Property 11: Recommended k is the highest-silhouette k,
# ties broken by smallest k
# Validates: Requirements 5.2, 7.4
# ---------------------------------------------------------------------------


def _expected_recommended_k(scores: dict[int, float]) -> int:
    """Independently compute the expected recommended k.

    Rules (must NOT call select_recommended_k):
      1. Round each score to 4 decimal places.
      2. Find the maximum rounded score.
      3. Collect all k values whose rounded score equals the maximum.
      4. Return the smallest such k (tie-breaking rule).
    """
    rounded = {k: round(s, 4) for k, s in scores.items()}
    best = max(rounded.values())
    candidates = [k for k, s in rounded.items() if s == best]
    return min(candidates)


@given(scores=_score_mapping)
@settings(max_examples=100)
def test_select_recommended_k_highest_silhouette_ties_broken_by_smallest_k(
    scores: dict[int, float],
) -> None:
    """
    **Validates: Requirements 5.2, 7.4**

    Property 11: Recommended k is the highest-silhouette k, ties broken by smallest k.

    For any mapping of k ∈ {2, 3, 4, 5} to silhouette scores,
    select_recommended_k must return the k with the strictly greatest score
    when rounded to four decimal places; when two or more k values share the
    highest rounded score, it must return the smallest such k.
    """
    # Feature: grain-clustering-analysis, Property 11: Recommended k is the highest-silhouette k, ties broken by smallest k
    result = select_recommended_k(scores)
    expected = _expected_recommended_k(scores)

    assert result == expected, (
        f"select_recommended_k({scores!r}) returned {result!r}, "
        f"expected {expected!r}. "
        f"Rounded scores: { {k: round(s, 4) for k, s in scores.items()} }"
    )


# ---------------------------------------------------------------------------
# Unit tests for print_silhouette_table — stdout summary table
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------


class TestPrintSilhouetteTable:
    """Unit tests for the stdout silhouette summary table (Requirement 5.3)."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _capture(scores: dict[int, float], recommended_k: int, capsys: pytest.CaptureFixture) -> str:
        """Call print_silhouette_table and return the captured stdout."""
        print_silhouette_table(scores, recommended_k)
        return capsys.readouterr().out

    # ------------------------------------------------------------------
    # All four K values appear in the output
    # ------------------------------------------------------------------

    def test_all_k_values_present(self, capsys: pytest.CaptureFixture) -> None:
        """The table must list each K in {2, 3, 4, 5}."""
        scores = {2: 0.42135, 3: 0.58174, 4: 0.49010, 5: 0.41001}
        out = self._capture(scores, recommended_k=3, capsys=capsys)
        for k in [2, 3, 4, 5]:
            assert str(k) in out, f"K={k} not found in stdout output"

    # ------------------------------------------------------------------
    # Score formatting: 4 decimal places
    # ------------------------------------------------------------------

    def test_scores_rounded_to_4dp(self, capsys: pytest.CaptureFixture) -> None:
        """Each score must appear formatted to exactly 4 decimal places."""
        scores = {2: 0.42135, 3: 0.58174, 4: 0.49010, 5: 0.41001}
        out = self._capture(scores, recommended_k=3, capsys=capsys)
        # Check each expected formatted string is present.
        assert "0.4214" in out, "Score for K=2 not rounded/formatted correctly"
        assert "0.5817" in out, "Score for K=3 not rounded/formatted correctly"
        assert "0.4901" in out, "Score for K=4 not rounded/formatted correctly"
        assert "0.4100" in out, "Score for K=5 not rounded/formatted correctly"

    def test_score_with_trailing_zeros_shown_to_4dp(self, capsys: pytest.CaptureFixture) -> None:
        """Scores with trailing zeros after rounding must still show 4 decimal places."""
        scores = {2: 0.5000, 3: 0.3000, 4: 0.1000, 5: 0.2000}
        out = self._capture(scores, recommended_k=2, capsys=capsys)
        assert "0.5000" in out, "Trailing zeros must be preserved to 4 dp"
        assert "0.3000" in out
        assert "0.1000" in out
        assert "0.2000" in out

    def test_negative_score_shown_to_4dp(self, capsys: pytest.CaptureFixture) -> None:
        """Negative silhouette scores must be formatted correctly to 4 dp."""
        scores = {2: -0.12345, 3: 0.1, 4: 0.2, 5: 0.3}
        out = self._capture(scores, recommended_k=5, capsys=capsys)
        assert "-0.1235" in out, "Negative score not rounded/formatted correctly"

    # ------------------------------------------------------------------
    # Recommended K marker: `*` in its own column
    # ------------------------------------------------------------------

    def test_recommended_k_row_has_star_marker(self, capsys: pytest.CaptureFixture) -> None:
        """The recommended K row must contain a `*` marker."""
        scores = {2: 0.4, 3: 0.6, 4: 0.5, 5: 0.45}
        out = self._capture(scores, recommended_k=3, capsys=capsys)
        lines = out.strip().splitlines()
        # Find the line that contains K=3
        k3_lines = [ln for ln in lines if ln.strip().startswith("3")]
        assert k3_lines, "No line starting with '3' found in output"
        assert "*" in k3_lines[0], "Recommended K=3 row must have a `*` marker"

    def test_non_recommended_k_rows_have_no_star(self, capsys: pytest.CaptureFixture) -> None:
        """Rows for non-recommended K values must NOT contain a `*` marker."""
        scores = {2: 0.4, 3: 0.6, 4: 0.5, 5: 0.45}
        out = self._capture(scores, recommended_k=3, capsys=capsys)
        lines = out.strip().splitlines()
        for k in [2, 4, 5]:
            k_lines = [ln for ln in lines if ln.strip().startswith(str(k))]
            assert k_lines, f"No line starting with '{k}' found in output"
            assert "*" not in k_lines[0], (
                f"Non-recommended K={k} row must NOT have a `*` marker"
            )

    def test_exactly_one_star_marker_in_output(self, capsys: pytest.CaptureFixture) -> None:
        """Exactly one `*` marker must appear across all data rows."""
        scores = {2: 0.4, 3: 0.6, 4: 0.5, 5: 0.45}
        out = self._capture(scores, recommended_k=3, capsys=capsys)
        lines = out.strip().splitlines()
        # Exclude header line(s) — count stars only in data rows (lines starting with a digit)
        data_lines = [ln for ln in lines if ln and ln.strip()[0].isdigit()]
        star_count = sum(1 for ln in data_lines if "*" in ln)
        assert star_count == 1, f"Expected exactly 1 `*` marker, found {star_count}"

    # ------------------------------------------------------------------
    # Star on different recommended K values (parametrised)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("recommended_k", [2, 3, 4, 5])
    def test_star_on_correct_k_for_each_possible_recommended_k(
        self, recommended_k: int, capsys: pytest.CaptureFixture
    ) -> None:
        """The `*` must appear on whichever K is recommended."""
        scores = {2: 0.3, 3: 0.4, 4: 0.5, 5: 0.35}
        out = self._capture(scores, recommended_k=recommended_k, capsys=capsys)
        lines = out.strip().splitlines()
        # The line for recommended_k must have *.
        rec_lines = [ln for ln in lines if ln.strip().startswith(str(recommended_k))]
        assert rec_lines, f"No line found for K={recommended_k}"
        assert "*" in rec_lines[0], f"No `*` on K={recommended_k} row"
        # All other K lines must NOT have *.
        for other_k in [2, 3, 4, 5]:
            if other_k == recommended_k:
                continue
            other_lines = [ln for ln in lines if ln.strip().startswith(str(other_k))]
            if other_lines:
                assert "*" not in other_lines[0], (
                    f"`*` found on non-recommended K={other_k} row"
                )

    # ------------------------------------------------------------------
    # Output goes to stdout, not stderr
    # ------------------------------------------------------------------

    def test_output_goes_to_stdout_not_stderr(self, capsys: pytest.CaptureFixture) -> None:
        """print_silhouette_table must write to stdout, not stderr."""
        scores = {2: 0.4, 3: 0.6, 4: 0.5, 5: 0.45}
        print_silhouette_table(scores, recommended_k=3)
        captured = capsys.readouterr()
        assert len(captured.out) > 0, "stdout must have content"
        assert captured.err == "", "stderr must be empty"

    # ------------------------------------------------------------------
    # K values appear in ascending order
    # ------------------------------------------------------------------

    def test_k_values_appear_in_ascending_order(self, capsys: pytest.CaptureFixture) -> None:
        """K values must be listed in ascending order (2, 3, 4, 5)."""
        # Supply scores in non-ascending order to ensure sorting is applied.
        scores = {5: 0.41, 4: 0.49, 3: 0.58, 2: 0.42}
        out = self._capture(scores, recommended_k=3, capsys=capsys)
        lines = out.strip().splitlines()
        data_lines = [ln for ln in lines if ln and ln.strip()[0].isdigit()]
        assert len(data_lines) == 4, "Expected 4 data rows"
        k_values = [int(ln.strip().split()[0]) for ln in data_lines]
        assert k_values == [2, 3, 4, 5], f"K values not in ascending order: {k_values}"

    # ------------------------------------------------------------------
    # Integration: select_recommended_k + print_silhouette_table agree
    # ------------------------------------------------------------------

    def test_star_matches_select_recommended_k(self, capsys: pytest.CaptureFixture) -> None:
        """The `*` marker must be on the same K that select_recommended_k returns."""
        scores = {2: 0.42135, 3: 0.58174, 4: 0.49010, 5: 0.41001}
        rec_k = select_recommended_k(scores)
        out = self._capture(scores, recommended_k=rec_k, capsys=capsys)
        lines = out.strip().splitlines()
        rec_lines = [ln for ln in lines if ln.strip().startswith(str(rec_k))]
        assert rec_lines, f"No line for recommended K={rec_k}"
        assert "*" in rec_lines[0], f"`*` missing from recommended K={rec_k} row"
