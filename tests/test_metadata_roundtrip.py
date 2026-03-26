"""Property-based tests for metadata JSON round-trip.

Feature: sedimental-analysis-tool
Property: 15 - Metadata JSON Round-Trip
Validates: Requirements 5.12

For any valid MetadataConfig object, serializing to JSON then parsing SHALL
produce an equivalent MetadataConfig (same default values, same per-image overrides).
"""

import json
import tempfile
import pytest
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from hypothesis import given, settings, strategies as st

from sedimental.metadata import MetadataParser
from sedimental.models import MetadataConfig, SampleMetadata


# ---------------------------------------------------------------------------
# Serialization helper (inverse of MetadataParser.parse)
# ---------------------------------------------------------------------------

def _metadata_to_dict(m: SampleMetadata) -> Dict[str, Any]:
    """Serialize a SampleMetadata to a JSON-compatible dict."""
    d: Dict[str, Any] = {}
    if m.sample_id is not None:
        d["sample_id"] = m.sample_id
    if m.location_lat is not None or m.location_lon is not None or m.location_description is not None:
        loc: Dict[str, Any] = {}
        if m.location_lat is not None:
            loc["lat"] = m.location_lat
        if m.location_lon is not None:
            loc["lon"] = m.location_lon
        if m.location_description is not None:
            loc["description"] = m.location_description
        d["location"] = loc
    if m.capture_date is not None:
        d["capture_date"] = m.capture_date.isoformat()
    if m.scale_ppm is not None:
        d["scale_ppm"] = m.scale_ppm
    if m.submitted_by is not None:
        d["submitted_by"] = m.submitted_by
    d.update(m.custom_fields)
    return d


def _config_to_json(config: MetadataConfig) -> str:
    """Serialize a MetadataConfig to a JSON string."""
    data: Dict[str, Any] = {
        "default": _metadata_to_dict(config.default),
        "images": {
            filename: _metadata_to_dict(meta)
            for filename, meta in config.images.items()
        },
    }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Custom fields must use keys that don't collide with known metadata keys
_KNOWN_KEYS = {"sample_id", "location", "capture_date", "scale_ppm", "submitted_by"}

_custom_key = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
).filter(lambda k: k not in _KNOWN_KEYS)

# Custom field values must be JSON-serializable primitives
_custom_value = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(
        min_value=-1e6, max_value=1e6,
        allow_nan=False, allow_infinity=False,
    ),
)


@st.composite
def sample_metadata_strategy(draw) -> SampleMetadata:
    """Generate arbitrary SampleMetadata with JSON-round-trip-safe values."""
    return SampleMetadata(
        sample_id=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        location_lat=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False),
            )
        ),
        location_lon=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False),
            )
        ),
        location_description=draw(st.one_of(st.none(), st.text(min_size=1, max_size=100))),
        capture_date=draw(
            st.one_of(
                st.none(),
                st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
            )
        ),
        scale_ppm=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.01, max_value=10_000.0, allow_nan=False, allow_infinity=False),
            )
        ),
        submitted_by=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
        custom_fields=draw(
            st.dictionaries(keys=_custom_key, values=_custom_value, max_size=5)
        ),
    )


@st.composite
def metadata_config_strategy(draw) -> MetadataConfig:
    """Generate arbitrary MetadataConfig objects."""
    default = draw(sample_metadata_strategy())
    image_filenames = draw(
        st.lists(
            st.text(min_size=1, max_size=30).map(lambda s: s + ".jpg"),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )
    images = {fn: draw(sample_metadata_strategy()) for fn in image_filenames}
    return MetadataConfig(default=default, images=images)


# ---------------------------------------------------------------------------
# Helpers for equivalence comparison
# ---------------------------------------------------------------------------

def _metadata_equiv(a: SampleMetadata, b: SampleMetadata) -> bool:
    """Return True if two SampleMetadata objects are semantically equivalent."""
    return (
        a.sample_id == b.sample_id
        and _float_equiv(a.location_lat, b.location_lat)
        and _float_equiv(a.location_lon, b.location_lon)
        and a.location_description == b.location_description
        and a.capture_date == b.capture_date
        and _float_equiv(a.scale_ppm, b.scale_ppm)
        and a.submitted_by == b.submitted_by
        and a.custom_fields == b.custom_fields
    )


def _float_equiv(a: Optional[float], b: Optional[float]) -> bool:
    """Float comparison that handles None and near-equality."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) < 1e-9


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestMetadataJsonRoundTrip:
    """Test suite for Property 15: Metadata JSON Round-Trip."""

    @given(config=metadata_config_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_default_metadata(self, config):
        """
        Property: Serializing a MetadataConfig to JSON then parsing SHALL
        produce equivalent default metadata.
        """
        parser = MetadataParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metadata.json"
            path.write_text(_config_to_json(config), encoding="utf-8")
            parsed = parser.parse(path)

        assert _metadata_equiv(config.default, parsed.default), (
            f"Default metadata mismatch.\nOriginal: {config.default}\nParsed:   {parsed.default}"
        )

    @given(config=metadata_config_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_image_keys(self, config):
        """
        Property: Serializing then parsing SHALL preserve all per-image filename keys.
        """
        parser = MetadataParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metadata.json"
            path.write_text(_config_to_json(config), encoding="utf-8")
            parsed = parser.parse(path)

        assert set(parsed.images.keys()) == set(config.images.keys()), (
            f"Image keys mismatch.\nOriginal: {set(config.images.keys())}\n"
            f"Parsed:   {set(parsed.images.keys())}"
        )

    @given(config=metadata_config_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_per_image_metadata(self, config):
        """
        Property: Serializing then parsing SHALL produce equivalent per-image metadata
        for every image entry.
        """
        parser = MetadataParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metadata.json"
            path.write_text(_config_to_json(config), encoding="utf-8")
            parsed = parser.parse(path)

        for filename, original_meta in config.images.items():
            parsed_meta = parsed.images[filename]
            assert _metadata_equiv(original_meta, parsed_meta), (
                f"Per-image metadata mismatch for '{filename}'.\n"
                f"Original: {original_meta}\nParsed:   {parsed_meta}"
            )

    @given(config=metadata_config_strategy())
    @settings(max_examples=100)
    def test_double_round_trip_is_stable(self, config):
        """
        Property: Performing the round-trip twice SHALL produce the same result
        as performing it once (stability / idempotence of serialization).
        """
        parser = MetadataParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "meta1.json"
            path1.write_text(_config_to_json(config), encoding="utf-8")
            parsed1 = parser.parse(path1)

            path2 = Path(tmpdir) / "meta2.json"
            path2.write_text(_config_to_json(parsed1), encoding="utf-8")
            parsed2 = parser.parse(path2)

        assert _metadata_equiv(parsed1.default, parsed2.default)
        assert set(parsed1.images.keys()) == set(parsed2.images.keys())
        for filename in parsed1.images:
            assert _metadata_equiv(parsed1.images[filename], parsed2.images[filename])

    # ------------------------------------------------------------------
    # Concrete examples
    # ------------------------------------------------------------------

    def test_concrete_full_metadata_round_trip(self, tmp_path):
        """Concrete example: a fully-populated MetadataConfig survives round-trip."""
        parser = MetadataParser()
        config = MetadataConfig(
            default=SampleMetadata(
                sample_id="SAMPLE001",
                location_lat=39.5,
                location_lon=-106.5,
                location_description="Colorado River, Mile 42",
                capture_date=date(2024, 3, 15),
                scale_ppm=12.5,
                submitted_by="researcher",
                custom_fields={"depth_m": 5, "notes": "clear water"},
            ),
            images={
                "sample1.jpg": SampleMetadata(
                    sample_id="SAMPLE001-A",
                    location_lat=39.6,
                    location_lon=-106.6,
                ),
                "sample2.jpg": SampleMetadata(scale_ppm=20.0),
            },
        )

        path = tmp_path / "metadata.json"
        path.write_text(_config_to_json(config), encoding="utf-8")
        parsed = parser.parse(path)

        assert _metadata_equiv(config.default, parsed.default)
        assert set(parsed.images.keys()) == {"sample1.jpg", "sample2.jpg"}
        assert _metadata_equiv(config.images["sample1.jpg"], parsed.images["sample1.jpg"])
        assert _metadata_equiv(config.images["sample2.jpg"], parsed.images["sample2.jpg"])

    def test_concrete_empty_config_round_trip(self, tmp_path):
        """Concrete example: an empty MetadataConfig survives round-trip."""
        parser = MetadataParser()
        config = MetadataConfig(default=SampleMetadata(), images={})

        path = tmp_path / "metadata.json"
        path.write_text(_config_to_json(config), encoding="utf-8")
        parsed = parser.parse(path)

        assert _metadata_equiv(config.default, parsed.default)
        assert parsed.images == {}

    def test_concrete_custom_fields_round_trip(self, tmp_path):
        """Concrete example: custom fields survive round-trip unchanged."""
        parser = MetadataParser()
        config = MetadataConfig(
            default=SampleMetadata(
                custom_fields={"site_code": "RC42", "operator_id": 7, "temp_c": 14.3}
            ),
            images={},
        )

        path = tmp_path / "metadata.json"
        path.write_text(_config_to_json(config), encoding="utf-8")
        parsed = parser.parse(path)

        assert parsed.default.custom_fields["site_code"] == "RC42"
        assert parsed.default.custom_fields["operator_id"] == 7
        assert abs(parsed.default.custom_fields["temp_c"] - 14.3) < 1e-9
