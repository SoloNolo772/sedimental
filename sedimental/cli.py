"""
Sedimental CLI - Command-line interface for sediment analysis.

This module provides the entry point for the sedimental command-line tool.
Outside the container it is a thin wrapper that invokes Docker commands.
Inside the container it calls the ProcessingOrchestrator directly.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .logging import configure_logging
from .orchestrator import ProcessingOrchestrator

# Docker image name (matches docker-compose.yml)
DOCKER_IMAGE = "sedimental:latest"

# Container volume mount points
CONTAINER_INPUT = "/data/input"
CONTAINER_OUTPUT = "/data/output"
CONTAINER_TEMP = "/data/temp"


def _resolve_path(p: str) -> Path:
    """Return an absolute Path for the given string."""
    return Path(p).resolve()


def run_docker_process(args) -> int:
    """Invoke Docker container for image processing.

    Maps local input/output paths to container volume mounts, passes CLI
    arguments to the container entrypoint, and streams container output.

    Requirements: 6.7
    """
    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)

    # Determine whether input is a file or directory so we can set up the
    # correct volume mount and container-side path.
    if input_path.is_dir():
        local_input_dir = input_path
        container_input_arg = CONTAINER_INPUT
    else:
        local_input_dir = input_path.parent
        container_input_arg = f"{CONTAINER_INPUT}/{input_path.name}"

    # Output is always a file; mount its parent directory.
    local_output_dir = output_path.parent
    local_output_dir.mkdir(parents=True, exist_ok=True)
    container_output_arg = f"{CONTAINER_OUTPUT}/{output_path.name}"

    # Build the docker run command.
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{local_input_dir}:{CONTAINER_INPUT}:ro",
        "-v", f"{local_output_dir}:{CONTAINER_OUTPUT}",
        DOCKER_IMAGE,
        "process",
        container_input_arg,
        "-o", container_output_arg,
    ]

    # Optional flags forwarded to the container entrypoint.
    if getattr(args, "metadata", None):
        metadata_path = _resolve_path(args.metadata)
        # Mount metadata file's directory as a third volume if it differs from
        # the input directory, then reference it inside the container.
        if metadata_path.parent.resolve() == local_input_dir:
            container_metadata_arg = f"{CONTAINER_INPUT}/{metadata_path.name}"
        else:
            # Mount under /data/temp for simplicity.
            cmd = (
                cmd[:cmd.index(DOCKER_IMAGE)]
                + ["-v", f"{metadata_path.parent}:{CONTAINER_TEMP}:ro"]
                + cmd[cmd.index(DOCKER_IMAGE):]
            )
            container_metadata_arg = f"{CONTAINER_TEMP}/{metadata_path.name}"
        cmd += ["--metadata", container_metadata_arg]

    if getattr(args, "save_masks", False):
        cmd.append("--save-masks")

    if getattr(args, "remove_overlaps", False):
        cmd.append("--remove-overlaps")

    if getattr(args, "scale", None) is not None:
        cmd += ["--scale", str(args.scale)]

    if getattr(args, "verbose", False):
        cmd.append("--verbose")

    # Stream output so the user sees progress (Req 6.7).
    print(f"[sedimental] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, text=True)
        return result.returncode
    except FileNotFoundError:
        print(
            "Error: 'docker' command not found. "
            "Please install Docker: https://docs.docker.com/get-docker/",
            file=sys.stderr,
        )
        return 1


def run_docker_web(args) -> int:
    """Invoke Docker container for the web interface.

    Starts the web service container with port mapping so the browser-based
    interface is accessible on the requested port.

    Requirements: 8.3
    """
    port = getattr(args, "port", 8080)

    cmd = [
        "docker", "run", "--rm",
        "-p", f"{port}:{port}",
        "-e", f"SEDIMENTAL_WEB_PORT={port}",
        DOCKER_IMAGE,
        "web",
        "--port", str(port),
    ]

    print(f"[sedimental] Starting web interface on port {port}...")
    print(f"[sedimental] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, text=True)
        return result.returncode
    except FileNotFoundError:
        print(
            "Error: 'docker' command not found. "
            "Please install Docker: https://docs.docker.com/get-docker/",
            file=sys.stderr,
        )
        return 1


def run_process_internal(args) -> int:
    """Run the processing pipeline directly (inside-container execution).

    Calls ProcessingOrchestrator.process_batch() and maps BatchResult to an
    exit code following Property 17 / Requirements 6.8 and 6.9:

    - All images succeed  → exit 0
    - Partial failure     → exit 0  (warnings logged)
    - All images fail     → exit 1  (error message printed)
    - No images found     → exit 1  (error message printed)

    Requirements: 6.8, 6.9
    """
    log_file_env = os.environ.get("SEDIMENTAL_LOG_FILE")
    log_file = Path(log_file_env) if log_file_env else None
    configure_logging(verbose=getattr(args, "verbose", False), log_file=log_file)

    input_path = Path(args.input)
    output_path = Path(args.output)
    metadata_path = Path(args.metadata) if getattr(args, "metadata", None) else None
    save_masks = getattr(args, "save_masks", False)
    remove_overlaps = getattr(args, "remove_overlaps", False)

    orchestrator = ProcessingOrchestrator()

    try:
        batch = orchestrator.process_batch(
            input_path=input_path,
            output_path=output_path,
            metadata_path=metadata_path,
            save_masks=save_masks,
            remove_overlaps=remove_overlaps,
        )
    except Exception as exc:
        print(f"Error: processing failed: {exc}", file=sys.stderr)
        return 1

    # Requirement 6.9 – total failure: no images succeeded
    if batch.successful == 0:
        if batch.total_images == 0:
            print("Error: no JPEG images found in the specified input path.", file=sys.stderr)
        else:
            print(
                f"Error: all {batch.total_images} image(s) failed to process.",
                file=sys.stderr,
            )
            for fname, err in batch.errors.items():
                print(f"  {fname}: {err}", file=sys.stderr)
        return 1

    # Partial failure – warn but exit 0 (Property 17)
    if batch.failed > 0:
        print(
            f"Warning: {batch.failed} of {batch.total_images} image(s) failed; "
            f"{batch.successful} succeeded.",
            file=sys.stderr,
        )
        for fname, err in batch.errors.items():
            print(f"  {fname}: {err}", file=sys.stderr)

    # Requirement 6.8 – success
    print(
        f"Processing complete: {batch.successful}/{batch.total_images} image(s) succeeded. "
        f"Results written to {output_path}"
    )
    return 0


def main():
    """Entry point for sedimental CLI."""
    parser = argparse.ArgumentParser(
        description='Sedimental: Sediment grain analysis tool'
    )
    subparsers = parser.add_subparsers(dest='command')

    # Process command
    process_parser = subparsers.add_parser(
        'process',
        help='Process sediment images'
    )
    process_parser.add_argument(
        'input',
        help='Image file or directory to process'
    )
    process_parser.add_argument(
        '-o', '--output',
        help='Output CSV path',
        default='results.csv'
    )
    process_parser.add_argument(
        '--metadata',
        help='Metadata JSON file path'
    )
    process_parser.add_argument(
        '--save-masks',
        action='store_true',
        help='Save intermediate segmentation masks'
    )
    process_parser.add_argument(
        '--remove-overlaps',
        action='store_true',
        help=(
            'Detect and exclude partially-covered (overlapping) grains '
            'from the results using shape-based heuristics. When combined '
            'with --save-masks, also writes an *_overlap_analysis.csv '
            'and preserves the unfiltered mask as *_mask_original.tiff.'
        ),
    )
    process_parser.add_argument(
        '--scale',
        type=float,
        help='Pixels per millimeter for unit conversion'
    )
    process_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    # Web command
    web_parser = subparsers.add_parser(
        'web',
        help='Start web interface'
    )
    web_parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port for web server (default: 8080)'
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == 'process':
        # Inside the container: run the orchestrator directly so we can
        # return a meaningful exit code (Requirements 6.8, 6.9).
        if os.environ.get('SEDIMENTAL_INSIDE_CONTAINER'):
            return run_process_internal(args)
        return run_docker_process(args)

    if args.command == 'web':
        return run_docker_web(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
