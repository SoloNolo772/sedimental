"""
Sedimental CLI - Command-line interface for sediment analysis.

This module provides the entry point for the sedimental command-line tool.
"""

import argparse
import sys


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
        print(f"Processing: {args.input}")
        print("Note: Full processing pipeline not yet implemented")
        return 0

    if args.command == 'web':
        print(f"Starting web server on port {args.port}")
        print("Note: Web interface not yet implemented")
        return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
