"""
Image loading and validation for Sedimental analysis tool.

This module provides the ImageLoader class for validating and loading
JPEG images, and discovering JPEG files in directories.
"""

import logging
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image, UnidentifiedImageError

from .errors import InvalidImageError

logger = logging.getLogger("sedimental.loader")


class ImageLoader:
    """Validates and loads JPEG images."""

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg"}

    def load(self, path: Path) -> np.ndarray:
        """
        Load and validate a JPEG image.

        Args:
            path: Path to the JPEG image file.

        Returns:
            Image as a numpy array with shape (H, W, 3).

        Raises:
            FileNotFoundError: If the file does not exist.
            InvalidImageError: If the file is not a valid JPEG or is corrupted.
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")

        try:
            with Image.open(path) as img:
                # Verify it's actually a JPEG by checking format
                if img.format != "JPEG":
                    raise InvalidImageError(
                        path.name,
                        f"file is not a JPEG (detected format: {img.format})",
                    )

                # Force full decode to catch corrupted files
                img.verify()

            # Re-open after verify (verify closes/invalidates the image)
            with Image.open(path) as img:
                img.load()
                # Convert to RGB to ensure (H, W, 3) shape
                rgb_img = img.convert("RGB")
                return np.array(rgb_img)

        except InvalidImageError:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise InvalidImageError(path.name, str(exc)) from exc
        except Exception as exc:
            raise InvalidImageError(path.name, f"unexpected error: {exc}") from exc

    def discover_images(self, directory: Path) -> List[Path]:
        """
        Find all JPEG files in a directory (non-recursive).

        Logs a warning for any non-JPEG files encountered.

        Args:
            directory: Path to the directory to scan.

        Returns:
            List of Paths to JPEG files found in the directory.
        """
        directory = Path(directory)
        jpeg_files: List[Path] = []

        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue

            suffix = entry.suffix.lower()
            if suffix in self.SUPPORTED_EXTENSIONS:
                jpeg_files.append(entry)
            else:
                logger.warning("Skipping non-JPEG file: %s", entry.name)

        return jpeg_files
