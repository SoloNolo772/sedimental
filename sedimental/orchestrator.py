"""
Processing orchestrator for Sedimental analysis tool.

Coordinates the full pipeline: image loading, segmentation, measurement,
metadata resolution, and CSV output. Handles partial failures gracefully
so a single bad image never aborts a batch run.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .csv_writer import CSVWriter
from .errors import SedimentalError
from .loader import ImageLoader
from .measurement import MeasurementEngine
from .metadata import MetadataParser
from .models import (
    BatchResult,
    ImageResult,
    MetadataConfig,
    ProcessingResult,
    SampleMetadata,
)
from .segmentation import SegmentationEngine

logger = logging.getLogger("sedimental.orchestrator")


class ProcessingOrchestrator:
    """Coordinates the image processing pipeline.

    Instantiate once and reuse across calls; the MeasurementEngine and
    SegmentationEngine are created lazily on first use so that expensive
    initialisation (Cellpose model load, PyImageJ JVM start) only happens
    when actually needed.
    """

    def __init__(self):
        self._loader = ImageLoader()
        self._seg_engine: Optional[SegmentationEngine] = None
        self._meas_engine: Optional[MeasurementEngine] = None
        self._csv_writer = CSVWriter()
        self._metadata_parser = MetadataParser()

    # ------------------------------------------------------------------
    # Lazy engine accessors
    # ------------------------------------------------------------------

    @property
    def seg_engine(self) -> SegmentationEngine:
        if self._seg_engine is None:
            import os
            use_gpu = os.environ.get("SEDIMENTAL_USE_GPU", "false").lower() == "true"
            if use_gpu:
                # Verify CUDA is actually available before passing gpu=True
                try:
                    import torch
                    use_gpu = torch.cuda.is_available()
                    if not use_gpu:
                        logger.warning("SEDIMENTAL_USE_GPU=true but no CUDA device found; falling back to CPU")
                except ImportError:
                    use_gpu = False
                    logger.warning("SEDIMENTAL_USE_GPU=true but torch not installed; falling back to CPU")
            if use_gpu:
                logger.info("GPU acceleration enabled for segmentation")
            self._seg_engine = SegmentationEngine(gpu=use_gpu)
        return self._seg_engine

    @property
    def meas_engine(self) -> MeasurementEngine:
        if self._meas_engine is None:
            self._meas_engine = MeasurementEngine()
        return self._meas_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_single(
        self,
        image_path: Path,
        metadata: Optional[SampleMetadata] = None,
        save_mask: bool = False,
        output_dir: Optional[Path] = None,
    ) -> ProcessingResult:
        """Process a single image and return measurements.

        Args:
            image_path: Path to the JPEG image file.
            metadata: Optional metadata to associate with the image.
                      If None, an empty SampleMetadata is used.
            save_mask: Whether to save the segmentation mask as a TIFF.
            output_dir: Directory for mask output (required when
                        save_mask=True). Defaults to image_path.parent.

        Returns:
            ProcessingResult with success=True and an ImageResult on
            success, or success=False with an error message on failure.
        """
        image_path = Path(image_path)
        filename = image_path.name
        meta = metadata or SampleMetadata()

        logger.info("Processing '%s'", filename)

        try:
            # 1. Load image
            image = self._loader.load(image_path)

            # 2. Segment grains
            seg_result = self.seg_engine.segment(image, filename=filename)

            # 3. Measure grains
            measurements = self.meas_engine.measure(
                seg_result.mask,
                scale_ppm=meta.scale_ppm,
                filename=filename,
            )

            # 4. Optionally save mask
            mask_path: Optional[Path] = None
            if save_mask:
                dest_dir = Path(output_dir) if output_dir else image_path.parent
                mask_path = dest_dir / (image_path.stem + "_mask.tiff")
                self.seg_engine.save_mask(seg_result.mask, mask_path)

            image_result = ImageResult(
                source_file=filename,
                metadata=meta,
                measurements=measurements,
                segmentation_mask_path=mask_path,
                warnings=seg_result.warnings,
            )

            logger.info(
                "Finished '%s': %d grain(s) measured", filename, len(measurements)
            )
            return ProcessingResult(success=True, image_result=image_result)

        except SedimentalError as exc:
            logger.error("Failed to process '%s': %s", filename, exc)
            return ProcessingResult(success=False, error=str(exc))
        except Exception as exc:
            logger.error("Unexpected error processing '%s': %s", filename, exc)
            return ProcessingResult(success=False, error=f"Unexpected error: {exc}")

    def process_batch(
        self,
        input_path: Path,
        output_path: Path,
        metadata_path: Optional[Path] = None,
        save_masks: bool = False,
        parallel: bool = False,
        max_workers: int = 4,
        progress_callback=None,
    ) -> BatchResult:
        """Process all JPEGs in a directory and write a single CSV.

        Partial failures are handled gracefully: if one image fails,
        processing continues with the remaining images. The failed image
        is recorded in BatchResult.errors.

        Args:
            input_path: Directory containing JPEG images (or a single
                        JPEG file path).
            output_path: Destination path for the aggregated results CSV.
            metadata_path: Optional explicit path to a metadata JSON file.
                           If None, auto-discovery is attempted (looks for
                           metadata.json in the input directory).
            save_masks: Whether to save segmentation masks alongside the CSV.
            parallel: When True, images are processed concurrently using a
                      ThreadPoolExecutor with up to max_workers threads.
            max_workers: Maximum number of worker threads when parallel=True.
            progress_callback: Optional callable(current: int, total: int)
                               invoked after each image completes.

        Returns:
            BatchResult summarising totals, successes, failures, and errors.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # Resolve image list
        if input_path.is_file():
            image_paths = [input_path]
            input_dir = input_path.parent
        else:
            image_paths = self._loader.discover_images(input_path)
            input_dir = input_path

        total = len(image_paths)
        logger.info(
            "Batch processing %d image(s) from '%s' (parallel=%s, max_workers=%d)",
            total, input_dir, parallel, max_workers,
        )

        # Resolve metadata config
        metadata_config: Optional[MetadataConfig] = self._resolve_metadata(
            metadata_path, input_dir
        )

        # Output directory for masks (same directory as the CSV)
        mask_dir = output_path.parent / "masks" if save_masks else None

        def _resolve_meta(filename: str) -> SampleMetadata:
            if metadata_config is not None:
                return self._metadata_parser.get_for_image(metadata_config, filename)
            return SampleMetadata()

        def _process_one(image_path: Path) -> Tuple[Path, "ProcessingResult"]:
            meta = _resolve_meta(image_path.name)
            result = self.process_single(
                image_path,
                metadata=meta,
                save_mask=save_masks,
                output_dir=mask_dir,
            )
            return image_path, result

        results: List[ImageResult] = []
        errors: Dict[str, str] = {}

        completed_count = 0

        if parallel and total > 1:
            workers = min(max_workers, total)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_path = {
                    executor.submit(_process_one, p): p for p in image_paths
                }
                ordered: Dict[Path, "ProcessingResult"] = {}
                for future in as_completed(future_to_path):
                    img_path, proc_result = future.result()
                    ordered[img_path] = proc_result
                    completed_count += 1
                    if progress_callback is not None:
                        progress_callback(completed_count, total)

            for image_path in image_paths:
                proc_result = ordered[image_path]
                if proc_result.success and proc_result.image_result is not None:
                    results.append(proc_result.image_result)
                else:
                    errors[image_path.name] = proc_result.error or "Unknown error"
        else:
            for image_path in image_paths:
                _, proc_result = _process_one(image_path)
                completed_count += 1
                if progress_callback is not None:
                    progress_callback(completed_count, total)
                if proc_result.success and proc_result.image_result is not None:
                    results.append(proc_result.image_result)
                else:
                    errors[image_path.name] = proc_result.error or "Unknown error"

        # Write aggregated CSV (even if empty — creates a header-only file)
        if results:
            self._csv_writer.write(results, output_path)
        else:
            logger.warning(
                "No successful results to write; skipping CSV output"
            )

        successful = len(results)
        failed = len(errors)

        logger.info(
            "Batch complete: %d/%d succeeded, %d failed",
            successful,
            total,
            failed,
        )
        if errors:
            for fname, err in errors.items():
                logger.error("  FAILED '%s': %s", fname, err)

        return BatchResult(
            total_images=total,
            successful=successful,
            failed=failed,
            results=results,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_metadata(
        self,
        metadata_path: Optional[Path],
        input_dir: Path,
    ) -> Optional[MetadataConfig]:
        """Load metadata from an explicit path or auto-discover it.

        Returns None if no metadata file is found or if parsing fails
        during auto-discovery (a warning is logged in that case).
        Raises MetadataParseError if an explicit --metadata path is given
        but cannot be parsed.
        """
        if metadata_path is not None:
            # Explicit path — fail fast on parse error
            logger.info("Loading metadata from '%s'", metadata_path)
            return self._metadata_parser.parse(Path(metadata_path))

        # Auto-discovery: look for metadata.json in the input directory
        auto_path = input_dir / "metadata.json"
        if auto_path.exists():
            logger.info("Auto-discovered metadata at '%s'", auto_path)
            try:
                return self._metadata_parser.parse(auto_path)
            except SedimentalError as exc:
                logger.warning(
                    "Failed to parse auto-discovered metadata '%s': %s; "
                    "proceeding without metadata",
                    auto_path,
                    exc,
                )
                return None

        logger.debug("No metadata file found in '%s'", input_dir)
        return None
