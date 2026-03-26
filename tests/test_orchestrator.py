"""
Tests for ProcessingOrchestrator.

Uses mocked sub-components so no real Cellpose/PyImageJ runtime is needed.
"""

import json
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sedimental.orchestrator import ProcessingOrchestrator
from sedimental.models import (
    BatchResult,
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    ProcessingResult,
    SampleMetadata,
    SegmentationResult,
)
from sedimental.errors import InvalidImageError, SegmentationError


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _fake_measurement(grain_id: int = 1) -> GrainMeasurement:
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


def _fake_mask(h: int = 10, w: int = 10) -> np.ndarray:
    mask = np.zeros((h, w), dtype=np.int32)
    mask[2:5, 2:5] = 1
    return mask


def _make_orchestrator(
    load_return=None,
    seg_return=None,
    meas_return=None,
):
    """Return an orchestrator with mocked sub-components."""
    orch = ProcessingOrchestrator()

    # Mock loader
    orch._loader = MagicMock()
    orch._loader.load.return_value = (
        load_return if load_return is not None else np.zeros((10, 10, 3), dtype=np.uint8)
    )

    # Mock segmentation engine
    mock_seg = MagicMock()
    mock_seg.segment.return_value = (
        seg_return
        if seg_return is not None
        else SegmentationResult(mask=_fake_mask(), grain_count=1, warnings=[])
    )
    orch._seg_engine = mock_seg

    # Mock measurement engine
    mock_meas = MagicMock()
    mock_meas.measure.return_value = (
        meas_return if meas_return is not None else [_fake_measurement()]
    )
    orch._meas_engine = mock_meas

    return orch


# ---------------------------------------------------------------------------
# process_single — success path
# ---------------------------------------------------------------------------

def test_process_single_success(tmp_path):
    """process_single returns success=True with an ImageResult."""
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"fake")

    orch = _make_orchestrator()
    result = orch.process_single(img_file)

    assert result.success is True
    assert result.image_result is not None
    assert result.image_result.source_file == "sample.jpg"
    assert len(result.image_result.measurements) == 1
    assert result.error is None


def test_process_single_uses_provided_metadata(tmp_path):
    """Metadata passed to process_single is attached to the ImageResult."""
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"fake")

    meta = SampleMetadata(sample_id="S001", scale_ppm=10.0)
    orch = _make_orchestrator()
    result = orch.process_single(img_file, metadata=meta)

    assert result.success is True
    assert result.image_result.metadata.sample_id == "S001"
    # scale_ppm should be forwarded to the measurement engine
    orch._meas_engine.measure.assert_called_once()
    _, kwargs = orch._meas_engine.measure.call_args
    assert kwargs.get("scale_ppm") == 10.0 or orch._meas_engine.measure.call_args[0][1] == 10.0


def test_process_single_saves_mask(tmp_path):
    """save_mask=True causes seg_engine.save_mask to be called."""
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"fake")

    orch = _make_orchestrator()
    result = orch.process_single(img_file, save_mask=True, output_dir=tmp_path)

    assert result.success is True
    orch._seg_engine.save_mask.assert_called_once()
    assert result.image_result.segmentation_mask_path is not None


def test_process_single_no_mask_by_default(tmp_path):
    """save_mask defaults to False — save_mask should not be called."""
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"fake")

    orch = _make_orchestrator()
    orch.process_single(img_file)

    orch._seg_engine.save_mask.assert_not_called()


# ---------------------------------------------------------------------------
# process_single — failure paths
# ---------------------------------------------------------------------------

def test_process_single_invalid_image_returns_failure(tmp_path):
    """InvalidImageError from loader → success=False, error message set."""
    img_file = tmp_path / "bad.jpg"
    img_file.write_bytes(b"not an image")

    orch = _make_orchestrator()
    orch._loader.load.side_effect = InvalidImageError("bad.jpg", "corrupted")

    result = orch.process_single(img_file)

    assert result.success is False
    assert "bad.jpg" in result.error
    assert result.image_result is None


def test_process_single_segmentation_error_returns_failure(tmp_path):
    """SegmentationError → success=False, processing does not raise."""
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"fake")

    orch = _make_orchestrator()
    orch._seg_engine.segment.side_effect = SegmentationError("sample.jpg", "model crash")

    result = orch.process_single(img_file)

    assert result.success is False
    assert result.error is not None


def test_process_single_unexpected_exception_returns_failure(tmp_path):
    """Unexpected exceptions are caught and returned as failures."""
    img_file = tmp_path / "sample.jpg"
    img_file.write_bytes(b"fake")

    orch = _make_orchestrator()
    orch._loader.load.side_effect = RuntimeError("out of memory")

    result = orch.process_single(img_file)

    assert result.success is False
    assert "Unexpected error" in result.error


# ---------------------------------------------------------------------------
# process_batch — success path
# ---------------------------------------------------------------------------

def test_process_batch_aggregates_results(tmp_path):
    """Batch over two images produces a BatchResult with both results."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "a.jpg").write_bytes(b"fake")
    (input_dir / "b.jpg").write_bytes(b"fake")
    output_csv = tmp_path / "output" / "results.csv"

    orch = _make_orchestrator(
        meas_return=[_fake_measurement(1), _fake_measurement(2)]
    )
    orch._loader.discover_images.return_value = [
        input_dir / "a.jpg",
        input_dir / "b.jpg",
    ]

    batch = orch.process_batch(input_dir, output_csv)

    assert isinstance(batch, BatchResult)
    assert batch.total_images == 2
    assert batch.successful == 2
    assert batch.failed == 0
    assert len(batch.results) == 2
    assert batch.errors == {}


def test_process_batch_writes_csv(tmp_path):
    """Successful batch writes a CSV file to output_path."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "a.jpg").write_bytes(b"fake")
    output_csv = tmp_path / "results.csv"

    orch = _make_orchestrator()
    orch._loader.discover_images.return_value = [input_dir / "a.jpg"]

    orch.process_batch(input_dir, output_csv)

    assert output_csv.exists()


def test_process_batch_partial_failure(tmp_path):
    """One failing image does not abort the batch; errors dict is populated."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    good = input_dir / "good.jpg"
    bad = input_dir / "bad.jpg"
    good.write_bytes(b"fake")
    bad.write_bytes(b"fake")
    output_csv = tmp_path / "results.csv"

    orch = _make_orchestrator()
    orch._loader.discover_images.return_value = [good, bad]

    # Make loader fail only for bad.jpg
    def load_side_effect(path):
        if path.name == "bad.jpg":
            raise InvalidImageError("bad.jpg", "corrupted")
        return np.zeros((10, 10, 3), dtype=np.uint8)

    orch._loader.load.side_effect = load_side_effect

    batch = orch.process_batch(input_dir, output_csv)

    assert batch.total_images == 2
    assert batch.successful == 1
    assert batch.failed == 1
    assert "bad.jpg" in batch.errors
    assert output_csv.exists()


def test_process_batch_all_fail_no_csv(tmp_path):
    """When all images fail, no CSV is written."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "bad.jpg").write_bytes(b"fake")
    output_csv = tmp_path / "results.csv"

    orch = _make_orchestrator()
    orch._loader.discover_images.return_value = [input_dir / "bad.jpg"]
    orch._loader.load.side_effect = InvalidImageError("bad.jpg", "corrupted")

    batch = orch.process_batch(input_dir, output_csv)

    assert batch.successful == 0
    assert batch.failed == 1
    assert not output_csv.exists()


# ---------------------------------------------------------------------------
# Metadata resolution
# ---------------------------------------------------------------------------

def test_process_batch_auto_discovers_metadata(tmp_path):
    """metadata.json in input dir is auto-discovered and applied."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "a.jpg").write_bytes(b"fake")
    metadata = {"default": {"sample_id": "AUTO001"}, "images": {}}
    (input_dir / "metadata.json").write_text(json.dumps(metadata))
    output_csv = tmp_path / "results.csv"

    orch = _make_orchestrator()
    orch._loader.discover_images.return_value = [input_dir / "a.jpg"]

    batch = orch.process_batch(input_dir, output_csv)

    assert batch.successful == 1
    assert batch.results[0].metadata.sample_id == "AUTO001"


def test_process_batch_explicit_metadata_overrides_autodiscovery(tmp_path):
    """Explicit --metadata path takes precedence over auto-discovered file."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "a.jpg").write_bytes(b"fake")
    # Auto-discovered file
    (input_dir / "metadata.json").write_text(
        json.dumps({"default": {"sample_id": "AUTO"}, "images": {}})
    )
    # Explicit override file
    explicit_meta = tmp_path / "explicit.json"
    explicit_meta.write_text(
        json.dumps({"default": {"sample_id": "EXPLICIT"}, "images": {}})
    )
    output_csv = tmp_path / "results.csv"

    orch = _make_orchestrator()
    orch._loader.discover_images.return_value = [input_dir / "a.jpg"]

    batch = orch.process_batch(input_dir, output_csv, metadata_path=explicit_meta)

    assert batch.results[0].metadata.sample_id == "EXPLICIT"


def test_process_batch_single_file_input(tmp_path):
    """process_batch accepts a single file path instead of a directory."""
    img_file = tmp_path / "single.jpg"
    img_file.write_bytes(b"fake")
    output_csv = tmp_path / "results.csv"

    orch = _make_orchestrator()
    # discover_images should NOT be called for a single file
    batch = orch.process_batch(img_file, output_csv)

    orch._loader.discover_images.assert_not_called()
    assert batch.total_images == 1
    assert batch.successful == 1
