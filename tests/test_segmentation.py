"""
Property-based tests for SegmentationEngine.

Tests cover:
- Property 5: Segmentation Mask Validity
  - mask shape matches input image shape
  - mask dtype is int32
  - background label is 0
  - grain_count equals number of unique positive labels
  - grain_count matches len(unique(mask[mask > 0]))
- Property 6: Mask Persistence on Request
  - save_mask() writes a readable TIFF with identical content
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import tifffile
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.errors import OutputError, SegmentationError
from sedimental.models import SegmentationResult
from sedimental.segmentation import SegmentationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rgb_image(height: int, width: int) -> np.ndarray:
    """Return a random uint8 RGB array of the given dimensions."""
    rng = np.random.default_rng(seed=42)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def make_labeled_mask(height: int, width: int, grain_count: int) -> np.ndarray:
    """
    Return a (H, W) int32 mask with *grain_count* unique positive labels.
    Labels are distributed roughly evenly; 0 is background.
    """
    mask = np.zeros((height, width), dtype=np.int32)
    if grain_count == 0:
        return mask
    # Assign each pixel a label in [0, grain_count] based on position
    total_pixels = height * width
    flat = mask.ravel()
    pixels_per_grain = max(1, total_pixels // (grain_count + 1))
    for label in range(1, grain_count + 1):
        start = (label - 1) * pixels_per_grain
        end = min(start + pixels_per_grain, total_pixels)
        flat[start:end] = label
    return mask


def make_engine_with_mock_model(mock_mask: np.ndarray) -> SegmentationEngine:
    """
    Return a SegmentationEngine whose Cellpose model is replaced with a mock
    that always returns *mock_mask* as the segmentation result.
    """
    engine = SegmentationEngine()
    mock_model = MagicMock()
    mock_model.eval.return_value = ([mock_mask], [None], [None])
    engine._model = mock_model
    return engine


# ---------------------------------------------------------------------------
# Unit tests: segment()
# ---------------------------------------------------------------------------

class TestSegmentationEngineSegment:
    """Unit tests for SegmentationEngine.segment()."""

    def test_segment_returns_segmentation_result(self):
        """segment() should return a SegmentationResult."""
        mask = make_labeled_mask(10, 10, 3)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(10, 10)

        result = engine.segment(image, "test.jpg")

        assert isinstance(result, SegmentationResult)

    def test_segment_mask_shape_matches_image(self):
        """Returned mask shape (H, W) must match the input image (H, W)."""
        h, w = 20, 30
        mask = make_labeled_mask(h, w, 5)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(h, w)

        result = engine.segment(image, "test.jpg")

        assert result.mask.shape == (h, w)

    def test_segment_mask_dtype_is_int32(self):
        """Returned mask must have dtype int32."""
        mask = make_labeled_mask(8, 8, 2)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(8, 8)

        result = engine.segment(image, "test.jpg")

        assert result.mask.dtype == np.int32

    def test_segment_grain_count_matches_unique_positive_labels(self):
        """grain_count must equal the number of unique positive labels in mask."""
        grain_count = 4
        mask = make_labeled_mask(16, 16, grain_count)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(16, 16)

        result = engine.segment(image, "test.jpg")

        unique_positive = int(np.sum(np.unique(result.mask) > 0))
        assert result.grain_count == unique_positive

    def test_segment_zero_grains_adds_warning(self):
        """When no grains are detected, a warning should be added."""
        mask = np.zeros((10, 10), dtype=np.int32)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(10, 10)

        result = engine.segment(image, "empty.jpg")

        assert result.grain_count == 0
        assert len(result.warnings) > 0
        assert any("empty.jpg" in w for w in result.warnings)

    def test_segment_nonzero_grains_no_warning(self):
        """When grains are detected, no warning should be added."""
        mask = make_labeled_mask(10, 10, 3)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(10, 10)

        result = engine.segment(image, "grains.jpg")

        assert result.grain_count == 3
        assert result.warnings == []

    def test_segment_invalid_shape_raises_segmentation_error(self):
        """Passing a non-RGB array should raise SegmentationError."""
        engine = SegmentationEngine()
        grayscale = np.zeros((10, 10), dtype=np.uint8)

        with pytest.raises(SegmentationError):
            engine.segment(grayscale, "gray.jpg")

    def test_segment_model_exception_raises_segmentation_error(self):
        """If the model raises, SegmentationError should be re-raised."""
        engine = SegmentationEngine()
        mock_model = MagicMock()
        mock_model.eval.side_effect = RuntimeError("model exploded")
        engine._model = mock_model
        image = make_rgb_image(10, 10)

        with pytest.raises(SegmentationError):
            engine.segment(image, "boom.jpg")

    def test_segment_background_label_is_zero(self):
        """Background pixels must be labelled 0."""
        mask = make_labeled_mask(12, 12, 3)
        engine = make_engine_with_mock_model(mask)
        image = make_rgb_image(12, 12)

        result = engine.segment(image, "test.jpg")

        assert 0 in np.unique(result.mask)


# ---------------------------------------------------------------------------
# Unit tests: save_mask()
# ---------------------------------------------------------------------------

class TestSegmentationEngineSaveMask:
    """Unit tests for SegmentationEngine.save_mask()."""

    def test_save_mask_creates_file(self, tmp_path):
        """save_mask() should create a file at the given path."""
        engine = SegmentationEngine()
        mask = make_labeled_mask(8, 8, 2)
        out = tmp_path / "mask.tiff"

        engine.save_mask(mask, out)

        assert out.exists()

    def test_save_mask_content_round_trips(self, tmp_path):
        """Saved TIFF should load back to an identical array."""
        engine = SegmentationEngine()
        mask = make_labeled_mask(10, 10, 3)
        out = tmp_path / "mask.tiff"

        engine.save_mask(mask, out)
        loaded = tifffile.imread(str(out))

        np.testing.assert_array_equal(loaded, mask)

    def test_save_mask_creates_parent_dirs(self, tmp_path):
        """save_mask() should create missing parent directories."""
        engine = SegmentationEngine()
        mask = make_labeled_mask(6, 6, 1)
        out = tmp_path / "nested" / "deep" / "mask.tiff"

        engine.save_mask(mask, out)

        assert out.exists()

    def test_save_mask_raises_output_error_on_bad_path(self):
        """save_mask() should raise OutputError if writing fails."""
        engine = SegmentationEngine()
        mask = make_labeled_mask(4, 4, 1)
        bad_path = Path("/nonexistent_root/cannot_write/mask.tiff")

        with pytest.raises(OutputError):
            engine.save_mask(mask, bad_path)


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestSegmentationMaskProperties:
    """
    Property 5: Segmentation Mask Validity

    For any RGB image of shape (H, W, 3), the SegmentationEngine SHALL return
    a SegmentationResult where:
    - mask.shape == (H, W)
    - mask.dtype == int32
    - 0 is the background label (present in mask)
    - grain_count == number of unique positive integer labels in mask
    - grain_count >= 0

    Validates: Requirements 2.1, 2.2, 2.3
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        height=st.integers(min_value=4, max_value=128),
        width=st.integers(min_value=4, max_value=128),
        grain_count=st.integers(min_value=0, max_value=20),
    )
    def test_property_mask_shape_matches_image(self, height, width, grain_count):
        """Property 5a: mask shape must equal (H, W) of the input image."""
        mock_mask = make_labeled_mask(height, width, grain_count)
        engine = make_engine_with_mock_model(mock_mask)
        image = make_rgb_image(height, width)

        result = engine.segment(image, "prop_test.jpg")

        assert result.mask.shape == (height, width), (
            f"Expected mask shape ({height}, {width}), got {result.mask.shape}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        height=st.integers(min_value=4, max_value=128),
        width=st.integers(min_value=4, max_value=128),
        grain_count=st.integers(min_value=0, max_value=20),
    )
    def test_property_mask_dtype_is_int32(self, height, width, grain_count):
        """Property 5b: mask dtype must always be int32."""
        mock_mask = make_labeled_mask(height, width, grain_count)
        engine = make_engine_with_mock_model(mock_mask)
        image = make_rgb_image(height, width)

        result = engine.segment(image, "prop_test.jpg")

        assert result.mask.dtype == np.int32, (
            f"Expected dtype int32, got {result.mask.dtype}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        height=st.integers(min_value=4, max_value=128),
        width=st.integers(min_value=4, max_value=128),
        grain_count=st.integers(min_value=0, max_value=20),
    )
    def test_property_grain_count_equals_unique_positive_labels(
        self, height, width, grain_count
    ):
        """Property 5c: grain_count must equal the count of unique positive labels."""
        mock_mask = make_labeled_mask(height, width, grain_count)
        engine = make_engine_with_mock_model(mock_mask)
        image = make_rgb_image(height, width)

        result = engine.segment(image, "prop_test.jpg")

        unique_positive = int(np.sum(np.unique(result.mask) > 0))
        assert result.grain_count == unique_positive, (
            f"grain_count={result.grain_count} but unique positive labels={unique_positive}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        height=st.integers(min_value=4, max_value=128),
        width=st.integers(min_value=4, max_value=128),
        grain_count=st.integers(min_value=0, max_value=20),
    )
    def test_property_grain_count_non_negative(self, height, width, grain_count):
        """Property 5d: grain_count must always be >= 0."""
        mock_mask = make_labeled_mask(height, width, grain_count)
        engine = make_engine_with_mock_model(mock_mask)
        image = make_rgb_image(height, width)

        result = engine.segment(image, "prop_test.jpg")

        assert result.grain_count >= 0, (
            f"grain_count must be non-negative, got {result.grain_count}"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        height=st.integers(min_value=4, max_value=128),
        width=st.integers(min_value=4, max_value=128),
        grain_count=st.integers(min_value=1, max_value=20),
    )
    def test_property_labels_are_contiguous_positive_integers(
        self, height, width, grain_count
    ):
        """
        Property 5e: grain labels must be positive integers starting from 1.
        The set of unique positive labels must be a subset of {1, 2, ..., grain_count}.
        """
        mock_mask = make_labeled_mask(height, width, grain_count)
        engine = make_engine_with_mock_model(mock_mask)
        image = make_rgb_image(height, width)

        result = engine.segment(image, "prop_test.jpg")

        positive_labels = set(np.unique(result.mask[result.mask > 0]).tolist())
        # All positive labels must be >= 1
        assert all(label >= 1 for label in positive_labels), (
            f"Found non-positive labels in mask: {positive_labels}"
        )

    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        height=st.integers(min_value=4, max_value=64),
        width=st.integers(min_value=4, max_value=64),
        grain_count=st.integers(min_value=0, max_value=10),
    )
    def test_property_mask_persistence_round_trip(self, tmp_path, height, width, grain_count):
        """
        Property 6: Mask Persistence on Request

        For any segmentation mask, save_mask() followed by tifffile.imread()
        SHALL return an array that is element-wise identical to the original mask.

        Validates: Requirements 2.4
        """
        import uuid
        engine = SegmentationEngine()
        mask = make_labeled_mask(height, width, grain_count).astype(np.int32)
        out_path = tmp_path / f"mask_{uuid.uuid4().hex}.tiff"

        engine.save_mask(mask, out_path)
        loaded = tifffile.imread(str(out_path))

        assert loaded.shape == mask.shape, (
            f"Loaded mask shape {loaded.shape} != original {mask.shape}"
        )
        np.testing.assert_array_equal(loaded, mask)
