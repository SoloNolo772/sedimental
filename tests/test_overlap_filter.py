"""
Tests for the OverlapGrainFilter (partially-covered grain removal).

The filter takes a labeled segmentation mask and, using shape-based
heuristics (solidity + normalized convexity defects), removes grains
that appear to be occluded by a neighbor.
"""

from __future__ import annotations

import numpy as np
import pytest

from sedimental.overlap_filter import (
    OverlapFilterResult,
    OverlapGrainFilter,
    OverlapPairRecord,
)


# ---------------------------------------------------------------------------
# Mask fixtures
# ---------------------------------------------------------------------------


def _disk(cy: int, cx: int, radius: int, shape=(80, 80)) -> np.ndarray:
    """Return a boolean disk mask."""
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= radius ** 2


def _disk_with_bite(
    cy: int,
    cx: int,
    radius: int,
    bite_cy: int,
    bite_cx: int,
    bite_radius: int,
    shape=(80, 80),
) -> np.ndarray:
    """Return a boolean disk with a large circular bite removed."""
    disk = _disk(cy, cx, radius, shape=shape)
    bite = _disk(bite_cy, bite_cx, bite_radius, shape=shape)
    return disk & ~bite


def _two_touching_disks_mask() -> np.ndarray:
    """Two convex disks side-by-side, touching each other."""
    mask = np.zeros((80, 80), dtype=np.int32)
    mask[_disk(40, 25, 12)] = 1
    mask[_disk(40, 50, 12)] = 2
    return mask


def _convex_touching_bitten_mask() -> np.ndarray:
    """A convex disk (id=1) touching a bitten disk (id=2).

    Grain 1 is drawn as a full convex disk. Grain 2 is what remains of a
    second disk after grain 1 occludes it — i.e. a crescent whose
    concave arc faces grain 1. The two labels share a boundary (grain
    1's outer arc coincides with grain 2's inner arc), which is what
    the dilation-based contact detector picks up.
    """
    shape = (80, 80)
    disk1 = _disk(40, 30, 15, shape=shape)  # convex "occluder"
    disk2 = _disk(40, 50, 15, shape=shape)  # underlying grain
    crescent = disk2 & ~disk1  # visible portion of the underlying grain

    mask = np.zeros(shape, dtype=np.int32)
    mask[disk1] = 1
    mask[crescent] = 2
    return mask


def _isolated_disks_mask() -> np.ndarray:
    """Two convex disks with plenty of gap between them (no contact)."""
    mask = np.zeros((80, 80), dtype=np.int32)
    mask[_disk(20, 20, 8)] = 1
    mask[_disk(60, 60, 8)] = 2
    return mask


# ---------------------------------------------------------------------------
# Basic behavior
# ---------------------------------------------------------------------------


class TestFilterBasics:
    """Sanity tests that don't depend on the removal heuristic."""

    def test_empty_mask_returns_empty_result(self):
        mask = np.zeros((20, 20), dtype=np.int32)
        result = OverlapGrainFilter().filter(mask)

        assert isinstance(result, OverlapFilterResult)
        assert result.original_grain_count == 0
        assert result.removed_ids == []
        assert result.pair_records == []
        np.testing.assert_array_equal(result.filtered_mask, mask)

    def test_single_grain_never_removed(self):
        mask = np.zeros((60, 60), dtype=np.int32)
        mask[_disk(30, 30, 10, shape=(60, 60))] = 7  # non-contiguous label id on purpose

        result = OverlapGrainFilter().filter(mask)

        assert result.original_grain_count == 1
        assert result.removed_ids == []
        assert result.pair_records == []
        np.testing.assert_array_equal(result.filtered_mask, mask)

    def test_isolated_grains_produce_no_pairs(self):
        mask = _isolated_disks_mask()
        result = OverlapGrainFilter().filter(mask)

        assert result.original_grain_count == 2
        assert result.pair_records == []
        assert result.removed_ids == []
        np.testing.assert_array_equal(result.filtered_mask, mask)

    def test_two_convex_disks_touching_no_removal(self):
        """Touching but both convex: nothing should be removed."""
        mask = _two_touching_disks_mask()
        result = OverlapGrainFilter().filter(mask)

        assert result.original_grain_count == 2
        # A pair is detected because they touch,
        assert len(result.pair_records) == 1
        # ... but neither has enough concavity/solidity gap to be removed.
        assert result.removed_ids == []

    def test_non_2d_mask_raises(self):
        with pytest.raises(ValueError):
            OverlapGrainFilter().filter(np.zeros((4, 4, 4), dtype=np.int32))

    def test_labels_are_preserved_for_surviving_grains(self):
        """Surviving grain labels must appear unchanged in filtered_mask."""
        mask = _convex_touching_bitten_mask()
        result = OverlapGrainFilter().filter(mask)

        surviving = set(np.unique(result.filtered_mask)) - {0}
        original = set(np.unique(mask)) - {0}
        # No relabeling — surviving grains keep their original IDs.
        assert surviving.issubset(original)
        # Removed grain IDs must not appear in filtered_mask.
        for gid in result.removed_ids:
            assert gid not in surviving


# ---------------------------------------------------------------------------
# Heuristic behavior
# ---------------------------------------------------------------------------


class TestFilterHeuristic:
    """Tests for the shape-based removal decision."""

    def test_bitten_grain_next_to_convex_gets_removed(self):
        """A concave, low-solidity grain touching a convex one is removed."""
        mask = _convex_touching_bitten_mask()
        result = OverlapGrainFilter().filter(mask)

        # Grain 2 is the one with the "bite" — it should be flagged.
        assert 2 in result.removed_ids
        assert 1 not in result.removed_ids
        # The filtered mask must have zeroed out grain 2's pixels.
        assert not np.any(result.filtered_mask == 2)
        # And left grain 1 intact.
        assert np.count_nonzero(result.filtered_mask == 1) == np.count_nonzero(mask == 1)

    def test_pair_record_reason_populated_when_grain_removed(self):
        mask = _convex_touching_bitten_mask()
        result = OverlapGrainFilter().filter(mask)

        record = next(
            r for r in result.pair_records if r.removed_grain is not None
        )
        assert record.reason  # non-empty reason string
        assert record.removed_grain in {record.grain_a, record.grain_b}

    def test_pair_records_include_all_touching_pairs(self):
        """Every touching pair should have exactly one record."""
        mask = _convex_touching_bitten_mask()
        result = OverlapGrainFilter().filter(mask)

        # Only one touching pair in this fixture (grains 1 & 2).
        assert len(result.pair_records) == 1

    def test_high_min_votes_prevents_removal(self):
        """Setting min_votes above what the tests can produce disables removal."""
        mask = _convex_touching_bitten_mask()
        # Only 3 tests exist — requiring 4 votes makes removal impossible.
        result = OverlapGrainFilter(min_votes=4).filter(mask)

        assert result.removed_ids == []
        # The mask must be unchanged.
        np.testing.assert_array_equal(result.filtered_mask, mask)

    def test_extreme_solidity_gap_prevents_solidity_vote(self):
        """A very high solidity_gap suppresses the solidity vote."""
        mask = _convex_touching_bitten_mask()
        result = OverlapGrainFilter(solidity_gap=0.99).filter(mask)

        # We still expect removal because both concavity votes may fire,
        # but the solidity vote should not be in the "reason" string.
        for record in result.pair_records:
            if record.removed_grain is not None:
                assert "lower solidity" not in record.reason


# ---------------------------------------------------------------------------
# Removed-id set semantics
# ---------------------------------------------------------------------------


class TestRemovedIdSet:
    def test_removed_ids_are_sorted_and_unique(self):
        """Same grain removed on multiple pairs appears once, sorted."""
        # Center grain (id 2) is a lens carved by two convex occluders
        # (ids 1 and 3) on either side. Grain 2 loses both pairs; the
        # dedupe logic must list its id only once.
        shape = (80, 100)
        disk_left = _disk(40, 30, 18, shape=shape)
        disk_center = _disk(40, 50, 18, shape=shape)
        disk_right = _disk(40, 70, 18, shape=shape)

        # Grain 2 = visible portion of the center disk after both
        # neighbors occlude it. Because the two occluders overlap the
        # center disk on opposite sides, what remains is a thin,
        # heavily-concave lens.
        grain_2 = disk_center & ~disk_left & ~disk_right

        mask = np.zeros(shape, dtype=np.int32)
        mask[disk_left] = 1
        mask[disk_right] = 3
        mask[grain_2] = 2

        result = OverlapGrainFilter().filter(mask)

        # Grain 2 should be flagged (and listed only once).
        assert 2 in result.removed_ids
        assert result.removed_ids == sorted(result.removed_ids)
        assert result.removed_ids.count(2) == 1


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"contact_distance": -1},
            {"concavity_threshold": -0.01},
            {"relative_concavity_ratio": 0},
            {"solidity_gap": -0.01},
            {"min_votes": 0},
        ],
    )
    def test_invalid_params_raise(self, kwargs):
        with pytest.raises(ValueError):
            OverlapGrainFilter(**kwargs)


# ---------------------------------------------------------------------------
# Analysis CSV writer
# ---------------------------------------------------------------------------


class TestOverlapAnalysisCsv:
    def test_write_overlap_analysis_csv_writes_all_columns(self, tmp_path):
        from sedimental.csv_writer import (
            OVERLAP_ANALYSIS_COLUMNS,
            write_overlap_analysis_csv,
        )

        records = [
            OverlapPairRecord(
                grain_a=1, grain_b=2,
                concavity_a=0.02, concavity_b=0.15,
                solidity_a=0.98, solidity_b=0.82,
                votes_a=0, votes_b=3,
                removed_grain=2,
                reason="strong global concavity; more concave than neighboring grain; lower solidity",
            )
        ]
        out = tmp_path / "analysis.csv"
        write_overlap_analysis_csv(records, out)

        text = out.read_text(encoding="utf-8")
        # Header contains every documented column.
        header = text.splitlines()[0]
        for col in OVERLAP_ANALYSIS_COLUMNS:
            assert col in header
        # Row contains the removed grain id.
        assert ",2," in text or text.rstrip().endswith(",2")

    def test_write_overlap_analysis_csv_creates_parent_dirs(self, tmp_path):
        from sedimental.csv_writer import write_overlap_analysis_csv

        out = tmp_path / "nested" / "dir" / "analysis.csv"
        write_overlap_analysis_csv([], out)
        assert out.exists()

    def test_write_overlap_analysis_csv_empty_records_writes_header_only(self, tmp_path):
        from sedimental.csv_writer import write_overlap_analysis_csv

        out = tmp_path / "analysis.csv"
        write_overlap_analysis_csv([], out)
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1  # header only
