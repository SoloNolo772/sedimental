"""
Quick helper: segment a JPEG from data/input/ and save the mask to data/output/.

Usage (from workspace root):
    docker compose run --rm sedimental python segment_image.py your_image.jpg
"""

import sys
from pathlib import Path

from sedimental.loader import ImageLoader
from sedimental.segmentation import SegmentationEngine


def main():
    if len(sys.argv) < 2:
        print("Usage: python segment_image.py <filename.jpg>")
        sys.exit(1)

    filename = sys.argv[1]
    input_path = Path("/data/input") / filename
    output_path = Path("/data/output") / (Path(filename).stem + "_mask.tiff")

    print(f"Loading {input_path} ...")
    image = ImageLoader().load(input_path)
    print(f"Image shape: {image.shape}")

    print("Segmenting (this may take a moment on first run) ...")
    engine = SegmentationEngine()
    result = engine.segment(image, filename)
    print(f"Detected {result.grain_count} grain(s)")

    if result.warnings:
        for w in result.warnings:
            print(f"Warning: {w}")

    engine.save_mask(result.mask, output_path)
    print(f"Mask saved -> data/output/{output_path.name}")


if __name__ == "__main__":
    main()
