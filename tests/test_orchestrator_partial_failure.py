"""Property-based tests for partial batch failure resilience.

Feature: sedimental-analysis-tool
Property: 18 - Partial Batch Failure Resilience
Validates: Requirements 9.5
"""

import numpy as np
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.errors import InvalidImageError, SegmentationError
from sedimental.models import (
    BatchResult,
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    SampleMetadata,
    SegmentationResult,
)
from sedimental.orchestrator import ProcessingOrchestrator


# ---------------------------------------------------------------------------
# Helpers
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


def _fake_mask() -> np.ndarray:
    mask = np.zeros((10, 10), dtype=np.int32)
    mask[2:5, 2:5] = 1
    return mask


def _make_orchestrator_with_failures(
    good_names: list[str],
    bad_names: list[str],
    tmp_path: Path,
) -> tuple[ProcessingOrchestrator, Path, list[Path]]:
    """
    Build an orchestrator whose loader succeeds for good_names and raises
    InvalidImageError for bad_names. Returns the orchestrator, the input
    directory, and the ordered list of image paths.
    """
    input_dir = tmp_path / "input"
    input_dir.mkdir(exist_ok=True)

    all_names = good_names + bad_names
    image_paths = [input_dir / name for name in all_names]
    for p in image_paths:
        p.write_bytes(b"fake")

    orch = ProcessingOrchestrator()

    # Mock loader
    orch._loader = MagicMock()
    orch._loader.discover_images.return_value = image_paths

    def load_side_effect(path: Path):
        if path.name in bad_names:
            raise InvalidImageError(path.name, "corrupted")
        return np.zeros((10, 10, 3), dtype=np.uint8)

    orch._loader.load.side_effect = load_side_effect

    # Mock segmentation engine
    mock_seg = MagicMock()
    mock_seg.segment.return_value = SegmentationResult(
        mask=_fake_mask(), grain_count=1, warnings=[]
    )
    orch._seg_engine = mock_seg

    # Mock measurement engine
    mock_meas = MagicMock()
    mock_meas.measure.return_value = [_fake_measurement()]
    orch._meas_engine = mock_meas

    return orch, input_dir, image_paths


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def partial_failure_scenario(draw):
    """
    Generate a scenario with N total images where K fail (0 < K < N).

    Returns (good_names, bad_names) as lists of unique filenames.
    """
    total = draw(st.integers(min_value=2, max_value=10))
    # At least 1 failure and at least 1 success
    num_bad = draw(st.integers(min_value=1, max_value=total - 1))
    num_good = total - num_bad

    names = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="_",
                ),
            ).map(lambda s: s + ".jpg"),
            min_size=total,
            max_size=total,
            unique=True,
        )
    )

    good_names = names[:num_good]
    bad_names = names[num_good:]
    return good_names, bad_names


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestPartialBatchFailureResilience:
    """
    Property 18: Partial Batch Failure Resilience

    For any batch of N images where K images fail processing (0 < K < N),
    the BatchResult SHALL contain:
    - successful == N - K
    - failed == K
    - results list with N - K ImageResult objects
    - errors dict with K entries mapping failed filenames to error messages

    Validates: Requirements 9.5
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_successful_count_equals_n_minus_k(self, tmp_path, scenario):
        """
        Property 18a: successful == N - K (total minus failures).
        """
        good_names, bad_names = scenario
        n = len(good_names) + len(bad_names)
        k = len(bad_names)

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.successful == n - k, (
            f"Expected successful={n - k}, got {batch.successful} "
            f"(total={n}, failed={k})"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_failed_count_equals_k(self, tmp_path, scenario):
        """
        Property 18b: failed == K (exactly the number of failing images).
        """
        good_names, bad_names = scenario
        k = len(bad_names)

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.failed == k, (
            f"Expected failed={k}, got {batch.failed}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_results_list_length_equals_successful(self, tmp_path, scenario):
        """
        Property 18c: len(results) == successful — one ImageResult per success.
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert len(batch.results) == batch.successful, (
            f"len(results)={len(batch.results)} != successful={batch.successful}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_errors_dict_length_equals_failed(self, tmp_path, scenario):
        """
        Property 18d: len(errors) == failed — one error entry per failing image.
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert len(batch.errors) == batch.failed, (
            f"len(errors)={len(batch.errors)} != failed={batch.failed}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_errors_dict_keys_are_failed_filenames(self, tmp_path, scenario):
        """
        Property 18e: errors dict keys are exactly the filenames of the failing images.
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert set(batch.errors.keys()) == set(bad_names), (
            f"errors keys {set(batch.errors.keys())} != expected {set(bad_names)}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_error_messages_are_non_empty(self, tmp_path, scenario):
        """
        Property 18f: Every error entry has a non-empty error message string.
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        for filename, error_msg in batch.errors.items():
            assert isinstance(error_msg, str) and len(error_msg) > 0, (
                f"Error message for '{filename}' is empty or not a string"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_successful_results_contain_only_good_files(self, tmp_path, scenario):
        """
        Property 18g: results list contains only ImageResults for the good images,
        not for any of the failing ones.
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        result_files = {r.source_file for r in batch.results}
        assert result_files.issubset(set(good_names)), (
            f"results contain unexpected files: {result_files - set(good_names)}"
        )
        for bad in bad_names:
            assert bad not in result_files, (
                f"Failed image '{bad}' unexpectedly appeared in results"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_total_images_equals_n(self, tmp_path, scenario):
        """
        Property 18h: total_images == N (all images, successful and failed).
        """
        good_names, bad_names = scenario
        n = len(good_names) + len(bad_names)

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == n, (
            f"Expected total_images={n}, got {batch.total_images}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_successful_plus_failed_equals_total(self, tmp_path, scenario):
        """
        Property 18i: successful + failed == total_images (no images unaccounted for).
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.successful + batch.failed == batch.total_images, (
            f"successful({batch.successful}) + failed({batch.failed}) "
            f"!= total_images({batch.total_images})"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=partial_failure_scenario())
    def test_property_csv_written_when_partial_failure(self, tmp_path, scenario):
        """
        Property 18j: A CSV is written when at least one image succeeds,
        even if others fail.
        """
        good_names, bad_names = scenario

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        # At least one success guaranteed by the scenario strategy
        assert batch.successful > 0
        assert output_csv.exists(), (
            "CSV should be written when at least one image succeeds"
        )

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_one_bad_out_of_three(self, tmp_path):
        """Concrete: 2 good + 1 bad → successful=2, failed=1, errors has bad.jpg."""
        good_names = ["good1.jpg", "good2.jpg"]
        bad_names = ["bad.jpg"]

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == 3
        assert batch.successful == 2
        assert batch.failed == 1
        assert "bad.jpg" in batch.errors
        assert len(batch.results) == 2
        assert output_csv.exists()

    def test_concrete_segmentation_failure_is_resilient(self, tmp_path):
        """Concrete: segmentation failure on one image doesn't abort the batch."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        for name in ["a.jpg", "b.jpg", "c.jpg"]:
            (input_dir / name).write_bytes(b"fake")

        orch = ProcessingOrchestrator()
        orch._loader = MagicMock()
        orch._loader.discover_images.return_value = [
            input_dir / "a.jpg",
            input_dir / "b.jpg",
            input_dir / "c.jpg",
        ]
        orch._loader.load.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        mock_seg = MagicMock()

        def seg_side_effect(image, filename=""):
            if filename == "b.jpg":
                raise SegmentationError("b.jpg", "model crash")
            return SegmentationResult(mask=_fake_mask(), grain_count=1, warnings=[])

        mock_seg.segment.side_effect = seg_side_effect
        orch._seg_engine = mock_seg

        mock_meas = MagicMock()
        mock_meas.measure.return_value = [_fake_measurement()]
        orch._meas_engine = mock_meas

        output_csv = tmp_path / "results.csv"
        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == 3
        assert batch.successful == 2
        assert batch.failed == 1
        assert "b.jpg" in batch.errors
        assert output_csv.exists()

    def test_concrete_error_message_contains_filename(self, tmp_path):
        """Concrete: error messages reference the failing filename."""
        good_names = ["good.jpg"]
        bad_names = ["corrupted.jpg"]

        orch, input_dir, _ = _make_orchestrator_with_failures(
            good_names, bad_names, tmp_path
        )
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert "corrupted.jpg" in batch.errors
        assert "corrupted.jpg" in batch.errors["corrupted.jpg"]
