"""
Tests for MeasurementEngine.

Covers:
- Basic measurement correctness (area, perimeter, circularity, roundness,
  feret_diameter, major_axis, minor_axis)
- Scale conversion (pixels → mm)
- Grain count consistency
- Error handling for invalid inputs
- MeasurementUnit assignment
- Property 7: Measurement Count Consistency
"""

import math

import numpy as np
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.errors import MeasurementError
from sedimental.measurement import MeasurementEngine
from sedimental.models import GrainMeasurement, MeasurementUnit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_circular_mask(radius: int = 10, padding: int = 5) -> np.ndarray:
    """
    Return a mask containing a single roughly-circular grain (label=1).
    The grain is a filled circle of the given radius centred in the array.
    """
    size = 2 * (radius + padding)
    mask = np.zeros((size, size), dtype=np.int32)
    cy, cx = size // 2, size // 2
    y, x = np.ogrid[:size, :size]
    mask[(x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2] = 1
    return mask


def make_multi_grain_mask(n: int = 3, grain_radius: int = 5) -> np.ndarray:
    """
    Return a mask with *n* non-overlapping circular grains arranged in a row.
    Each grain has a unique positive label.
    """
    spacing = 2 * grain_radius + 4
    width = n * spacing + spacing
    height = spacing * 2
    mask = np.zeros((height, width), dtype=np.int32)
    cy = height // 2
    for i in range(n):
        cx = spacing + i * spacing
        y, x = np.ogrid[:height, :width]
        mask[(x - cx) ** 2 + (y - cy) ** 2 <= grain_radius ** 2] = i + 1
    return mask


# ---------------------------------------------------------------------------
# Unit tests: basic correctness
# ---------------------------------------------------------------------------

class TestMeasurementEngineBasic:

    def test_returns_list_of_grain_measurements(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        results = engine.measure(mask)
        assert isinstance(results, list)
        assert all(isinstance(m, GrainMeasurement) for m in results)

    def test_single_grain_returns_one_measurement(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        results = engine.measure(mask)
        assert len(results) == 1

    def test_multi_grain_count_matches_labels(self):
        n = 4
        mask = make_multi_grain_mask(n)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        assert len(results) == n

    def test_grain_ids_match_mask_labels(self):
        n = 3
        mask = make_multi_grain_mask(n)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        result_ids = {m.grain_id for m in results}
        expected_ids = set(range(1, n + 1))
        assert result_ids == expected_ids

    def test_empty_mask_returns_empty_list(self):
        mask = np.zeros((20, 20), dtype=np.int32)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        assert results == []

    def test_area_is_positive(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert m.area > 0

    def test_perimeter_is_positive(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert m.perimeter > 0

    def test_circularity_between_zero_and_one(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert 0 < m.circularity <= 1.0

    def test_roundness_between_zero_and_one(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert 0 < m.roundness <= 1.0

    def test_feret_diameter_positive(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert m.feret_diameter > 0

    def test_major_axis_gte_minor_axis(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert m.major_axis >= m.minor_axis > 0

    def test_feret_diameter_gte_major_axis(self):
        """Feret diameter (max caliper) must be >= major axis length."""
        mask = make_circular_mask(radius=15)
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        # Allow small floating-point tolerance
        assert m.feret_diameter >= m.major_axis - 1e-6

    def test_unit_is_pixels_without_scale(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask)[0]
        assert m.unit == MeasurementUnit.PIXELS
        assert m.scale_factor is None

    def test_unit_is_mm_with_scale(self):
        mask = make_circular_mask()
        engine = MeasurementEngine()
        m = engine.measure(mask, scale_ppm=10.0)[0]
        assert m.unit == MeasurementUnit.MILLIMETERS
        assert m.scale_factor == 10.0


# ---------------------------------------------------------------------------
# Unit tests: scale conversion
# ---------------------------------------------------------------------------

class TestMeasurementEngineScaleConversion:

    def test_area_converted_by_scale_squared(self):
        """Area in mm² = area_px / scale_ppm²."""
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=5.0)

        area_px = px_results[0].area
        area_mm = mm_results[0].area
        assert abs(area_mm - area_px / 25.0) < 1e-6

    def test_perimeter_converted_by_scale(self):
        """Perimeter in mm = perimeter_px / scale_ppm."""
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=4.0)

        perim_px = px_results[0].perimeter
        perim_mm = mm_results[0].perimeter
        assert abs(perim_mm - perim_px / 4.0) < 1e-6

    def test_major_axis_converted_by_scale(self):
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px = engine.measure(mask)[0]
        mm = engine.measure(mask, scale_ppm=2.0)[0]
        assert abs(mm.major_axis - px.major_axis / 2.0) < 1e-6

    def test_minor_axis_converted_by_scale(self):
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px = engine.measure(mask)[0]
        mm = engine.measure(mask, scale_ppm=2.0)[0]
        assert abs(mm.minor_axis - px.minor_axis / 2.0) < 1e-6

    def test_feret_diameter_converted_by_scale(self):
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px = engine.measure(mask)[0]
        mm = engine.measure(mask, scale_ppm=2.0)[0]
        assert abs(mm.feret_diameter - px.feret_diameter / 2.0) < 1e-6

    def test_circularity_unchanged_by_scale(self):
        """Circularity is dimensionless; scale must not change it."""
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px = engine.measure(mask)[0]
        mm = engine.measure(mask, scale_ppm=7.0)[0]
        assert abs(mm.circularity - px.circularity) < 1e-9

    def test_roundness_unchanged_by_scale(self):
        """Roundness is dimensionless; scale must not change it."""
        mask = make_circular_mask(radius=10)
        engine = MeasurementEngine()
        px = engine.measure(mask)[0]
        mm = engine.measure(mask, scale_ppm=7.0)[0]
        assert abs(mm.roundness - px.roundness) < 1e-9


# ---------------------------------------------------------------------------
# Unit tests: error handling
# ---------------------------------------------------------------------------

class TestMeasurementEngineErrors:

    def test_3d_mask_raises_measurement_error(self):
        """A 3-D array is not a valid mask."""
        engine = MeasurementEngine()
        bad_mask = np.zeros((10, 10, 3), dtype=np.int32)
        with pytest.raises(MeasurementError):
            engine.measure(bad_mask)

    def test_filename_appears_in_error_message(self):
        engine = MeasurementEngine()
        bad_mask = np.zeros((5, 5, 2), dtype=np.int32)
        with pytest.raises(MeasurementError) as exc_info:
            engine.measure(bad_mask, filename="bad_image.jpg")
        assert "bad_image.jpg" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Lazy initialisation
# ---------------------------------------------------------------------------

class TestMeasurementEngineLazyInit:

    def test_ij_is_none_on_construction(self):
        """PyImageJ handle should not be initialised at construction time."""
        engine = MeasurementEngine()
        assert engine._ij is None


# ---------------------------------------------------------------------------
# Helpers for property tests
# ---------------------------------------------------------------------------

def make_non_overlapping_grain_mask(grain_count: int, grain_radius: int = 4) -> np.ndarray:
    """
    Build a mask with *grain_count* non-overlapping circular grains arranged
    in a grid. Each grain has a unique positive integer label; 0 = background.

    Returns a 2-D int32 array.
    """
    if grain_count == 0:
        return np.zeros((20, 20), dtype=np.int32)

    spacing = 2 * grain_radius + 4
    cols = max(1, int(np.ceil(np.sqrt(grain_count))))
    rows = max(1, int(np.ceil(grain_count / cols)))
    height = rows * spacing + spacing
    width = cols * spacing + spacing
    mask = np.zeros((height, width), dtype=np.int32)

    label = 1
    for row in range(rows):
        for col in range(cols):
            if label > grain_count:
                break
            cy = spacing // 2 + row * spacing
            cx = spacing // 2 + col * spacing
            y_idx, x_idx = np.ogrid[:height, :width]
            mask[(x_idx - cx) ** 2 + (y_idx - cy) ** 2 <= grain_radius ** 2] = label
            label += 1

    return mask


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestMeasurementCountConsistency:
    """
    Property 7: Measurement Count Consistency

    For any segmentation mask with N unique positive labels (grains),
    MeasurementEngine.measure() SHALL return exactly N GrainMeasurement
    objects, and each measurement SHALL have a unique grain_id corresponding
    to a label present in the mask.

    Validates: Requirements 3.1
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(grain_count=st.integers(min_value=0, max_value=20))
    def test_property_measurement_count_equals_grain_labels(self, grain_count):
        """
        Property 7a: measure() returns exactly N measurements for a mask
        with N unique positive labels.
        """
        mask = make_non_overlapping_grain_mask(grain_count)
        engine = MeasurementEngine()

        results = engine.measure(mask)

        unique_positive_labels = set(np.unique(mask[mask > 0]).tolist())
        assert len(results) == len(unique_positive_labels), (
            f"Expected {len(unique_positive_labels)} measurements for "
            f"{grain_count} grains, got {len(results)}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(grain_count=st.integers(min_value=1, max_value=20))
    def test_property_grain_ids_match_mask_labels(self, grain_count):
        """
        Property 7b: Each GrainMeasurement.grain_id corresponds to a label
        that exists in the mask, and all grain_ids are unique.
        """
        mask = make_non_overlapping_grain_mask(grain_count)
        engine = MeasurementEngine()

        results = engine.measure(mask)

        mask_labels = set(np.unique(mask[mask > 0]).tolist())
        result_ids = [m.grain_id for m in results]

        # All returned grain_ids must be present in the mask
        for gid in result_ids:
            assert gid in mask_labels, (
                f"grain_id {gid} not found in mask labels {mask_labels}"
            )

        # grain_ids must be unique (no duplicates)
        assert len(result_ids) == len(set(result_ids)), (
            f"Duplicate grain_ids found: {result_ids}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(grain_count=st.integers(min_value=1, max_value=20))
    def test_property_all_mask_labels_have_measurement(self, grain_count):
        """
        Property 7c: Every unique positive label in the mask has a
        corresponding GrainMeasurement (no label is silently dropped).
        """
        mask = make_non_overlapping_grain_mask(grain_count)
        engine = MeasurementEngine()

        results = engine.measure(mask)

        mask_labels = set(np.unique(mask[mask > 0]).tolist())
        result_ids = {m.grain_id for m in results}

        assert mask_labels == result_ids, (
            f"Mask labels {mask_labels} do not match measurement ids {result_ids}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(grain_count=st.integers(min_value=0, max_value=20))
    def test_property_empty_mask_returns_empty_list(self, grain_count):
        """
        Property 7d: A mask with no positive labels (all zeros) always
        returns an empty list, regardless of mask dimensions.
        """
        # Build a mask of varying size but force all zeros
        size = max(4, grain_count * 2 + 4)
        mask = np.zeros((size, size), dtype=np.int32)
        engine = MeasurementEngine()

        results = engine.measure(mask)

        assert results == [], (
            f"Expected empty list for all-zero mask, got {len(results)} measurements"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        scale_ppm=st.one_of(st.none(), st.floats(min_value=0.1, max_value=100.0)),
    )
    def test_property_count_invariant_under_scale(self, grain_count, scale_ppm):
        """
        Property 7e: The number of measurements is invariant under scale
        conversion — applying scale_ppm does not add or remove measurements.
        """
        mask = make_non_overlapping_grain_mask(grain_count)
        engine = MeasurementEngine()

        results = engine.measure(mask, scale_ppm=scale_ppm)

        unique_positive_labels = set(np.unique(mask[mask > 0]).tolist())
        assert len(results) == len(unique_positive_labels), (
            f"scale_ppm={scale_ppm}: expected {len(unique_positive_labels)} "
            f"measurements, got {len(results)}"
        )


class TestMeasurementValueInvariants:
    """
    Property 8: Measurement Value Invariants

    For any GrainMeasurement returned by the MeasurementEngine:
    - area > 0
    - perimeter > 0
    - 0 < circularity <= 1
    - 0 < roundness <= 1
    - feret_diameter > 0
    - major_axis >= minor_axis > 0
    - feret_diameter >= major_axis

    Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_area_positive(self, grain_count, grain_radius):
        """Property 8a: area > 0 for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert m.area > 0, f"grain_id={m.grain_id}: area={m.area} is not > 0"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_perimeter_positive(self, grain_count, grain_radius):
        """Property 8b: perimeter > 0 for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert m.perimeter > 0, f"grain_id={m.grain_id}: perimeter={m.perimeter} is not > 0"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_circularity_in_range(self, grain_count, grain_radius):
        """Property 8c: 0 < circularity <= 1 for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert 0 < m.circularity <= 1.0, (
                f"grain_id={m.grain_id}: circularity={m.circularity} out of range (0, 1]"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_roundness_in_range(self, grain_count, grain_radius):
        """Property 8d: 0 < roundness <= 1 for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert 0 < m.roundness <= 1.0, (
                f"grain_id={m.grain_id}: roundness={m.roundness} out of range (0, 1]"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_feret_diameter_positive(self, grain_count, grain_radius):
        """Property 8e: feret_diameter > 0 for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert m.feret_diameter > 0, (
                f"grain_id={m.grain_id}: feret_diameter={m.feret_diameter} is not > 0"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_major_axis_gte_minor_axis(self, grain_count, grain_radius):
        """Property 8f: major_axis >= minor_axis > 0 for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert m.minor_axis > 0, (
                f"grain_id={m.grain_id}: minor_axis={m.minor_axis} is not > 0"
            )
            assert m.major_axis >= m.minor_axis, (
                f"grain_id={m.grain_id}: major_axis={m.major_axis} < minor_axis={m.minor_axis}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
    )
    def test_property_feret_gte_major_axis(self, grain_count, grain_radius):
        """Property 8g: feret_diameter >= major_axis for every grain measurement."""
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask)
        for m in results:
            assert m.feret_diameter >= m.major_axis - 1e-6, (
                f"grain_id={m.grain_id}: feret_diameter={m.feret_diameter} < major_axis={m.major_axis}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=15),
        grain_radius=st.integers(min_value=3, max_value=12),
        scale_ppm=st.floats(min_value=0.5, max_value=50.0),
    )
    def test_property_invariants_hold_under_scale(self, grain_count, grain_radius, scale_ppm):
        """
        Property 8h: All value invariants hold regardless of scale_ppm.
        Scaling changes magnitudes but must not violate any invariant.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()
        results = engine.measure(mask, scale_ppm=scale_ppm)
        for m in results:
            assert m.area > 0
            assert m.perimeter > 0
            assert 0 < m.circularity <= 1.0
            assert 0 < m.roundness <= 1.0
            assert m.feret_diameter > 0
            assert m.minor_axis > 0
            assert m.major_axis >= m.minor_axis
            assert m.feret_diameter >= m.major_axis - 1e-6


class TestScaleConversionCorrectness:
    """
    Property 9: Scale Conversion Correctness

    For any measurement with scale_ppm = S (where S > 0):
    - Length measurements (perimeter, feret_diameter, major_axis, minor_axis)
      in mm SHALL equal pixel_value / S
    - Area measurement in mm² SHALL equal pixel_area / S²
    - Circularity and roundness SHALL remain unchanged (dimensionless ratios)

    Validates: Requirements 3.8, 10.1, 10.2
    # Feature: sedimental-analysis-tool
    # Tags: property-9, scale-conversion, requirements-3.8, requirements-10.1, requirements-10.2
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_area_equals_pixel_area_divided_by_scale_squared(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9a: area_mm = area_px / S²

        Area scales with the square of the linear scale factor.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            expected = px.area / (scale_ppm ** 2)
            assert abs(mm.area - expected) < 1e-6, (
                f"grain_id={mm.grain_id}: area_mm={mm.area} != "
                f"area_px/S²={expected} (scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_perimeter_equals_pixel_perimeter_divided_by_scale(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9b: perimeter_mm = perimeter_px / S

        Perimeter is a length measurement and scales linearly.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            expected = px.perimeter / scale_ppm
            assert abs(mm.perimeter - expected) < 1e-6, (
                f"grain_id={mm.grain_id}: perimeter_mm={mm.perimeter} != "
                f"perimeter_px/S={expected} (scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_feret_diameter_equals_pixel_feret_divided_by_scale(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9c: feret_diameter_mm = feret_diameter_px / S

        Feret diameter is a length measurement and scales linearly.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            expected = px.feret_diameter / scale_ppm
            assert abs(mm.feret_diameter - expected) < 1e-6, (
                f"grain_id={mm.grain_id}: feret_diameter_mm={mm.feret_diameter} != "
                f"feret_px/S={expected} (scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_major_axis_equals_pixel_major_axis_divided_by_scale(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9d: major_axis_mm = major_axis_px / S

        Major axis is a length measurement and scales linearly.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            expected = px.major_axis / scale_ppm
            assert abs(mm.major_axis - expected) < 1e-6, (
                f"grain_id={mm.grain_id}: major_axis_mm={mm.major_axis} != "
                f"major_axis_px/S={expected} (scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_minor_axis_equals_pixel_minor_axis_divided_by_scale(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9e: minor_axis_mm = minor_axis_px / S

        Minor axis is a length measurement and scales linearly.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            expected = px.minor_axis / scale_ppm
            assert abs(mm.minor_axis - expected) < 1e-6, (
                f"grain_id={mm.grain_id}: minor_axis_mm={mm.minor_axis} != "
                f"minor_axis_px/S={expected} (scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_circularity_unchanged_by_scale(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9f: circularity is dimensionless and SHALL be identical
        regardless of scale_ppm.

        circularity = 4π×area/perimeter². When both area and perimeter are
        scaled (area/S², perimeter/S), the S terms cancel out:
        4π×(area/S²)/(perimeter/S)² = 4π×area/perimeter²
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            assert abs(mm.circularity - px.circularity) < 1e-9, (
                f"grain_id={mm.grain_id}: circularity changed under scale "
                f"(px={px.circularity}, mm={mm.circularity}, scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_roundness_unchanged_by_scale(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9g: roundness is dimensionless and SHALL be identical
        regardless of scale_ppm.

        roundness = 4×area/(π×major_axis²). When area scales by 1/S² and
        major_axis scales by 1/S, the S terms cancel out:
        4×(area/S²)/(π×(major_axis/S)²) = 4×area/(π×major_axis²)
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        px_results = engine.measure(mask)
        mm_results = engine.measure(mask, scale_ppm=scale_ppm)

        px_by_id = {m.grain_id: m for m in px_results}
        for mm in mm_results:
            px = px_by_id[mm.grain_id]
            assert abs(mm.roundness - px.roundness) < 1e-9, (
                f"grain_id={mm.grain_id}: roundness changed under scale "
                f"(px={px.roundness}, mm={mm.roundness}, scale_ppm={scale_ppm})"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
        scale_ppm=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    )
    def test_property_unit_is_mm_when_scale_provided(
        self, grain_count, grain_radius, scale_ppm
    ):
        """
        Property 9h: unit SHALL be MILLIMETERS and scale_factor SHALL equal
        scale_ppm when a scale is provided.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        results = engine.measure(mask, scale_ppm=scale_ppm)

        for m in results:
            assert m.unit == MeasurementUnit.MILLIMETERS, (
                f"grain_id={m.grain_id}: expected unit=MILLIMETERS, got {m.unit}"
            )
            assert m.scale_factor == scale_ppm, (
                f"grain_id={m.grain_id}: expected scale_factor={scale_ppm}, got {m.scale_factor}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        grain_count=st.integers(min_value=1, max_value=10),
        grain_radius=st.integers(min_value=4, max_value=12),
    )
    def test_property_unit_is_pixels_when_no_scale(self, grain_count, grain_radius):
        """
        Property 9i: unit SHALL be PIXELS and scale_factor SHALL be None
        when no scale_ppm is provided.
        """
        mask = make_non_overlapping_grain_mask(grain_count, grain_radius)
        engine = MeasurementEngine()

        results = engine.measure(mask)

        for m in results:
            assert m.unit == MeasurementUnit.PIXELS, (
                f"grain_id={m.grain_id}: expected unit=PIXELS, got {m.unit}"
            )
            assert m.scale_factor is None, (
                f"grain_id={m.grain_id}: expected scale_factor=None, got {m.scale_factor}"
            )
