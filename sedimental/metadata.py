"""
Metadata parsing for Sedimental analysis tool.

This module provides the MetadataParser class for loading and merging
sample metadata from JSON files.
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import MetadataParseError
from .models import MetadataConfig, SampleMetadata

logger = logging.getLogger("sedimental.metadata")


class MetadataParser:
    """Parses and merges sample metadata from JSON files.

    Expected JSON format::

        {
            "default": {
                "sample_id": "SAMPLE001",
                "location": {"lat": 39.5, "lon": -106.5},
                "capture_date": "2024-01-15",
                "scale_ppm": 12.5
            },
            "images": {
                "sample1.jpg": {
                    "sample_id": "SAMPLE001-A",
                    "location": {"lat": 39.6, "lon": -106.6}
                }
            }
        }
    """

    def parse(self, path: Path) -> MetadataConfig:
        """Parse a metadata JSON file.

        Args:
            path: Path to the metadata JSON file.

        Returns:
            MetadataConfig with default and per-image metadata.

        Raises:
            MetadataParseError: If the file cannot be read or contains
                invalid JSON or an unexpected structure.
        """
        path = Path(path)
        path_str = str(path)

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MetadataParseError(path_str, f"cannot read file: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MetadataParseError(
                path_str, f"invalid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise MetadataParseError(
                path_str, "top-level value must be a JSON object"
            )

        # Parse "default" section (optional — empty metadata if absent)
        default_raw = data.get("default", {})
        if not isinstance(default_raw, dict):
            raise MetadataParseError(
                path_str, '"default" must be a JSON object'
            )
        default_meta = self._parse_metadata_dict(default_raw, path_str, context="default")

        # Parse "images" section (optional)
        images_raw = data.get("images", {})
        if not isinstance(images_raw, dict):
            raise MetadataParseError(
                path_str, '"images" must be a JSON object'
            )

        images: Dict[str, SampleMetadata] = {}
        for filename, img_data in images_raw.items():
            if not isinstance(img_data, dict):
                raise MetadataParseError(
                    path_str,
                    f'"images.{filename}" must be a JSON object',
                )
            images[filename] = self._parse_metadata_dict(
                img_data, path_str, context=f"images.{filename}"
            )

        return MetadataConfig(default=default_meta, images=images)

    def get_for_image(
        self, config: MetadataConfig, image_filename: str
    ) -> SampleMetadata:
        """Get merged metadata for a specific image.

        Per-image metadata (if present) is merged on top of the default,
        with per-image values taking precedence.

        Args:
            config: Parsed MetadataConfig.
            image_filename: The filename (basename) of the image.

        Returns:
            Merged SampleMetadata for the image.
        """
        per_image = config.images.get(image_filename)
        if per_image is None:
            logger.debug(
                "No per-image metadata for '%s'; using defaults", image_filename
            )
            return config.default

        logger.debug("Merging per-image metadata for '%s'", image_filename)
        return config.default.merge(per_image)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_metadata_dict(
        self, data: Dict[str, Any], path_str: str, context: str
    ) -> SampleMetadata:
        """Convert a raw dict into a SampleMetadata instance.

        Args:
            data: Raw dict from JSON.
            path_str: File path string (for error messages).
            context: JSON path context string (for error messages).

        Returns:
            SampleMetadata populated from *data*.

        Raises:
            MetadataParseError: On type or value errors.
        """
        def _ctx(field: str) -> str:
            return f"{context}.{field}"

        # sample_id
        sample_id: Optional[str] = None
        if "sample_id" in data:
            v = data["sample_id"]
            if not isinstance(v, str):
                raise MetadataParseError(
                    path_str, f'"{_ctx("sample_id")}" must be a string'
                )
            sample_id = v

        # location
        location_lat: Optional[float] = None
        location_lon: Optional[float] = None
        location_description: Optional[str] = None
        if "location" in data:
            loc = data["location"]
            if not isinstance(loc, dict):
                raise MetadataParseError(
                    path_str, f'"{_ctx("location")}" must be a JSON object'
                )
            if "lat" in loc:
                location_lat = self._parse_float(
                    loc["lat"], path_str, _ctx("location.lat"),
                    min_val=-90.0, max_val=90.0
                )
            if "lon" in loc:
                location_lon = self._parse_float(
                    loc["lon"], path_str, _ctx("location.lon"),
                    min_val=-180.0, max_val=180.0
                )
            if "description" in loc:
                v = loc["description"]
                if not isinstance(v, str):
                    raise MetadataParseError(
                        path_str,
                        f'"{_ctx("location.description")}" must be a string',
                    )
                location_description = v

        # capture_date
        capture_date: Optional[date] = None
        if "capture_date" in data:
            v = data["capture_date"]
            if not isinstance(v, str):
                raise MetadataParseError(
                    path_str, f'"{_ctx("capture_date")}" must be a string'
                )
            try:
                capture_date = date.fromisoformat(v)
            except ValueError as exc:
                raise MetadataParseError(
                    path_str,
                    f'"{_ctx("capture_date")}" is not a valid ISO 8601 date: {exc}',
                ) from exc

        # scale_ppm
        scale_ppm: Optional[float] = None
        if "scale_ppm" in data:
            scale_ppm = self._parse_float(
                data["scale_ppm"], path_str, _ctx("scale_ppm"), min_val=0.0, exclusive_min=True
            )

        # submitted_by
        submitted_by: Optional[str] = None
        if "submitted_by" in data:
            v = data["submitted_by"]
            if not isinstance(v, str):
                raise MetadataParseError(
                    path_str, f'"{_ctx("submitted_by")}" must be a string'
                )
            submitted_by = v

        # Collect remaining keys as custom_fields (exclude known keys)
        known_keys = {
            "sample_id", "location", "capture_date",
            "scale_ppm", "submitted_by",
        }
        custom_fields: Dict[str, Any] = {
            k: v for k, v in data.items() if k not in known_keys
        }

        return SampleMetadata(
            sample_id=sample_id,
            location_lat=location_lat,
            location_lon=location_lon,
            location_description=location_description,
            capture_date=capture_date,
            scale_ppm=scale_ppm,
            submitted_by=submitted_by,
            custom_fields=custom_fields,
        )

    def _parse_float(
        self,
        value: Any,
        path_str: str,
        field_ctx: str,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        exclusive_min: bool = False,
    ) -> float:
        """Parse and validate a numeric value as float.

        Raises:
            MetadataParseError: If value is not numeric or out of range.
        """
        if not isinstance(value, (int, float)):
            raise MetadataParseError(
                path_str, f'"{field_ctx}" must be a number'
            )
        fval = float(value)
        if min_val is not None:
            if exclusive_min and fval <= min_val:
                raise MetadataParseError(
                    path_str, f'"{field_ctx}" must be greater than {min_val}'
                )
            elif not exclusive_min and fval < min_val:
                raise MetadataParseError(
                    path_str, f'"{field_ctx}" must be >= {min_val}'
                )
        if max_val is not None and fval > max_val:
            raise MetadataParseError(
                path_str, f'"{field_ctx}" must be <= {max_val}'
            )
        return fval
