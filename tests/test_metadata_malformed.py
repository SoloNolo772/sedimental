"""Property-based tests for malformed metadata error handling.

Feature: sedimental-analysis-tool
Property: 16 - Malformed Metadata Error
Validates: Requirements 5.11

For any malformed JSON string (invalid syntax, missing required structure),
the MetadataParser.parse() SHALL raise a MetadataParseError whose message
describes the parsing failure.
"""

import json
import tempfile
import uuid
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from sedimental.errors import MetadataParseError
from sedimental.metadata import MetadataParser


# ---------------------------------------------------------------------------
# Hypothesis strategies for malformed inputs
# ---------------------------------------------------------------------------

@st.composite
def invalid_json_string_strategy(draw):
    """Generate strings that are not valid JSON."""
    # Corrupt a valid JSON object by truncating, injecting bad chars, etc.
    base = draw(st.text(min_size=1, max_size=200))
    # Filter out anything that happens to be valid JSON
    return draw(
        st.one_of(
            # Truncated JSON objects
            st.just("{"),
            st.just("{bad"),
            st.just('{"key": }'),
            st.just('{"key": "value"'),
            st.just("[1, 2,]"),
            st.just("}{"),
            # Arbitrary non-JSON text
            st.text(min_size=1, max_size=100).filter(
                lambda s: _is_invalid_json(s)
            ),
        )
    )


def _is_invalid_json(s: str) -> bool:
    """Return True if s is NOT valid JSON."""
    try:
        json.loads(s)
        return False
    except (json.JSONDecodeError, ValueError):
        return True


@st.composite
def non_object_json_strategy(draw):
    """Generate valid JSON that is NOT a top-level object (dict)."""
    return draw(
        st.one_of(
            st.just("null"),
            st.just("true"),
            st.just("false"),
            st.integers().map(str),
            st.floats(allow_nan=False, allow_infinity=False).map(
                lambda f: json.dumps(f)
            ),
            st.text(min_size=0, max_size=50).map(lambda s: json.dumps(s)),
            st.lists(st.integers(), min_size=0, max_size=5).map(json.dumps),
        )
    )


@st.composite
def invalid_field_type_strategy(draw):
    """Generate a valid JSON object with a known field set to a wrong type."""
    field = draw(
        st.sampled_from([
            ("sample_id", draw(st.one_of(st.integers(), st.booleans(), st.lists(st.integers())))),
            ("scale_ppm", draw(st.one_of(st.text(min_size=1), st.booleans(), st.lists(st.integers())))),
            ("capture_date", draw(st.one_of(st.integers(), st.booleans(), st.lists(st.integers())))),
            ("location", draw(st.one_of(st.text(min_size=1), st.integers(), st.booleans()))),
            ("submitted_by", draw(st.one_of(st.integers(), st.booleans(), st.lists(st.integers())))),
        ])
    )
    key, bad_value = field
    return json.dumps({"default": {key: bad_value}})


@st.composite
def invalid_scale_ppm_strategy(draw):
    """Generate JSON with scale_ppm set to a non-positive number."""
    value = draw(
        st.one_of(
            st.just(0),
            st.just(0.0),
            st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
            st.integers(max_value=-1),
        )
    )
    return json.dumps({"default": {"scale_ppm": value}})


@st.composite
def out_of_range_location_strategy(draw):
    """Generate JSON with lat/lon values outside valid ranges."""
    kind = draw(st.sampled_from(["lat_high", "lat_low", "lon_high", "lon_low"]))
    if kind == "lat_high":
        val = draw(st.floats(min_value=90.001, max_value=1000.0, allow_nan=False, allow_infinity=False))
        loc = {"lat": val}
    elif kind == "lat_low":
        val = draw(st.floats(min_value=-1000.0, max_value=-90.001, allow_nan=False, allow_infinity=False))
        loc = {"lat": val}
    elif kind == "lon_high":
        val = draw(st.floats(min_value=180.001, max_value=1000.0, allow_nan=False, allow_infinity=False))
        loc = {"lon": val}
    else:
        val = draw(st.floats(min_value=-1000.0, max_value=-180.001, allow_nan=False, allow_infinity=False))
        loc = {"lon": val}
    return json.dumps({"default": {"location": loc}})


@st.composite
def invalid_capture_date_strategy(draw):
    """Generate JSON with capture_date set to a non-ISO-8601 string."""
    bad_date = draw(
        st.text(min_size=1, max_size=30).filter(
            lambda s: not _is_valid_iso_date(s)
        )
    )
    return json.dumps({"default": {"capture_date": bad_date}})


def _is_valid_iso_date(s: str) -> bool:
    from datetime import date
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_and_parse(content: str) -> None:
    """Write content to a temp file and attempt to parse it."""
    parser = MetadataParser()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / f"{uuid.uuid4().hex}.json"
        path.write_text(content, encoding="utf-8")
        parser.parse(path)


# ---------------------------------------------------------------------------
# Property 16: Malformed Metadata Error
# ---------------------------------------------------------------------------

class TestMalformedMetadataError:
    """Test suite for Property 16: Malformed Metadata Error.

    For any malformed JSON string (invalid syntax, missing required structure),
    MetadataParser.parse() SHALL raise a MetadataParseError whose message
    describes the parsing failure.
    """

    # ------------------------------------------------------------------
    # Property: invalid JSON syntax always raises MetadataParseError
    # ------------------------------------------------------------------

    @given(bad_json=invalid_json_string_strategy())
    @settings(max_examples=100)
    def test_invalid_json_syntax_raises_metadata_parse_error(self, bad_json):
        """
        Property: Any string that is not valid JSON SHALL cause parse() to
        raise MetadataParseError.
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(bad_json)
        assert str(exc_info.value), "Error message must not be empty"

    @given(bad_json=invalid_json_string_strategy())
    @settings(max_examples=100)
    def test_invalid_json_error_message_describes_failure(self, bad_json):
        """
        Property: The MetadataParseError message for invalid JSON SHALL contain
        a description of the parsing failure (not just an empty string).
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(bad_json)
        error_msg = str(exc_info.value).lower()
        # Message should mention JSON or parsing in some form
        assert any(
            keyword in error_msg
            for keyword in ("json", "parse", "invalid", "failed")
        ), f"Error message lacks description: {exc_info.value}"

    # ------------------------------------------------------------------
    # Property: non-object root raises MetadataParseError
    # ------------------------------------------------------------------

    @given(non_obj=non_object_json_strategy())
    @settings(max_examples=100)
    def test_non_object_root_raises_metadata_parse_error(self, non_obj):
        """
        Property: Valid JSON whose top-level value is not an object SHALL
        raise MetadataParseError.
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(non_obj)
        assert str(exc_info.value)

    # ------------------------------------------------------------------
    # Property: wrong field types raise MetadataParseError
    # ------------------------------------------------------------------

    @given(bad_content=invalid_field_type_strategy())
    @settings(max_examples=100)
    def test_wrong_field_type_raises_metadata_parse_error(self, bad_content):
        """
        Property: A metadata JSON with a known field set to an incorrect type
        SHALL raise MetadataParseError.
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(bad_content)
        assert str(exc_info.value)

    # ------------------------------------------------------------------
    # Property: non-positive scale_ppm raises MetadataParseError
    # ------------------------------------------------------------------

    @given(bad_content=invalid_scale_ppm_strategy())
    @settings(max_examples=100)
    def test_non_positive_scale_ppm_raises_metadata_parse_error(self, bad_content):
        """
        Property: A scale_ppm value that is zero or negative SHALL raise
        MetadataParseError.
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(bad_content)
        assert "scale_ppm" in str(exc_info.value)

    # ------------------------------------------------------------------
    # Property: out-of-range lat/lon raises MetadataParseError
    # ------------------------------------------------------------------

    @given(bad_content=out_of_range_location_strategy())
    @settings(max_examples=100)
    def test_out_of_range_location_raises_metadata_parse_error(self, bad_content):
        """
        Property: Latitude outside [-90, 90] or longitude outside [-180, 180]
        SHALL raise MetadataParseError.
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(bad_content)
        assert str(exc_info.value)

    # ------------------------------------------------------------------
    # Property: invalid capture_date string raises MetadataParseError
    # ------------------------------------------------------------------

    @given(bad_content=invalid_capture_date_strategy())
    @settings(max_examples=100)
    def test_invalid_capture_date_raises_metadata_parse_error(self, bad_content):
        """
        Property: A capture_date value that is not a valid ISO 8601 date string
        SHALL raise MetadataParseError.
        """
        with pytest.raises(MetadataParseError) as exc_info:
            _write_and_parse(bad_content)
        assert "capture_date" in str(exc_info.value)

    # ------------------------------------------------------------------
    # Property: error is always MetadataParseError (not a generic exception)
    # ------------------------------------------------------------------

    @given(bad_json=invalid_json_string_strategy())
    @settings(max_examples=50)
    def test_error_type_is_always_metadata_parse_error(self, bad_json):
        """
        Property: parse() SHALL never raise a raw ValueError, json.JSONDecodeError,
        or other unhandled exception — only MetadataParseError.
        """
        try:
            _write_and_parse(bad_json)
        except MetadataParseError:
            pass  # Expected
        except Exception as exc:
            pytest.fail(
                f"Expected MetadataParseError but got {type(exc).__name__}: {exc}"
            )

    # ------------------------------------------------------------------
    # Concrete / regression tests
    # ------------------------------------------------------------------

    def test_concrete_invalid_json_syntax(self, tmp_path):
        """Concrete: Truncated JSON raises MetadataParseError with 'invalid JSON'."""
        path = tmp_path / "metadata.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "invalid JSON" in str(exc_info.value)

    def test_concrete_json_array_root_raises(self, tmp_path):
        """Concrete: A JSON array at root raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('[{"sample_id": "S1"}]', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "JSON object" in str(exc_info.value)

    def test_concrete_default_not_object_raises(self, tmp_path):
        """Concrete: 'default' set to a string raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": "not an object"}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert '"default"' in str(exc_info.value)

    def test_concrete_images_not_object_raises(self, tmp_path):
        """Concrete: 'images' set to a list raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"images": ["img.jpg"]}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert '"images"' in str(exc_info.value)

    def test_concrete_image_entry_not_object_raises(self, tmp_path):
        """Concrete: A per-image entry that is not an object raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"images": {"img.jpg": "bad"}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "images.img.jpg" in str(exc_info.value)

    def test_concrete_scale_ppm_zero_raises(self, tmp_path):
        """Concrete: scale_ppm of 0 raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"scale_ppm": 0}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "scale_ppm" in str(exc_info.value)

    def test_concrete_scale_ppm_negative_raises(self, tmp_path):
        """Concrete: Negative scale_ppm raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"scale_ppm": -5.0}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "scale_ppm" in str(exc_info.value)

    def test_concrete_invalid_capture_date_raises(self, tmp_path):
        """Concrete: Non-ISO capture_date raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"capture_date": "March 15 2024"}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "capture_date" in str(exc_info.value)

    def test_concrete_lat_out_of_range_raises(self, tmp_path):
        """Concrete: Latitude > 90 raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"location": {"lat": 91.0}}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "lat" in str(exc_info.value)

    def test_concrete_lon_out_of_range_raises(self, tmp_path):
        """Concrete: Longitude > 180 raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"location": {"lon": 200.0}}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "lon" in str(exc_info.value)

    def test_concrete_sample_id_wrong_type_raises(self, tmp_path):
        """Concrete: sample_id as integer raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"sample_id": 42}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "sample_id" in str(exc_info.value)

    def test_concrete_location_not_object_raises(self, tmp_path):
        """Concrete: location as a string raises MetadataParseError."""
        path = tmp_path / "metadata.json"
        path.write_text('{"default": {"location": "Colorado River"}}', encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "location" in str(exc_info.value)

    def test_concrete_error_contains_file_path(self, tmp_path):
        """Concrete: MetadataParseError message SHALL reference the file path."""
        path = tmp_path / "my_metadata.json"
        path.write_text("{bad json", encoding="utf-8")
        with pytest.raises(MetadataParseError) as exc_info:
            MetadataParser().parse(path)
        assert "my_metadata.json" in str(exc_info.value)
