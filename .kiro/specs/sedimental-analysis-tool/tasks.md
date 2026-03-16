# Implementation Plan: Sedimental Analysis Tool

## Overview

This implementation follows a Docker-first architecture where all processing runs inside containers. The CLI is a thin wrapper that invokes `docker run` commands. Implementation proceeds in five phases: Docker Foundation, Core Processing Pipeline, CLI Interface, Web Interface, and Integration & Polish.

## Tasks

- [ ] 1. Phase 1: Docker Foundation
  - [x] 1.1 Create base Dockerfile with multi-stage build
    - Set up python:3.10-slim base image
    - Install OpenJDK 11 for PyImageJ
    - Install Maven dependencies
    - Configure PyImageJ and ImageJ2 runtime
    - Install Napari core (headless mode)
    - Install ImageGrains package
    - _Requirements: 8.1, 8.2, 8.6_

  - [x] 1.2 Create Docker Compose configuration for development
    - Define sedimental service with volume mounts
    - Configure /data/input, /data/output, /data/temp directories
    - Set up environment variables for configuration
    - _Requirements: 8.4, 8.5_

  - [x] 1.3 Create entrypoint script and health check
    - Implement container startup script
    - Add health check endpoint for readiness
    - Verify ImageGrains and PyImageJ initialization
    - _Requirements: 8.7_

  - [x] 1.4 Checkpoint - Verify Docker build and startup
    - Ensure Docker image builds successfully
    - Verify container starts and passes health check within 60 seconds
    - Ask the user if questions arise

- [ ] 2. Phase 2: Core Processing Pipeline - Data Models and Utilities
  - [x] 2.1 Create project structure and error hierarchy
    - Create sedimental/ package structure
    - Implement SedimentalError base exception
    - Implement ImageError, InvalidImageError, UnsupportedFormatError
    - Implement SegmentationError, MeasurementError
    - Implement MetadataParseError, OutputError
    - _Requirements: 11.2, 11.3, 11.4_

  - [x] 2.2 Implement core data models
    - Create MeasurementUnit enum (PIXELS, MILLIMETERS)
    - Create SampleMetadata dataclass with merge() method
    - Create MetadataConfig dataclass
    - Create GrainMeasurement dataclass
    - Create SegmentationResult dataclass
    - Create ImageResult, ProcessingResult, BatchResult dataclasses
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [x] 2.3 Write property test for metadata merge precedence
    - **Property 14: Metadata Merge Precedence**
    - **Validates: Requirements 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10**

  - [x] 2.4 Implement logging configuration
    - Create configure_logging() function
    - Support verbose flag for debug output
    - Support log file output
    - Configure per-component log levels
    - _Requirements: 11.1, 11.5, 11.6_

- [ ] 3. Phase 2: Core Processing Pipeline - ImageLoader
  - [x] 3.1 Implement ImageLoader class
    - Implement load() method for JPEG validation and loading
    - Implement discover_images() for directory scanning
    - Support .jpg and .jpeg extensions (case-insensitive)
    - Raise InvalidImageError for corrupted files
    - Skip non-JPEG files with warning log
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 3.2 Write property test for valid JPEG acceptance
    - **Property 1: Valid JPEG Acceptance**
    - **Validates: Requirements 1.1**

  - [x] 3.3 Write property test for directory JPEG discovery
    - **Property 2: Directory JPEG Discovery**
    - **Validates: Requirements 1.2, 9.1**

  - [x] 3.4 Write property test for invalid file error identification
    - **Property 3: Invalid File Error Identification**
    - **Validates: Requirements 1.3**

  - [x] 3.5 Write property test for non-JPEG file filtering
    - **Property 4: Non-JPEG File Filtering**
    - **Validates: Requirements 1.4**

- [ ] 4. Phase 2: Core Processing Pipeline - SegmentationEngine
  - [x] 4.1 Implement SegmentationEngine class
    - Implement segment() method using ImageGrains algorithms
    - Return SegmentationResult with labeled mask and grain count
    - Assign unique integer labels to each grain (0 = background)
    - Log warning if no grains detected
    - Implement save_mask() for TIFF output
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 4.2 Write property test for segmentation mask validity
    - **Property 5: Segmentation Mask Validity**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 4.3 Write property test for mask persistence on request
    - **Property 6: Mask Persistence on Request**
    - **Validates: Requirements 2.4**

- [ ] 5. Phase 2: Core Processing Pipeline - MeasurementEngine
  - [ ] 5.1 Implement MeasurementEngine class
    - Implement lazy PyImageJ initialization
    - Implement measure() method for particle statistics
    - Calculate area, perimeter, circularity, roundness
    - Calculate feret_diameter, major_axis, minor_axis
    - Support scale_ppm for unit conversion
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ]* 5.2 Write property test for measurement count consistency
    - **Property 7: Measurement Count Consistency**
    - **Validates: Requirements 3.1**

  - [ ]* 5.3 Write property test for measurement value invariants
    - **Property 8: Measurement Value Invariants**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

  - [ ]* 5.4 Write property test for scale conversion correctness
    - **Property 9: Scale Conversion Correctness**
    - **Validates: Requirements 3.8, 10.1, 10.2**

- [ ] 6. Phase 2: Core Processing Pipeline - MetadataParser
  - [ ] 6.1 Implement MetadataParser class
    - Implement parse() method for JSON loading
    - Support "default" and "images" structure
    - Implement get_for_image() with merge logic
    - Raise MetadataParseError for malformed JSON
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.10, 5.11_

  - [ ]* 6.2 Write property test for metadata auto-discovery
    - **Property 12: Metadata Auto-Discovery**
    - **Validates: Requirements 5.1**

  - [ ]* 6.3 Write property test for metadata CLI override
    - **Property 13: Metadata CLI Override**
    - **Validates: Requirements 5.2**

  - [ ]* 6.4 Write property test for metadata JSON round-trip
    - **Property 15: Metadata JSON Round-Trip**
    - **Validates: Requirements 5.12**

  - [ ]* 6.5 Write property test for malformed metadata error
    - **Property 16: Malformed Metadata Error**
    - **Validates: Requirements 5.11**

- [ ] 7. Phase 2: Core Processing Pipeline - CSVWriter
  - [ ] 7.1 Implement CSVWriter class
    - Implement write() method with all required columns
    - Include source_file, grain_id, measurements, units, scale_factor
    - Include metadata columns (sample_id, location, capture_date, submitted_by)
    - Implement parse() method for round-trip support
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 7.2 Write property test for CSV round-trip
    - **Property 10: CSV Round-Trip**
    - **Validates: Requirements 4.8**

  - [ ]* 7.3 Write property test for CSV structure invariants
    - **Property 11: CSV Structure Invariants**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

  - [ ]* 7.4 Write property test for units column correctness
    - **Property 20: Units Column Correctness**
    - **Validates: Requirements 10.3, 10.4**

- [ ] 8. Phase 2: Core Processing Pipeline - ProcessingOrchestrator
  - [ ] 8.1 Implement ProcessingOrchestrator class
    - Implement process_single() for single image processing
    - Implement process_batch() for directory processing
    - Coordinate ImageLoader, SegmentationEngine, MeasurementEngine, CSVWriter
    - Handle partial failures gracefully (continue on error)
    - Aggregate results into single CSV
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6_

  - [ ]* 8.2 Write property test for partial batch failure resilience
    - **Property 18: Partial Batch Failure Resilience**
    - **Validates: Requirements 9.5**

  - [ ]* 8.3 Write property test for batch result aggregation
    - **Property 19: Batch Result Aggregation**
    - **Validates: Requirements 9.2, 9.6**

  - [ ]* 8.4 Implement parallel processing support
    - Add parallel flag and max_workers parameter
    - Use concurrent.futures for parallel image processing
    - _Requirements: 9.4_

- [ ] 9. Checkpoint - Core pipeline verification
  - Ensure all core components work together inside Docker
  - Run unit tests for all pipeline components
  - Ask the user if questions arise

- [ ] 10. Phase 3: CLI Interface
  - [ ] 10.1 Implement CLI argument parser
    - Create main() entry point with argparse
    - Add 'process' subcommand with input/output arguments
    - Add --metadata, --save-masks, --scale, --verbose flags
    - Add 'web' subcommand with --port argument
    - Implement --help output
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ] 10.2 Implement Docker invocation wrapper
    - Implement run_docker_process() for process command
    - Map local paths to container volume mounts
    - Pass CLI arguments to container entrypoint
    - Capture and display container output
    - Implement run_docker_web() for web command
    - _Requirements: 6.7, 8.3_

  - [ ] 10.3 Implement exit code handling
    - Return exit code 0 on success
    - Return non-zero exit code on failure
    - Display error messages on failure
    - _Requirements: 6.8, 6.9_

  - [ ]* 10.4 Write property test for exit code correctness
    - **Property 17: Exit Code Correctness**
    - **Validates: Requirements 6.8, 6.9**

- [ ] 11. Checkpoint - CLI verification
  - Test CLI with single image and directory inputs
  - Verify metadata auto-discovery and override
  - Verify --save-masks flag produces TIFF outputs
  - Ask the user if questions arise

- [ ] 12. Phase 4: Web Interface - FastAPI Server
  - [ ] 12.1 Implement FastAPI application and routes
    - Create FastAPI app with CORS configuration
    - Implement POST /api/jobs for job creation
    - Accept file uploads and metadata form fields
    - Implement GET /api/jobs/{job_id} for status
    - Implement GET /api/jobs/{job_id}/results for CSV download
    - Implement GET /api/jobs/{job_id}/masks/{filename} for mask download
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 12.2 Implement file upload validation
    - Validate uploaded files are valid JPEGs
    - Enforce maximum file size limit
    - Return descriptive error messages
    - _Requirements: 7.7, 7.8_

  - [ ] 12.3 Implement job queue with SQLite
    - Create jobs table with status tracking
    - Implement job creation and status updates
    - Track progress (current/total images)
    - Store result paths and error messages
    - _Requirements: 7.4_

  - [ ] 12.4 Implement background job processing
    - Process jobs asynchronously
    - Update job status during processing
    - Store results in job-specific directories
    - _Requirements: 7.4, 7.5_

- [ ] 13. Phase 4: Web Interface - Frontend
  - [ ] 13.1 Create minimal web frontend
    - Create HTML upload form
    - Add metadata input fields (sample_id, location, capture_date)
    - Add save_masks checkbox
    - Display processing status indicator
    - Provide download links for results
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 14. Checkpoint - Web interface verification
  - Test file upload and job creation
  - Verify job status polling
  - Test results and mask downloads
  - Ask the user if questions arise

- [ ] 15. Phase 5: Integration & Polish
  - [ ] 15.1 Write CLI integration tests
    - Test single image processing end-to-end
    - Test batch processing with metadata
    - Test error handling for invalid inputs
    - _Requirements: 6.1, 6.2, 9.1, 9.5_

  - [ ] 15.2 Write web API integration tests
    - Test upload and download flow
    - Test job status transitions
    - Test concurrent job handling
    - _Requirements: 7.1, 7.4, 7.5_

  - [ ] 15.3 Write Docker integration tests
    - Test container startup and health check
    - Test volume mount functionality
    - Test web service availability
    - _Requirements: 8.1, 8.5, 8.7_

  - [ ] 15.4 Create test fixtures and sample data
    - Create sample JPEG images for testing
    - Create sample metadata.json files
    - Create corrupted image files for error testing
    - Set up Hypothesis generators for property tests

- [ ] 16. Final checkpoint - Full system verification
  - Run complete test suite (unit, property, integration)
  - Verify Docker image builds and runs correctly
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional property-based tests that can be skipped for faster MVP
- All processing runs inside Docker containers - the CLI is a thin wrapper
- PyImageJ initialization is expensive; the MeasurementEngine uses lazy initialization
- The web interface uses SQLite for job tracking, persisted to mounted volume
- Parallel processing (task 8.4) is optional and can be deferred
- Each phase builds on the previous - Docker foundation must be complete before core pipeline
- Property tests use Hypothesis library with minimum 100 iterations per test
