"""
Unit tests for ImageLoader class.

Tests cover:
- Loading valid JPEG images
- Raising InvalidImageError for corrupted/non-JPEG files
- Raising FileNotFoundError for missing files
- discover_images() directory scanning
- Case-insensitive extension handling
- Warning logs for non-JPEG files
"""

import io
import logging
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from sedimental.errors import InvalidImageError
from sedimental.loader import ImageLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_jpeg(path: Path, width: int = 10, height: int = 8) -> Path:
    """Create a minimal valid JPEG file at *path* and return the path."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    img.save(path, format="JPEG")
    return path


def make_png(path: Path, width: int = 4, height: int = 4) -> Path:
    """Create a minimal PNG file at *path* and return the path."""
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    img.save(path, format="PNG")
    return path


def make_corrupted(path: Path) -> Path:
    """Write garbage bytes that look like a JPEG header but are corrupted."""
    # JPEG magic bytes followed by garbage
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20 + b"garbage data here")
    return path


def make_text_file(path: Path) -> Path:
    """Create a plain text file."""
    path.write_text("this is not an image")
    return path


# ---------------------------------------------------------------------------
# Tests: load()
# ---------------------------------------------------------------------------

class TestImageLoaderLoad:
    """Tests for ImageLoader.load()."""

    def test_load_valid_jpeg_returns_ndarray(self, tmp_path):
        """A valid JPEG should be loaded as a numpy array."""
        loader = ImageLoader()
        img_path = make_jpeg(tmp_path / "sample.jpg")

        result = loader.load(img_path)

        assert isinstance(result, np.ndarray)

    def test_load_valid_jpeg_shape(self, tmp_path):
        """Loaded image should have shape (H, W, 3)."""
        loader = ImageLoader()
        img_path = make_jpeg(tmp_path / "sample.jpg", width=20, height=15)

        result = loader.load(img_path)

        assert result.ndim == 3
        assert result.shape[2] == 3
        assert result.shape[0] == 15  # height
        assert result.shape[1] == 20  # width

    def test_load_jpeg_extension_case_insensitive(self, tmp_path):
        """Both .jpg and .jpeg extensions should be loadable."""
        loader = ImageLoader()

        jpg_path = make_jpeg(tmp_path / "a.jpg")
        jpeg_path = make_jpeg(tmp_path / "b.jpeg")

        arr_jpg = loader.load(jpg_path)
        arr_jpeg = loader.load(jpeg_path)

        assert arr_jpg.shape[2] == 3
        assert arr_jpeg.shape[2] == 3

    def test_load_missing_file_raises_file_not_found(self, tmp_path):
        """Loading a non-existent file should raise FileNotFoundError."""
        loader = ImageLoader()
        missing = tmp_path / "does_not_exist.jpg"

        with pytest.raises(FileNotFoundError):
            loader.load(missing)

    def test_load_corrupted_jpeg_raises_invalid_image_error(self, tmp_path):
        """A corrupted JPEG should raise InvalidImageError."""
        loader = ImageLoader()
        bad_path = make_corrupted(tmp_path / "bad.jpg")

        with pytest.raises(InvalidImageError):
            loader.load(bad_path)

    def test_load_invalid_image_error_contains_filename(self, tmp_path):
        """InvalidImageError message should contain the filename."""
        loader = ImageLoader()
        bad_path = make_corrupted(tmp_path / "corrupted_sample.jpg")

        with pytest.raises(InvalidImageError) as exc_info:
            loader.load(bad_path)

        assert "corrupted_sample.jpg" in str(exc_info.value)

    def test_load_png_file_raises_invalid_image_error(self, tmp_path):
        """A PNG file (not JPEG) should raise InvalidImageError."""
        loader = ImageLoader()
        png_path = make_png(tmp_path / "image.png")

        with pytest.raises(InvalidImageError):
            loader.load(png_path)

    def test_load_text_file_raises_invalid_image_error(self, tmp_path):
        """A plain text file should raise InvalidImageError."""
        loader = ImageLoader()
        txt_path = make_text_file(tmp_path / "not_an_image.jpg")

        with pytest.raises(InvalidImageError):
            loader.load(txt_path)

    def test_load_returns_rgb_array(self, tmp_path):
        """Loaded image should be an RGB array (dtype uint8, values 0-255)."""
        loader = ImageLoader()
        img_path = make_jpeg(tmp_path / "color.jpg", width=5, height=5)

        result = loader.load(img_path)

        assert result.dtype == np.uint8
        assert result.min() >= 0
        assert result.max() <= 255


# ---------------------------------------------------------------------------
# Tests: discover_images()
# ---------------------------------------------------------------------------

class TestImageLoaderDiscoverImages:
    """Tests for ImageLoader.discover_images()."""

    def test_discover_returns_jpeg_files(self, tmp_path):
        """discover_images() should return .jpg and .jpeg files."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "a.jpg")
        make_jpeg(tmp_path / "b.jpeg")

        result = loader.discover_images(tmp_path)

        names = {p.name for p in result}
        assert "a.jpg" in names
        assert "b.jpeg" in names

    def test_discover_excludes_non_jpeg(self, tmp_path):
        """discover_images() should not return non-JPEG files."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "good.jpg")
        make_png(tmp_path / "bad.png")
        make_text_file(tmp_path / "notes.txt")

        result = loader.discover_images(tmp_path)

        names = {p.name for p in result}
        assert "good.jpg" in names
        assert "bad.png" not in names
        assert "notes.txt" not in names

    def test_discover_empty_directory(self, tmp_path):
        """discover_images() on an empty directory should return empty list."""
        loader = ImageLoader()

        result = loader.discover_images(tmp_path)

        assert result == []

    def test_discover_count_matches_jpeg_files(self, tmp_path):
        """Number of returned paths should equal number of JPEG files."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "one.jpg")
        make_jpeg(tmp_path / "two.jpg")
        make_jpeg(tmp_path / "three.jpeg")
        make_png(tmp_path / "ignore.png")

        result = loader.discover_images(tmp_path)

        assert len(result) == 3

    def test_discover_case_insensitive_extensions(self, tmp_path):
        """discover_images() should find .JPG and .JPEG (uppercase) files."""
        loader = ImageLoader()
        # Create files with uppercase extensions by writing bytes directly
        upper_jpg = tmp_path / "UPPER.JPG"
        make_jpeg(upper_jpg)
        upper_jpeg = tmp_path / "UPPER2.JPEG"
        make_jpeg(upper_jpeg)

        result = loader.discover_images(tmp_path)

        names = {p.name for p in result}
        assert "UPPER.JPG" in names
        assert "UPPER2.JPEG" in names

    def test_discover_returns_path_objects(self, tmp_path):
        """discover_images() should return a list of Path objects."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "img.jpg")

        result = loader.discover_images(tmp_path)

        assert all(isinstance(p, Path) for p in result)

    def test_discover_non_recursive(self, tmp_path):
        """discover_images() should not recurse into subdirectories."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "top.jpg")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        make_jpeg(subdir / "nested.jpg")

        result = loader.discover_images(tmp_path)

        names = {p.name for p in result}
        assert "top.jpg" in names
        assert "nested.jpg" not in names

    def test_discover_logs_warning_for_non_jpeg(self, tmp_path, caplog):
        """discover_images() should log a warning for non-JPEG files."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "good.jpg")
        make_text_file(tmp_path / "readme.txt")

        with caplog.at_level(logging.WARNING, logger="sedimental.loader"):
            loader.discover_images(tmp_path)

        assert any("readme.txt" in record.message for record in caplog.records)

    def test_discover_no_warning_for_jpeg_only(self, tmp_path, caplog):
        """discover_images() should not log warnings when all files are JPEGs."""
        loader = ImageLoader()
        make_jpeg(tmp_path / "a.jpg")
        make_jpeg(tmp_path / "b.jpeg")

        with caplog.at_level(logging.WARNING, logger="sedimental.loader"):
            loader.discover_images(tmp_path)

        assert len(caplog.records) == 0


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

# **Validates: Requirements 1.1**
class TestImageLoaderProperties:
    """Property-based tests for ImageLoader using Hypothesis."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        width=st.integers(min_value=1, max_value=256),
        height=st.integers(min_value=1, max_value=256),
        r=st.integers(min_value=0, max_value=255),
        g=st.integers(min_value=0, max_value=255),
        b=st.integers(min_value=0, max_value=255),
    )
    def test_property_valid_jpeg_acceptance(self, tmp_path, width, height, r, g, b):
        """Property 1: Valid JPEG Acceptance.

        For any valid JPEG image file, ImageLoader SHALL successfully load it
        and return a numpy array with shape (H, W, 3) where H > 0 and W > 0.

        **Validates: Requirements 1.1**
        """
        # Build a valid JPEG in memory and write to a temp file
        buf = io.BytesIO()
        img = Image.new("RGB", (width, height), color=(r, g, b))
        img.save(buf, format="JPEG")
        buf.seek(0)

        jpeg_path = tmp_path / f"test_{width}x{height}.jpg"
        jpeg_path.write_bytes(buf.read())

        loader = ImageLoader()
        result = loader.load(jpeg_path)

        # Must be a numpy array
        assert isinstance(result, np.ndarray)
        # Must have exactly 3 dimensions
        assert result.ndim == 3
        # Height and width must be positive
        assert result.shape[0] > 0
        assert result.shape[1] > 0
        # Must have 3 colour channels (RGB)
        assert result.shape[2] == 3

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        jpeg_names=st.lists(
            st.from_regex(r"[a-z]{1,8}", fullmatch=True),
            min_size=0,
            max_size=10,
            unique=True,
        ),
        extensions=st.lists(
            st.sampled_from([".jpg", ".jpeg", ".JPG", ".JPEG"]),
            min_size=0,
            max_size=10,
        ),
        non_jpeg_names=st.lists(
            st.from_regex(r"[a-z]{1,8}", fullmatch=True),
            min_size=0,
            max_size=5,
            unique=True,
        ),
    )
    def test_property_directory_jpeg_discovery(
        self, tmp_path, jpeg_names, extensions, non_jpeg_names
    ):
        """Property 2: Directory JPEG Discovery.

        For any directory containing N JPEG files (with extensions .jpg or
        .jpeg, case-insensitive), discover_images() SHALL return exactly N
        file paths, and all returned paths SHALL have JPEG extensions.

        **Validates: Requirements 1.2, 9.1**
        """
        # Use a fresh subdirectory per example so files from previous
        # Hypothesis examples don't accumulate in tmp_path.
        import uuid
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Pair each jpeg_name with an extension (zip stops at the shorter list)
        jpeg_pairs = list(zip(jpeg_names, extensions))

        # Ensure non-JPEG filenames don't collide with JPEG filenames
        jpeg_stems = {name for name, _ in jpeg_pairs}
        safe_non_jpeg = [n for n in non_jpeg_names if n not in jpeg_stems]

        # Create JPEG files
        created_jpeg_paths = set()
        for name, ext in jpeg_pairs:
            p = work_dir / f"{name}{ext}"
            buf = io.BytesIO()
            Image.new("RGB", (4, 4), color=(0, 0, 0)).save(buf, format="JPEG")
            p.write_bytes(buf.getvalue())
            created_jpeg_paths.add(p)

        # Create non-JPEG files (.txt)
        for name in safe_non_jpeg:
            (work_dir / f"{name}.txt").write_text("not an image")

        loader = ImageLoader()
        result = loader.discover_images(work_dir)

        # All returned paths must have a JPEG extension (case-insensitive)
        jpeg_extensions = {".jpg", ".jpeg"}
        for p in result:
            assert p.suffix.lower() in jpeg_extensions, (
                f"discover_images() returned a non-JPEG path: {p}"
            )

        # Count must equal the number of JPEG files we created
        assert len(result) == len(created_jpeg_paths), (
            f"Expected {len(created_jpeg_paths)} JPEG files, got {len(result)}"
        )

        # Every returned path must live inside the work directory
        for p in result:
            assert p.parent == work_dir, (
                f"discover_images() returned a path outside the directory: {p}"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        jpeg_count=st.integers(min_value=0, max_value=8),
        non_jpeg_extensions=st.lists(
            st.sampled_from([".png", ".txt", ".bmp", ".tiff", ".gif", ".csv", ".json"]),
            min_size=0,
            max_size=8,
        ),
    )
    def test_property_non_jpeg_file_filtering(
        self, tmp_path, jpeg_count, non_jpeg_extensions
    ):
        """Property 4: Non-JPEG File Filtering.

        For any directory containing a mix of JPEG and non-JPEG files,
        discover_images() SHALL return only files with JPEG extensions, and
        the count of returned files SHALL equal the count of JPEG files in
        the directory.

        **Validates: Requirements 1.4**
        """
        import uuid
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        # Create JPEG files
        for i in range(jpeg_count):
            p = work_dir / f"jpeg_{i}.jpg"
            buf = io.BytesIO()
            Image.new("RGB", (4, 4), color=(i * 10 % 255, 0, 0)).save(buf, format="JPEG")
            p.write_bytes(buf.getvalue())

        # Create non-JPEG files
        for i, ext in enumerate(non_jpeg_extensions):
            p = work_dir / f"other_{i}{ext}"
            p.write_bytes(b"not a jpeg")

        loader = ImageLoader()
        result = loader.discover_images(work_dir)

        # Count must equal exactly the number of JPEG files created
        assert len(result) == jpeg_count, (
            f"Expected {jpeg_count} results, got {len(result)}"
        )

        # Every returned path must have a JPEG extension
        jpeg_extensions = {".jpg", ".jpeg"}
        for p in result:
            assert p.suffix.lower() in jpeg_extensions, (
                f"discover_images() returned a non-JPEG path: {p}"
            )

        # No non-JPEG file should appear in the results
        result_names = {p.name for p in result}
        for i, ext in enumerate(non_jpeg_extensions):
            non_jpeg_name = f"other_{i}{ext}"
            assert non_jpeg_name not in result_names, (
                f"Non-JPEG file '{non_jpeg_name}' was incorrectly included in results"
            )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        content=st.one_of(
            # Empty file
            st.just(b""),
            # Truncated JPEG header (magic bytes only, no valid data after)
            st.just(b"\xff\xd8"),
            # Random bytes that are NOT valid JPEG (avoid \xff\xd8 prefix)
            st.binary(min_size=1, max_size=512).filter(
                lambda b: not b.startswith(b"\xff\xd8")
            ),
            # Text content encoded as bytes
            st.text(min_size=1, max_size=200).map(lambda s: s.encode("utf-8")),
            # Random binary data with JPEG magic but corrupted body
            st.binary(min_size=4, max_size=512).map(
                lambda b: b"\xff\xd8\xff\xe0" + b
            ),
        )
    )
    def test_property_invalid_file_error_identification(self, tmp_path, content):
        """Property 3: Invalid File Error Identification.

        For any corrupted or invalid image file, the ImageLoader SHALL raise
        an InvalidImageError whose message contains the filename of the
        problematic file.

        **Validates: Requirements 1.3**
        """
        import uuid
        filename = f"invalid_{uuid.uuid4().hex}.jpg"
        invalid_path = tmp_path / filename
        invalid_path.write_bytes(content)

        loader = ImageLoader()
        with pytest.raises(InvalidImageError) as exc_info:
            loader.load(invalid_path)

        assert filename in str(exc_info.value), (
            f"InvalidImageError message does not contain filename '{filename}': "
            f"{exc_info.value}"
        )
