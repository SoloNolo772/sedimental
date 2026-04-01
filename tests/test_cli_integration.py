"""
CLI integration tests for Sedimental analysis tool.

Tests the run_process_internal() path end-to-end using mocked sub-components
(SegmentationEngine, MeasurementEngine) so no real Cellpose/PyImageJ runtime
is needed. All tests run inside the container via SEDIMENTAL_INSIDE_CONTAINER.

Validates Requirements: 6.1, 6.2, 9.1, 9.5
"""

import argparse
import json
import os
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sedimental.cli import run_process_internal
from sedimental.models import (
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    SampleMetadata,
    SegmentationResult,
)
from sedimental.errors import InvalidImageError, SegmentationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(input_path, output, metadata=None, save_masks=False, scale=None, verbose=False):
    return argparse.Namespace(
        input=str(input_path),
        output=str(output),
        metadata=str(metadata) if metadata else None,
        save_masks=save_masks,
        scale=scale,
        verbose=verbose,
    )


def _fake_measurement(grain_id: int = 1) -> GrainMeasurement:
    return GrainMeasurement(
        grain_id=grain_id,
        area=150.0,
        perimeter=50.0,
        circularity=0.75,
        roundness=0.85,
        feret_diameter=15.0,
        major_axis=14.0,
        minor_axis=10.0,
        unit=MeasurementUnit.PIXELS,
        scale_factor=None,
    )


def _fake_mask() -> np.ndarray:
    mask = np.zeros((20, 20), dtype=np.int32)
    mask[5:10, 5:10] = 1
    return mask


def _make_orchestrator(
    load_return=None,
    seg_return=None,
    meas_return=None,
    load_side_effect=None,
    seg_side_effect=None,
):
    """Return a ProcessingOrchestrator with mocked sub-components."""
    from sedimental.orchestrator import ProcessingOrchestrator

    orch = ProcessingOrchestrator()

    orch._loader = MagicMock()
    if load_side_effect:
        orch._loader.load.side_effect = load_side_effect
    else:
        orch._loader.load.return_value = (
            load_return if load_return is not None
            else np.zeros((20, 20, 3), dtype=np.uint8)
        )

    mock_seg = MagicMock()
    if seg_side_effect:
        mock_seg.segment.side_effect = seg_side_effect
    else:
        mock_seg.segment.return_value = (
            seg_return if seg_return is not None
            else SegmentationResult(mask=_fake_mask(), grain_count=1, warnings=[])
        )
    orch._seg_engine = mock_seg

    mock_meas = MagicMock()
    mock_meas.measure.return_value = (
        meas_return if meas_return is not None else [_fake_measurement()]
    )
    orch._meas_engine = mock_meas

    return orch


def _write_jpeg(path: Path) -> None:
    """Write a minimal valid JPEG to *path* using Pillow."""
    from PIL import Image
    img = Image.new("RGB", (10, 10), color=(128, 64, 32))
    img.save(path, format="JPEG")


# ---------------------------------------------------------------------------
# Single image processing end-to-end (Req 6.1, 6.2)
# ---------------------------------------------------------------------------

class TestSingleImageProcessing:
    """End-to-end tests for single image processing via run_process_internal."""

    def test_single_image_exits_zero(self, tmp_path):
        """Req 6.8 - processing a single valid image exits with code 0."""
        img = tmp_path / "sample.jpg"
        _write_jpeg(img)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(img, output_csv))

        assert result == 0

    def test_single_image_produces_csv(self, tmp_path):
        """Req 6.2 - output CSV is written to the specified path."""
        img = tmp_path / "sample.jpg"
        _write_jpeg(img)
        output_csv = tmp_path / "out" / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(img, output_csv))

        assert output_csv.exists(), "CSV file should be written to the specified output path"

    def test_single_image_csv_has_grain_rows(self, tmp_path):
        """CSV produced for a single image contains one row per grain."""
        img = tmp_path / "sample.jpg"
        _write_jpeg(img)
        output_csv = tmp_path / "results.csv"

        measurements = [_fake_measurement(1), _fake_measurement(2)]
        orch = _make_orchestrator(meas_return=measurements)
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(img, output_csv))

        lines = output_csv.read_text().splitlines()
        # header + 2 data rows
        assert len(lines) == 3, f"Expected 3 lines (header + 2 grains), got {len(lines)}"

    def test_single_image_csv_contains_source_filename(self, tmp_path):
        """Req 6.1 - source filename appears in the CSV output."""
        img = tmp_path / "mysample.jpg"
        _write_jpeg(img)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(img, output_csv))

        content = output_csv.read_text()
        assert "mysample.jpg" in content

    def test_single_image_csv_has_required_columns(self, tmp_path):
        """CSV header contains all required measurement columns."""
        img = tmp_path / "sample.jpg"
        _write_jpeg(img)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(img, output_csv))

        header = output_csv.read_text().splitlines()[0]
        for col in ("source_file", "grain_id", "area", "perimeter",
                    "circularity", "roundness", "feret_diameter",
                    "major_axis", "minor_axis", "units"):
            assert col in header, f"Expected column '{col}' in CSV header"

    def test_single_image_invalid_exits_nonzero(self, tmp_path):
        """Req 6.9 - invalid image causes non-zero exit code."""
        img = tmp_path / "bad.jpg"
        img.write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator(
            load_side_effect=lambda p: (_ for _ in ()).throw(
                InvalidImageError(p.name, "corrupted")
            )
        )
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(img, output_csv))

        assert result != 0

    def test_single_image_invalid_prints_error(self, tmp_path, capsys):
        """Req 6.9 - error message is printed to stderr for invalid input."""
        img = tmp_path / "bad.jpg"
        img.write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator(
            load_side_effect=lambda p: (_ for _ in ()).throw(
                InvalidImageError(p.name, "corrupted")
            )
        )
        orch._loader.discover_images.return_value = [img]

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(img, output_csv))

        captured = capsys.readouterr()
        assert "error" in captured.err.lower() or "Error" in captured.err


# ---------------------------------------------------------------------------
# Batch processing with metadata (Req 9.1, 6.3)
# ---------------------------------------------------------------------------

class TestBatchProcessingWithMetadata:
    """End-to-end tests for batch directory processing with metadata."""

    def _setup_batch(self, tmp_path, count=3):
        """Create *count* JPEG files in an input directory."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        images = []
        for i in range(count):
            img = input_dir / f"sample{i}.jpg"
            _write_jpeg(img)
            images.append(img)
        return input_dir, images

    def test_batch_processes_all_jpegs_in_directory(self, tmp_path):
        """Req 9.1 - all JPEG files in a directory are processed."""
        input_dir, images = self._setup_batch(tmp_path, count=3)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(input_dir, output_csv))

        assert result == 0

    def test_batch_csv_has_row_per_grain_across_images(self, tmp_path):
        """Req 9.2 - CSV aggregates grains from all images into one file."""
        input_dir, images = self._setup_batch(tmp_path, count=3)
        output_csv = tmp_path / "results.csv"

        # 2 grains per image → 6 total rows
        orch = _make_orchestrator(
            meas_return=[_fake_measurement(1), _fake_measurement(2)]
        )
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(input_dir, output_csv))

        lines = output_csv.read_text().splitlines()
        assert len(lines) == 7, f"Expected 7 lines (header + 6 grains), got {len(lines)}"

    def test_batch_csv_contains_all_source_filenames(self, tmp_path):
        """Req 9.3 - source filename is recorded for each grain row."""
        input_dir, images = self._setup_batch(tmp_path, count=2)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(input_dir, output_csv))

        content = output_csv.read_text()
        for img in images:
            assert img.name in content, f"Expected '{img.name}' in CSV output"

    def test_batch_with_auto_discovered_metadata(self, tmp_path):
        """Req 5.1 - metadata.json in input dir is auto-discovered and applied."""
        input_dir, images = self._setup_batch(tmp_path, count=2)
        metadata = {
            "default": {"sample_id": "RIVER-001", "submitted_by": "geo_user"},
            "images": {},
        }
        (input_dir / "metadata.json").write_text(json.dumps(metadata))
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(input_dir, output_csv))

        assert result == 0
        content = output_csv.read_text()
        assert "RIVER-001" in content

    def test_batch_with_explicit_metadata_path(self, tmp_path):
        """Req 5.2 / 6.3 - --metadata argument loads metadata from specified file."""
        input_dir, images = self._setup_batch(tmp_path, count=2)
        # Auto-discovered file (should be ignored)
        (input_dir / "metadata.json").write_text(
            json.dumps({"default": {"sample_id": "AUTO"}, "images": {}})
        )
        # Explicit override
        explicit = tmp_path / "explicit_meta.json"
        explicit.write_text(
            json.dumps({"default": {"sample_id": "EXPLICIT-999"}, "images": {}})
        )
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(
                _make_args(input_dir, output_csv, metadata=explicit)
            )

        assert result == 0
        content = output_csv.read_text()
        assert "EXPLICIT-999" in content
        assert "AUTO" not in content

    def test_batch_with_per_image_metadata_override(self, tmp_path):
        """Req 5.10 - per-image metadata overrides default metadata."""
        input_dir, images = self._setup_batch(tmp_path, count=2)
        img0_name = images[0].name
        metadata = {
            "default": {"sample_id": "DEFAULT-ID"},
            "images": {
                img0_name: {"sample_id": "OVERRIDE-ID"},
            },
        }
        (input_dir / "metadata.json").write_text(json.dumps(metadata))
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(input_dir, output_csv))

        content = output_csv.read_text()
        assert "OVERRIDE-ID" in content

    def test_batch_with_scale_flag(self, tmp_path):
        """Req 6.5 / 10.1 - --scale flag is forwarded to the orchestrator."""
        input_dir, images = self._setup_batch(tmp_path, count=1)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(
                _make_args(input_dir, output_csv, scale=25.4)
            )

        assert result == 0

    def test_batch_empty_directory_exits_nonzero(self, tmp_path):
        """Req 6.9 - empty directory (no JPEGs) exits with non-zero code."""
        input_dir = tmp_path / "empty"
        input_dir.mkdir()
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = []

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(input_dir, output_csv))

        assert result != 0


# ---------------------------------------------------------------------------
# Error handling for invalid inputs (Req 9.5, 6.9)
# ---------------------------------------------------------------------------

class TestErrorHandlingForInvalidInputs:
    """Tests for graceful error handling when inputs are invalid or processing fails."""

    def test_partial_failure_continues_processing(self, tmp_path):
        """Req 9.5 - one failing image does not abort the batch."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        good = input_dir / "good.jpg"
        bad = input_dir / "bad.jpg"
        _write_jpeg(good)
        bad.write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [good, bad]

        def load_side_effect(path):
            if path.name == "bad.jpg":
                raise InvalidImageError("bad.jpg", "corrupted")
            return np.zeros((20, 20, 3), dtype=np.uint8)

        orch._loader.load.side_effect = load_side_effect

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(input_dir, output_csv))

        # Partial failure → exit 0 (Property 17)
        assert result == 0
        assert output_csv.exists()

    def test_partial_failure_csv_contains_only_successful_results(self, tmp_path):
        """Req 9.5 - CSV only contains rows for successfully processed images."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        good = input_dir / "good.jpg"
        bad = input_dir / "bad.jpg"
        _write_jpeg(good)
        bad.write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [good, bad]

        def load_side_effect(path):
            if path.name == "bad.jpg":
                raise InvalidImageError("bad.jpg", "corrupted")
            return np.zeros((20, 20, 3), dtype=np.uint8)

        orch._loader.load.side_effect = load_side_effect

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(input_dir, output_csv))

        content = output_csv.read_text()
        assert "good.jpg" in content
        assert "bad.jpg" not in content

    def test_all_images_fail_exits_nonzero(self, tmp_path):
        """Req 6.9 - all images failing causes non-zero exit."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        images = [input_dir / f"bad{i}.jpg" for i in range(3)]
        for img in images:
            img.write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator(
            load_side_effect=lambda p: (_ for _ in ()).throw(
                InvalidImageError(p.name, "corrupted")
            )
        )
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(input_dir, output_csv))

        assert result != 0

    def test_all_images_fail_no_csv_written(self, tmp_path):
        """When all images fail, no CSV is written."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        images = [input_dir / "bad.jpg"]
        images[0].write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator(
            load_side_effect=lambda p: (_ for _ in ()).throw(
                InvalidImageError(p.name, "corrupted")
            )
        )
        orch._loader.discover_images.return_value = images

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(input_dir, output_csv))

        assert not output_csv.exists()

    def test_segmentation_failure_is_resilient(self, tmp_path):
        """Req 9.5 - segmentation failure on one image doesn't abort the batch."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        images = [input_dir / f"img{i}.jpg" for i in range(3)]
        for img in images:
            _write_jpeg(img)
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = images
        orch._loader.load.return_value = np.zeros((20, 20, 3), dtype=np.uint8)

        def seg_side_effect(image, filename=""):
            if filename == "img1.jpg":
                raise SegmentationError("img1.jpg", "model crash")
            return SegmentationResult(mask=_fake_mask(), grain_count=1, warnings=[])

        orch._seg_engine.segment.side_effect = seg_side_effect

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(input_dir, output_csv))

        assert result == 0
        assert output_csv.exists()

    def test_partial_failure_prints_warning_to_stderr(self, tmp_path, capsys):
        """Req 9.5 - partial failure logs a warning message."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        good = input_dir / "good.jpg"
        bad = input_dir / "bad.jpg"
        _write_jpeg(good)
        bad.write_bytes(b"not a jpeg")
        output_csv = tmp_path / "results.csv"

        orch = _make_orchestrator()
        orch._loader.discover_images.return_value = [good, bad]

        def load_side_effect(path):
            if path.name == "bad.jpg":
                raise InvalidImageError("bad.jpg", "corrupted")
            return np.zeros((20, 20, 3), dtype=np.uint8)

        orch._loader.load.side_effect = load_side_effect

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            run_process_internal(_make_args(input_dir, output_csv))

        captured = capsys.readouterr()
        assert "warning" in captured.err.lower() or "Warning" in captured.err

    def test_malformed_metadata_exits_nonzero(self, tmp_path):
        """Req 5.11 - malformed metadata JSON causes non-zero exit."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        img = input_dir / "sample.jpg"
        _write_jpeg(img)
        bad_meta = tmp_path / "bad_meta.json"
        bad_meta.write_text("{this is not valid json")
        output_csv = tmp_path / "results.csv"

        # Use real orchestrator so metadata parsing is exercised
        from sedimental.orchestrator import ProcessingOrchestrator
        orch = ProcessingOrchestrator()
        orch._loader = MagicMock()
        orch._loader.discover_images.return_value = [img]
        orch._loader.load.return_value = np.zeros((20, 20, 3), dtype=np.uint8)
        mock_seg = MagicMock()
        mock_seg.segment.return_value = SegmentationResult(
            mask=_fake_mask(), grain_count=1, warnings=[]
        )
        orch._seg_engine = mock_seg
        mock_meas = MagicMock()
        mock_meas.measure.return_value = [_fake_measurement()]
        orch._meas_engine = mock_meas

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(
                _make_args(input_dir, output_csv, metadata=bad_meta)
            )

        assert result != 0

    def test_nonexistent_input_path_exits_nonzero(self, tmp_path):
        """Req 6.9 - non-existent input path causes non-zero exit."""
        missing = tmp_path / "does_not_exist.jpg"
        output_csv = tmp_path / "results.csv"

        # Real orchestrator — loader will raise FileNotFoundError
        from sedimental.orchestrator import ProcessingOrchestrator
        orch = ProcessingOrchestrator()
        orch._loader = MagicMock()
        orch._loader.discover_images.return_value = [missing]
        orch._loader.load.side_effect = FileNotFoundError(f"not found: {missing}")
        mock_seg = MagicMock()
        orch._seg_engine = mock_seg
        mock_meas = MagicMock()
        orch._meas_engine = mock_meas

        with patch("sedimental.cli.ProcessingOrchestrator", return_value=orch):
            result = run_process_internal(_make_args(missing, output_csv))

        assert result != 0
