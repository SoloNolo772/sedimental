"""
Segmentation engine for Sedimental analysis tool.

Uses ImageGrains (backed by Cellpose) to detect grain boundaries in JPEG
images and produce labeled segmentation masks.
"""

import logging
import time
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import tifffile
from PIL import Image

from .errors import SegmentationError
from .models import SegmentationResult

logger = logging.getLogger("sedimental.segmentation")


class SegmentationEngine:
    """Wraps ImageGrains/Cellpose for grain boundary detection."""

    def __init__(self, model_type: str = "cyto2", gpu: bool = False):
        """
        Initialise the segmentation engine.

        Args:
            model_type: Cellpose model type to use (default: 'cyto2').
            gpu: Whether to use GPU acceleration (default: False).
        """
        self._model_type = model_type
        self._gpu = gpu
        self._model = None  # lazy initialisation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self):
        """Lazily initialise and return the Cellpose model."""
        if self._model is None:
            from cellpose import models as cp_models

            logger.debug(
                "Initialising Cellpose model (type=%s, gpu=%s)",
                self._model_type,
                self._gpu,
            )
            self._model = cp_models.CellposeModel(
                gpu=self._gpu,
                pretrained_model=self._model_type,
            )

            # Log which device the model actually loaded onto
            try:
                import torch
                params = list(self._model.net.parameters())
                device = str(params[0].device) if params else "unknown"
                if self._gpu and torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    mem_total = torch.cuda.get_device_properties(0).total_memory // (1024 ** 2)
                    logger.info("Cellpose model loaded on GPU: %s (%d MB VRAM)", gpu_name, mem_total)
                else:
                    logger.info("Cellpose model loaded on CPU (device=%s)", device)
            except Exception:
                logger.debug("Cellpose model ready (device check skipped)")

        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def segment(self, image: np.ndarray, filename: str = "<image>") -> SegmentationResult:
        """
        Detect grain boundaries in an RGB image.

        Args:
            image: RGB image as a numpy array with shape (H, W, 3).
            filename: Source filename used in error/warning messages.

        Returns:
            SegmentationResult with a labeled integer mask and grain count.

        Raises:
            SegmentationError: If segmentation fails unexpectedly.
        """
        if image.ndim != 3 or image.shape[2] != 3:
            raise SegmentationError(filename, f"expected RGB array (H,W,3), got shape {image.shape}")

        warnings = []

        try:
            model = self._get_model()
            logger.info("Segmenting image '%s' (%dx%d)", filename, image.shape[1], image.shape[0])

            t0 = time.time()
            # Cellpose eval returns (masks_list, flows_list, styles_list) for a
            # batch; we pass a single image so index [0].
            masks_list, _flows, _styles = model.eval(
                [image],
                diameter=None,
                channels=None,
            )
            elapsed = time.time() - t0
            mask: np.ndarray = masks_list[0]
            logger.info("Segmentation completed in %.2fs", elapsed)

        except SegmentationError:
            raise
        except Exception as exc:
            raise SegmentationError(filename, str(exc)) from exc

        # Count unique positive labels (0 = background)
        unique_labels = np.unique(mask)
        grain_count = int(np.sum(unique_labels > 0))

        if grain_count == 0:
            msg = f"No grains detected in '{filename}'"
            logger.warning(msg)
            warnings.append(msg)
        else:
            logger.info("Detected %d grain(s) in '%s'", grain_count, filename)

        return SegmentationResult(
            mask=mask.astype(np.int32),
            grain_count=grain_count,
            warnings=warnings,
        )

    def save_mask(self, mask: np.ndarray, output_path: Path) -> None:
        """
        Save a segmentation mask as a TIFF file with integer labels.

        Args:
            mask: Labeled integer mask array (H, W).
            output_path: Destination path for the TIFF file.

        Raises:
            OutputError: If writing fails.
        """
        from .errors import OutputError

        output_path = Path(output_path)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(str(output_path), mask.astype(np.int32))
            logger.info("Saved segmentation mask to '%s'", output_path)
        except Exception as exc:
            raise OutputError(f"Failed to write mask to '{output_path}': {exc}") from exc
