"""
CSV writer for Sedimental analysis tool.

Serializes grain measurements and metadata to CSV format, and parses
them back for round-trip support.
"""

import csv
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from .errors import OutputError
from .models import (
    GrainMeasurement,
    ImageResult,
    MeasurementUnit,
    SampleMetadata,
)

logger = logging.getLogger("sedimental.output")

COLUMNS = [
    "source_file",
    "grain_id",
    "area",
    "perimeter",
    "circularity",
    "roundness",
    "feret_diameter",
    "major_axis",
    "minor_axis",
    "units",
    "scale_factor",
    "sample_id",
    "location_lat",
    "location_lon",
    "location_description",
    "capture_date",
    "submitted_by",
]


def _opt_float(value: str) -> Optional[float]:
    """Parse an optional float from a CSV cell (empty string → None)."""
    return float(value) if value not in ("", "None") else None


def _opt_str(value: str) -> Optional[str]:
    """Return None for empty/None strings."""
    return value if value not in ("", "None") else None


def _opt_date(value: str) -> Optional[date]:
    """Parse an optional ISO 8601 date string."""
    if value in ("", "None"):
        return None
    return date.fromisoformat(value)


class CSVWriter:
    """Serializes grain measurements to CSV and parses them back."""

    COLUMNS = COLUMNS

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, results: List[ImageResult], output_path: Path) -> None:
        """Write all ImageResult objects to a CSV file.

        Args:
            results: List of ImageResult objects to serialise.
            output_path: Destination path for the CSV file.

        Raises:
            OutputError: If the file cannot be written.
        """
        output_path = Path(output_path)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS)
                writer.writeheader()
                total_rows = 0
                for image_result in results:
                    for row in self._rows_for_image(image_result):
                        writer.writerow(row)
                        total_rows += 1
        except OSError as exc:
            raise OutputError(f"Failed to write CSV to '{output_path}': {exc}") from exc

        logger.info("Wrote %d grain row(s) to '%s'", total_rows, output_path)

    def _rows_for_image(self, image_result: ImageResult):
        """Yield one dict per grain measurement in an ImageResult."""
        meta = image_result.metadata
        capture_date_str = (
            meta.capture_date.isoformat() if meta.capture_date is not None else ""
        )
        for m in image_result.measurements:
            yield {
                "source_file": image_result.source_file,
                "grain_id": m.grain_id,
                "area": m.area,
                "perimeter": m.perimeter,
                "circularity": m.circularity,
                "roundness": m.roundness,
                "feret_diameter": m.feret_diameter,
                "major_axis": m.major_axis,
                "minor_axis": m.minor_axis,
                "units": m.unit.value,
                "scale_factor": meta.scale_ppm if meta.scale_ppm is not None else "",
                "sample_id": meta.sample_id or "",
                "location_lat": meta.location_lat if meta.location_lat is not None else "",
                "location_lon": meta.location_lon if meta.location_lon is not None else "",
                "location_description": meta.location_description or "",
                "capture_date": capture_date_str,
                "submitted_by": meta.submitted_by or "",
            }

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def parse(self, path: Path) -> List[ImageResult]:
        """Parse a results CSV back into a list of ImageResult objects.

        Rows are grouped by source_file. Metadata is reconstructed from
        the first row of each group (all rows for the same image share
        the same metadata values).

        Args:
            path: Path to the CSV file.

        Returns:
            List of ImageResult objects, one per unique source_file.

        Raises:
            OutputError: If the file cannot be read or is malformed.
        """
        path = Path(path)
        try:
            with path.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
        except OSError as exc:
            raise OutputError(f"Failed to read CSV from '{path}': {exc}") from exc

        # Group rows by source_file, preserving insertion order
        groups: dict[str, list] = {}
        for row in rows:
            src = row.get("source_file", "")
            groups.setdefault(src, []).append(row)

        image_results: List[ImageResult] = []
        for source_file, file_rows in groups.items():
            metadata = self._parse_metadata(file_rows[0])
            measurements = [self._parse_measurement(r) for r in file_rows]
            image_results.append(
                ImageResult(
                    source_file=source_file,
                    metadata=metadata,
                    measurements=measurements,
                )
            )

        logger.info("Parsed %d image result(s) from '%s'", len(image_results), path)
        return image_results

    def _parse_metadata(self, row: dict) -> SampleMetadata:
        """Reconstruct SampleMetadata from a CSV row."""
        return SampleMetadata(
            sample_id=_opt_str(row.get("sample_id", "")),
            location_lat=_opt_float(row.get("location_lat", "")),
            location_lon=_opt_float(row.get("location_lon", "")),
            location_description=_opt_str(row.get("location_description", "")),
            capture_date=_opt_date(row.get("capture_date", "")),
            scale_ppm=_opt_float(row.get("scale_factor", "")),
            submitted_by=_opt_str(row.get("submitted_by", "")),
        )

    def _parse_measurement(self, row: dict) -> GrainMeasurement:
        """Reconstruct a GrainMeasurement from a CSV row."""
        units_str = row.get("units", "pixels")
        unit = (
            MeasurementUnit.MILLIMETERS
            if units_str == MeasurementUnit.MILLIMETERS.value
            else MeasurementUnit.PIXELS
        )
        # scale_factor on the grain is only set when measurements were converted
        # to mm; the CSV scale_factor column stores the image-level scale_ppm.
        scale_factor = (
            _opt_float(row.get("scale_factor", ""))
            if unit == MeasurementUnit.MILLIMETERS
            else None
        )
        return GrainMeasurement(
            grain_id=int(row["grain_id"]),
            area=float(row["area"]),
            perimeter=float(row["perimeter"]),
            circularity=float(row["circularity"]),
            roundness=float(row["roundness"]),
            feret_diameter=float(row["feret_diameter"]),
            major_axis=float(row["major_axis"]),
            minor_axis=float(row["minor_axis"]),
            unit=unit,
            scale_factor=scale_factor,
        )
