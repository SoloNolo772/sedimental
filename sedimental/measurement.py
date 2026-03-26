"""
Measurement engine for Sedimental analysis tool.

Calculates particle statistics (area, perimeter, circularity, roundness,
feret diameter, major/minor axis) from labeled segmentation masks using
scikit-image regionprops.

PyImageJ is used as an optional backend when available; scikit-image is the
default and is always available in the container.
"""

import logging
import math
from typing import List, Optional

import numpy as np
from skimage.measure import regionprops, label as sk_label

from .errors import MeasurementError
from .models import GrainMeasurement, MeasurementUnit

logger = logging.getLogger("sedimental.measurement")


class MeasurementEngine:
    """
    Calculates grain measurements from labeled segmentation masks.

    Uses scikit-image regionprops for particle statistics. PyImageJ
    initialization is kept as a lazy attribute for future extension but
    all current measurements are computed via scikit-image.
    """

    def __init__(self):
        self._ij = None  # Lazy PyImageJ handle (reserved for future use)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _circularity(area: float, perimeter: float) -> float:
        """4π × area / perimeter²  (1.0 = perfect circle)."""
        if perimeter <= 0:
            return 0.0
        return min(1.0, (4.0 * math.pi * area) / (perimeter ** 2))

    @staticmethod
    def _roundness(area: float, major_axis: float) -> float:
        """4 × area / (π × major_axis²)  (1.0 = perfect circle)."""
        if major_axis <= 0:
            return 0.0
        return min(1.0, (4.0 * area) / (math.pi * major_axis ** 2))

    @staticmethod
    def _feret_diameter(region) -> float:
        """
        Return the Feret (maximum caliper) diameter.

        scikit-image >= 0.19 exposes feret_diameter_max directly on the
        region object. Fall back to the bounding-box diagonal for older
        versions.
        """
        if hasattr(region, "feret_diameter_max"):
            return float(region.feret_diameter_max)
        # Fallback: bounding-box diagonal
        min_row, min_col, max_row, max_col = region.bbox
        return math.hypot(max_row - min_row, max_col - min_col)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def measure(
        self,
        mask: np.ndarray,
        scale_ppm: Optional[float] = None,
        filename: str = "<image>",
    ) -> List[GrainMeasurement]:
        """
        Calculate measurements for all labeled grains in a segmentation mask.

        Args:
            mask: Labeled integer mask (H, W) where 0 = background and each
                  positive integer identifies a unique grain.
            scale_ppm: Pixels per millimetre. When provided, length
                       measurements are converted to mm and area to mm².
                       Dimensionless ratios (circularity, roundness) are
                       unchanged.
            filename: Source filename used in error/warning messages.

        Returns:
            List of GrainMeasurement objects, one per unique positive label
            in the mask, sorted by grain_id.

        Raises:
            MeasurementError: If the mask array is invalid.
        """
        if mask.ndim != 2:
            raise MeasurementError(filename, None, f"expected 2-D mask, got shape {mask.shape}")

        unit = MeasurementUnit.MILLIMETERS if scale_ppm is not None else MeasurementUnit.PIXELS

        # regionprops requires a labeled array; our masks already are.
        regions = regionprops(mask.astype(np.int32))

        if not regions:
            logger.warning("No grains found in mask for '%s'", filename)
            return []

        measurements: List[GrainMeasurement] = []

        for region in regions:
            grain_id = int(region.label)
            try:
                area_px = float(region.area)
                perimeter_px = float(region.perimeter)
                major_px = float(region.major_axis_length)
                minor_px = float(region.minor_axis_length)
                feret_px = self._feret_diameter(region)

                circ = self._circularity(area_px, perimeter_px)
                rnd = self._roundness(area_px, major_px)

                if scale_ppm is not None and scale_ppm > 0:
                    area_out = area_px / (scale_ppm ** 2)
                    perimeter_out = perimeter_px / scale_ppm
                    major_out = major_px / scale_ppm
                    minor_out = minor_px / scale_ppm
                    feret_out = feret_px / scale_ppm
                else:
                    area_out = area_px
                    perimeter_out = perimeter_px
                    major_out = major_px
                    minor_out = minor_px
                    feret_out = feret_px

                measurements.append(
                    GrainMeasurement(
                        grain_id=grain_id,
                        area=area_out,
                        perimeter=perimeter_out,
                        circularity=circ,
                        roundness=rnd,
                        feret_diameter=feret_out,
                        major_axis=major_out,
                        minor_axis=minor_out,
                        unit=unit,
                        scale_factor=scale_ppm,
                    )
                )

                logger.debug(
                    "Grain %d: area=%.2f %s, circ=%.3f, round=%.3f",
                    grain_id,
                    area_out,
                    unit.value,
                    circ,
                    rnd,
                )

            except Exception as exc:
                logger.warning(
                    "Measurement failed for '%s' grain %d: %s", filename, grain_id, exc
                )
                raise MeasurementError(filename, grain_id, str(exc)) from exc

        logger.info(
            "Measured %d grain(s) in '%s' (units=%s)", len(measurements), filename, unit.value
        )
        return measurements
