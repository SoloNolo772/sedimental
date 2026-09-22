"""
Tests for the ProcessingOrchestrator integration with the overlap filter.

These tests mock the loader, segmentation, and measurement engines so
that only the wiring of ``remove_overlaps`` through the orchestrator is
under test. The overlap filter itself has its own unit tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from sedimental.models import (
    ImageResult,
    ProcessingResult,
    SampleMetadata,
    SegmentationResult,
)
from sedimental.orchestrator import ProcessingOrchestrator
from sedimental.overlap_filter import OverlapFilterResult, OverlapPairRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_measurement(grain_id: int = 1):
    from sedimental.models import GrainMeasurement, MeasurementUnit

    return GrainMeasurement(
        grain_id=grain_id,
        area=100.0,
        perimeter=40.0,
        circularity=0.785,
        roundness=0.9,
        feret_diameter=12.0,
        major_axis=11.0,
        minor_axis=9.0,
        unit=MeasurementUnit.PIXELS,
        scale_factor=None,
    )


def _make_orchestrator_with_mocks(seg_mask, meas_return=None):
    """Return an orchestrator with mocked loader/segmenter/measurer."""
    orch = ProcessingOrchestrator()

    orch._loader = MagicMock()
    orch._loader.load.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

    mock_seg = MagicMock()
    mock_seg.segment.return_value = SegmentationResult(
        mask=seg_mask, grain_count=int((np.unique(seg_mask) > 0).sum()), warnings=[]
    )
    orch._seg_engine = mock_seg

    mock_meas = MagicMock()
    mock_meas.measure.return_value = meas_return or [_fake_measurement(1)]
    orch._meas_engine = mock_meas

    return orch


def _mock_overlap_filter(removed_ids, filtered_mask, pair_records=None):
    mock_filter = MagicMock()
    mock_filter.filter.return_value = OverlapFilterResult(
        filtered_mask=filtered_mask,
        removed_ids=list(removed_ids),
        pair_records=pair_records or [],
        original_grain_count=int((np.unique(filtered_mask) > 0).sum())
        + len(removed_ids),
    )
    return mock_filter


# ---------------------------------------------------------------------------
# Default behavior (unchanged when flag is off)
# ---------------------------------------------------------------------------


class TestOverlapFilterOff:
    def test_default_does_not_invoke_overlap_filter(self, tmp_path):
        img = tmp_path / "sample.jpg"
        img.write_bytes(b"fake")

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1
        orch = _make_orchestrator_with_mocks(seg_mask)
        # Any use of the overlap filter would touch this attribute.
        orch._overlap_filter = MagicMock()

        result = orch.process_single(img)

        assert result.success
        orch._overlap_filter.filter.assert_not_called()
        assert result.image_result.overlap_filter_applied is False
        assert result.image_result.removed_overlap_ids == []
        assert result.image_result.original_grain_count is None


# ---------------------------------------------------------------------------
# Flag on: filter runs, measurements use filtered mask
# ---------------------------------------------------------------------------


class TestOverlapFilterOn:
    def test_filter_invoked_when_flag_true(self, tmp_path):
        img = tmp_path / "sample.jpg"
        img.write_bytes(b"fake")

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1
        seg_mask[6:9, 6:9] = 2

        filtered_mask = seg_mask.copy()
        filtered_mask[filtered_mask == 2] = 0  # simulate removal of grain 2

        orch = _make_orchestrator_with_mocks(seg_mask)
        orch._overlap_filter = _mock_overlap_filter(
            removed_ids=[2], filtered_mask=filtered_mask
        )

        result = orch.process_single(img, remove_overlaps=True)

        assert result.success
        orch._overlap_filter.filter.assert_called_once()

        # The mask passed to measurement must be the filtered one.
        measure_call_args, measure_call_kwargs = orch._meas_engine.measure.call_args
        passed_mask = measure_call_args[0] if measure_call_args else measure_call_kwargs["mask"]
        np.testing.assert_array_equal(passed_mask, filtered_mask)

    def test_image_result_records_overlap_metadata(self, tmp_path):
        img = tmp_path / "sample.jpg"
        img.write_bytes(b"fake")

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1
        seg_mask[6:9, 6:9] = 2
        filtered = seg_mask.copy()
        filtered[filtered == 2] = 0

        orch = _make_orchestrator_with_mocks(seg_mask)
        orch._overlap_filter = _mock_overlap_filter(
            removed_ids=[2], filtered_mask=filtered
        )

        result = orch.process_single(img, remove_overlaps=True)
        image_result = result.image_result

        assert image_result.overlap_filter_applied is True
        assert image_result.removed_overlap_ids == [2]
        assert image_result.original_grain_count == 2

    def test_no_removals_leaves_measurements_untouched(self, tmp_path):
        img = tmp_path / "sample.jpg"
        img.write_bytes(b"fake")

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1

        orch = _make_orchestrator_with_mocks(seg_mask)
        orch._overlap_filter = _mock_overlap_filter(
            removed_ids=[], filtered_mask=seg_mask
        )

        result = orch.process_single(img, remove_overlaps=True)

        assert result.success
        assert result.image_result.overlap_filter_applied is True
        assert result.image_result.removed_overlap_ids == []


# ---------------------------------------------------------------------------
# Persistence: save_mask + remove_overlaps
# ---------------------------------------------------------------------------


class TestSaveMaskWithOverlapFilter:
    def test_saves_filtered_and_original_masks_and_analysis_csv(self, tmp_path):
        img = tmp_path / "sample.jpg"
        img.write_bytes(b"fake")

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1
        seg_mask[6:9, 6:9] = 2
        filtered = seg_mask.copy()
        filtered[filtered == 2] = 0

        records = [
            OverlapPairRecord(
                grain_a=1, grain_b=2,
                concavity_a=0.02, concavity_b=0.20,
                solidity_a=0.98, solidity_b=0.60,
                votes_a=0, votes_b=3,
                removed_grain=2,
                reason="strong global concavity",
            ),
        ]

        orch = _make_orchestrator_with_mocks(seg_mask)
        orch._overlap_filter = _mock_overlap_filter(
            removed_ids=[2], filtered_mask=filtered, pair_records=records
        )
        # save_mask writes real TIFFs — replace with a spy so we don't
        # depend on tifffile inside this focused wiring test.
        saved_paths = []

        def fake_save(mask, path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"TIFF")
            saved_paths.append(Path(path))

        orch._seg_engine.save_mask.side_effect = fake_save

        result = orch.process_single(
            img,
            save_mask=True,
            output_dir=tmp_path,
            remove_overlaps=True,
        )

        assert result.success
        # Both the filtered and original mask files should have been saved.
        names = {p.name for p in saved_paths}
        assert "sample_mask.tiff" in names
        assert "sample_mask_original.tiff" in names
        # And the overlap analysis CSV should exist with a header row.
        analysis = tmp_path / "sample_overlap_analysis.csv"
        assert analysis.exists()
        header = analysis.read_text(encoding="utf-8").splitlines()[0]
        for col in ("grain_A", "grain_B", "removed_grain", "reason"):
            assert col in header
        # ImageResult should point at the analysis path.
        assert result.image_result.overlap_analysis_path == analysis
        assert result.image_result.filtered_mask_path == tmp_path / "sample_mask.tiff"

    def test_save_mask_alone_writes_only_one_mask(self, tmp_path):
        """save_mask=True + remove_overlaps=False → no extra files."""
        img = tmp_path / "sample.jpg"
        img.write_bytes(b"fake")

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1

        orch = _make_orchestrator_with_mocks(seg_mask)
        orch._overlap_filter = MagicMock()

        saved_paths = []

        def fake_save(mask, path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"TIFF")
            saved_paths.append(Path(path))

        orch._seg_engine.save_mask.side_effect = fake_save

        result = orch.process_single(img, save_mask=True, output_dir=tmp_path)

        assert result.success
        names = {p.name for p in saved_paths}
        assert names == {"sample_mask.tiff"}
        assert not (tmp_path / "sample_overlap_analysis.csv").exists()
        orch._overlap_filter.filter.assert_not_called()


# ---------------------------------------------------------------------------
# Batch propagation
# ---------------------------------------------------------------------------


class TestProcessBatchOverlapPropagation:
    def test_process_batch_threads_remove_overlaps(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "a.jpg").write_bytes(b"fake")
        output_csv = tmp_path / "out" / "results.csv"

        seg_mask = np.zeros((10, 10), dtype=np.int32)
        seg_mask[2:6, 2:6] = 1
        seg_mask[6:9, 6:9] = 2
        filtered = seg_mask.copy()
        filtered[filtered == 2] = 0

        orch = _make_orchestrator_with_mocks(seg_mask)
        orch._loader.discover_images.return_value = [input_dir / "a.jpg"]
        orch._overlap_filter = _mock_overlap_filter(
            removed_ids=[2], filtered_mask=filtered
        )

        batch = orch.process_batch(
            input_path=input_dir,
            output_path=output_csv,
            remove_overlaps=True,
        )

        assert batch.total_images == 1
        assert batch.successful == 1
        orch._overlap_filter.filter.assert_called_once()
        assert batch.results[0].overlap_filter_applied is True
        assert batch.results[0].removed_overlap_ids == [2]
