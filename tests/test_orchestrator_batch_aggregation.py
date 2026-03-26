"""Property-based tests for batch result aggregation.

Feature: sedimental-analysis-tool
Property: 19 - Batch Result Aggregation
Validates: Requirements 9.2, 9.6
"""

import numpy as np
from pathlib import Path
from unittest.mock import MagicMock

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

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


def _make_mask_with_n_grains(n: int) -> np.ndarray:
    """Return a (20, 20) mask with n distinct grain labels."""
    mask = np.zeros((20, 20), dtype=np.int32)
    for i in range(1, n + 1):
        mask[i, i] = i
    return mask


def _make_orchestrator_all_succeed(
    image_names: list[str],
    grains_per_image: list[int],
    tmp_path: Path,
) -> tuple[ProcessingOrchestrator, Path]:
    """
    Build an orchestrator where every image succeeds and each image
    produces the specified number of grains.
    """
    input_dir = tmp_path / "input"
    input_dir.mkdir(exist_ok=True)

    image_paths = []
    for name in image_names:
        p = input_dir / name
        p.write_bytes(b"fake")
        image_paths.append(p)

    orch = ProcessingOrchestrator()

    orch._loader = MagicMock()
    orch._loader.discover_images.return_value = image_paths
    orch._loader.load.return_value = np.zeros((20, 20, 3), dtype=np.uint8)

    # Segmentation: return a mask whose grain count matches grains_per_image
    seg_call_count = [0]

    def seg_side_effect(image, filename=""):
        idx = seg_call_count[0]
        n = grains_per_image[idx % len(grains_per_image)]
        seg_call_count[0] += 1
        return SegmentationResult(
            mask=_make_mask_with_n_grains(n),
            grain_count=n,
            warnings=[],
        )

    mock_seg = MagicMock()
    mock_seg.segment.side_effect = seg_side_effect
    orch._seg_engine = mock_seg

    # Measurement: return one GrainMeasurement per grain label
    meas_call_count = [0]

    def meas_side_effect(mask, scale_ppm=None, filename=""):
        idx = meas_call_count[0]
        n = grains_per_image[idx % len(grains_per_image)]
        meas_call_count[0] += 1
        return [_fake_measurement(grain_id=g) for g in range(1, n + 1)]

    mock_meas = MagicMock()
    mock_meas.measure.side_effect = meas_side_effect
    orch._meas_engine = mock_meas

    return orch, input_dir


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def batch_scenario(draw):
    """
    Generate a list of (image_name, grain_count) pairs for a successful batch.
    Each image has a unique name and between 0 and 5 grains.
    """
    n_images = draw(st.integers(min_value=1, max_value=8))
    names = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=15,
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="_",
                ),
            ).map(lambda s: s + ".jpg"),
            min_size=n_images,
            max_size=n_images,
            unique=True,
        )
    )
    grains = draw(
        st.lists(
            st.integers(min_value=0, max_value=5),
            min_size=n_images,
            max_size=n_images,
        )
    )
    return list(zip(names, grains))


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestBatchResultAggregation:
    """
    Property 19: Batch Result Aggregation

    For any batch processing of N images producing a total of G grains
    across all images:
    - The Results_CSV SHALL contain exactly G data rows
    - The BatchResult.total_images SHALL equal N
    - The sum of grain counts across all ImageResults SHALL equal G

    Validates: Requirements 9.2, 9.6
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=batch_scenario())
    def test_property_total_images_equals_n(self, tmp_path, scenario):
        """
        Property 19a: BatchResult.total_images == N (number of images in batch).
        """
        names = [name for name, _ in scenario]
        grains = [g for _, g in scenario]
        n = len(names)

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == n, (
            f"Expected total_images={n}, got {batch.total_images}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=batch_scenario())
    def test_property_grain_sum_matches_csv_rows(self, tmp_path, scenario):
        """
        Property 19b: The Results_CSV contains exactly G data rows where
        G = sum of grain counts across all successfully processed images.
        """
        names = [name for name, _ in scenario]
        grains = [g for _, g in scenario]
        total_grains = sum(grains)

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        if total_grains == 0:
            # No grains → CSV may or may not be written; just check row count is 0
            if not output_csv.exists():
                return
            lines = output_csv.read_text().strip().splitlines()
            data_rows = len(lines) - 1 if len(lines) > 1 else 0
            assert data_rows == 0
            return

        assert output_csv.exists(), "CSV should be written when grains > 0"

        # Count data rows (skip header)
        lines = output_csv.read_text().strip().splitlines()
        data_rows = len(lines) - 1  # subtract header

        assert data_rows == total_grains, (
            f"CSV has {data_rows} data rows but expected {total_grains} "
            f"(grains per image: {grains})"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=batch_scenario())
    def test_property_measurement_sum_equals_total_grains(self, tmp_path, scenario):
        """
        Property 19c: Sum of len(result.measurements) across all ImageResults
        equals the total grain count G.
        """
        names = [name for name, _ in scenario]
        grains = [g for _, g in scenario]
        total_grains = sum(grains)

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        measured_total = sum(len(r.measurements) for r in batch.results)

        assert measured_total == total_grains, (
            f"Sum of measurements={measured_total} != total_grains={total_grains}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=batch_scenario())
    def test_property_results_contain_source_filenames(self, tmp_path, scenario):
        """
        Property 19d: Every ImageResult in batch.results has a source_file
        that matches one of the input image names (Requirement 9.3).
        """
        names = [name for name, _ in scenario]
        grains = [g for _, g in scenario]

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        name_set = set(names)
        for result in batch.results:
            assert result.source_file in name_set, (
                f"source_file '{result.source_file}' not in input names {name_set}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(scenario=batch_scenario())
    def test_property_successful_equals_n_when_all_succeed(self, tmp_path, scenario):
        """
        Property 19e: When all images succeed, successful == N and failed == 0.
        """
        names = [name for name, _ in scenario]
        grains = [g for _, g in scenario]
        n = len(names)

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.successful == n, (
            f"Expected successful={n}, got {batch.successful}"
        )
        assert batch.failed == 0, (
            f"Expected failed=0, got {batch.failed}"
        )

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_three_images_total_grain_count(self, tmp_path):
        """Concrete: 3 images with 2, 3, 1 grains → 6 CSV rows, total_images=3."""
        names = ["a.jpg", "b.jpg", "c.jpg"]
        grains = [2, 3, 1]

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == 3
        assert batch.successful == 3
        assert batch.failed == 0

        lines = output_csv.read_text().strip().splitlines()
        assert len(lines) - 1 == 6  # 6 data rows

        measured = sum(len(r.measurements) for r in batch.results)
        assert measured == 6

    def test_concrete_single_image_grain_count_in_csv(self, tmp_path):
        """Concrete: 1 image with 4 grains → 4 CSV rows."""
        names = ["sample.jpg"]
        grains = [4]

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == 1
        lines = output_csv.read_text().strip().splitlines()
        assert len(lines) - 1 == 4

    def test_concrete_zero_grains_still_succeeds(self, tmp_path):
        """Concrete: 2 images each with 0 grains → batch succeeds, total_images=2."""
        names = ["empty1.jpg", "empty2.jpg"]
        grains = [0, 0]

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        batch = orch.process_batch(input_dir, output_csv)

        assert batch.total_images == 2
        assert batch.successful == 2
        assert batch.failed == 0
        # 0 grains total → 0 measurement rows across all results
        total_measured = sum(len(r.measurements) for r in batch.results)
        assert total_measured == 0

    def test_concrete_source_file_column_in_csv(self, tmp_path):
        """Concrete: source_file column in CSV matches input filenames."""
        names = ["rock1.jpg", "rock2.jpg"]
        grains = [1, 2]

        orch, input_dir = _make_orchestrator_all_succeed(names, grains, tmp_path)
        output_csv = tmp_path / "results.csv"

        orch.process_batch(input_dir, output_csv)

        content = output_csv.read_text()
        assert "rock1.jpg" in content
        assert "rock2.jpg" in content
