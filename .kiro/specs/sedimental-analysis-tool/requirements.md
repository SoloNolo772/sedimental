# Requirements Document

## Introduction

Sedimental is a sediment analysis tool for geologists that automates the conversion of raw JPEG images of sediment samples into quantitative measurements (size, circularity, roundness). The tool integrates ImageGrains for grain segmentation and PyImageJ for particle analysis, eliminating the need for separate Napari and ImageJ user interfaces. It provides both a CLI interface for batch processing and a Dockerized web interface for remote access.

## Glossary

- **Sedimental_CLI**: The command-line interface component that processes sediment images
- **Sedimental_Web**: The web-based user interface for uploading images and downloading results
- **Segmentation_Engine**: The component that uses ImageGrains algorithms to detect grain boundaries from JPEG images
- **Measurement_Engine**: The component that uses PyImageJ to calculate particle statistics from segmented images
- **Grain**: An individual sediment particle detected in an image
- **Circularity**: A shape descriptor calculated as 4π×area/perimeter², where 1.0 indicates a perfect circle
- **Roundness**: A shape descriptor calculated as 4×area/(π×major_axis²), measuring how close to circular the grain is
- **Feret_Diameter**: The longest distance between any two points along the grain boundary
- **Sample_Metadata**: Information about the sediment sample including filename, sample ID, location, and capture date
- **Segmentation_Mask**: A TIFF image where each grain is labeled with a unique integer value
- **Results_CSV**: The output file containing grain measurements and metadata

## Requirements

### Requirement 1: JPEG Image Input

**User Story:** As a geologist, I want to provide raw JPEG images of sediment samples, so that I can analyze them without manual preprocessing.

#### Acceptance Criteria

1. WHEN a valid JPEG image file is provided, THE Sedimental_CLI SHALL accept it for processing
2. WHEN a directory path is provided, THE Sedimental_CLI SHALL process all JPEG files within that directory
3. IF an invalid or corrupted image file is provided, THEN THE Sedimental_CLI SHALL return a descriptive error message identifying the problematic file
4. IF a non-JPEG file is provided, THEN THE Sedimental_CLI SHALL skip the file and log a warning

### Requirement 2: Grain Segmentation

**User Story:** As a geologist, I want the tool to automatically detect grain boundaries in my images, so that I don't need to manually use Napari.

#### Acceptance Criteria

1. WHEN a JPEG image is processed, THE Segmentation_Engine SHALL detect grain boundaries using ImageGrains algorithms
2. WHEN segmentation completes, THE Segmentation_Engine SHALL produce a Segmentation_Mask in TIFF format
3. THE Segmentation_Engine SHALL assign a unique integer label to each detected Grain
4. WHERE the user requests intermediate outputs, THE Sedimental_CLI SHALL save the Segmentation_Mask to disk
5. IF no grains are detected in an image, THEN THE Segmentation_Engine SHALL log a warning and continue processing

### Requirement 3: Particle Measurement

**User Story:** As a geologist, I want to obtain size, circularity, and roundness measurements for each grain, so that I can characterize my sediment samples.

#### Acceptance Criteria

1. WHEN a Segmentation_Mask is provided, THE Measurement_Engine SHALL calculate measurements for each labeled Grain
2. THE Measurement_Engine SHALL calculate the area in pixels for each Grain
3. THE Measurement_Engine SHALL calculate the perimeter in pixels for each Grain
4. THE Measurement_Engine SHALL calculate the Circularity for each Grain
5. THE Measurement_Engine SHALL calculate the Roundness for each Grain
6. THE Measurement_Engine SHALL calculate the Feret_Diameter for each Grain
7. THE Measurement_Engine SHALL calculate the major and minor axis lengths for each Grain
8. WHERE a scale calibration is provided, THE Measurement_Engine SHALL convert pixel measurements to physical units

### Requirement 4: CSV Output Generation

**User Story:** As a geologist, I want the measurements exported to CSV format, so that I can analyze the data in spreadsheet software or statistical tools.

#### Acceptance Criteria

1. WHEN measurements are complete, THE Sedimental_CLI SHALL generate a Results_CSV file
2. THE Results_CSV SHALL contain one row per detected Grain
3. THE Results_CSV SHALL include columns for area, perimeter, circularity, roundness, Feret_Diameter, major_axis, and minor_axis
4. THE Results_CSV SHALL include the source image filename for each Grain
5. WHERE Sample_Metadata is provided, THE Results_CSV SHALL include sample_id, location_lat, location_lon, and capture_date columns
6. THE Results_CSV SHALL include a scale_factor column containing the pixels-per-millimeter value used for conversion
7. THE Results_CSV SHALL use a header row with descriptive column names
8. FOR ALL valid measurement data, parsing the Results_CSV then formatting then parsing SHALL produce equivalent data (round-trip property)

### Requirement 5: Metadata Input

**User Story:** As a geologist, I want to associate metadata with my samples, so that I can track the origin and context of my measurements.

#### Acceptance Criteria

1. WHERE a metadata.json file exists in the input directory, THE Sedimental_CLI SHALL automatically load and parse it
2. WHERE a --metadata argument is provided, THE Sedimental_CLI SHALL use that file instead of auto-discovered metadata
3. THE metadata JSON SHALL support a "default" object containing metadata applied to all images
4. THE metadata JSON SHALL support an "images" object mapping specific filenames to per-image metadata overrides
5. THE Sedimental_CLI SHALL accept sample_id as a metadata field
6. THE Sedimental_CLI SHALL accept location as a metadata field containing lat and lon properties
7. THE Sedimental_CLI SHALL accept capture_date as a metadata field in ISO 8601 format
8. THE Sedimental_CLI SHALL accept scale_ppm (pixels-per-millimeter) as a metadata field
9. THE Sedimental_CLI SHALL accept custom metadata fields as key-value pairs
10. WHERE per-image metadata is provided, THE Sedimental_CLI SHALL merge it with default metadata, with per-image values taking precedence
11. IF metadata JSON is malformed, THEN THE Sedimental_CLI SHALL return a descriptive parsing error
12. FOR ALL valid metadata JSON, parsing then serializing then parsing SHALL produce an equivalent metadata object (round-trip property)

### Requirement 6: CLI Interface

**User Story:** As a geologist, I want to run the analysis from the command line, so that I can automate batch processing and integrate with existing workflows.

#### Acceptance Criteria

1. THE Sedimental_CLI SHALL accept an input path argument specifying the image file or directory
2. THE Sedimental_CLI SHALL accept an output path argument specifying where to write the Results_CSV
3. WHERE a --metadata argument is provided, THE Sedimental_CLI SHALL load metadata from the specified JSON file instead of auto-discovery
4. WHERE a --save-masks flag is provided, THE Sedimental_CLI SHALL save intermediate Segmentation_Mask files
5. WHERE a --scale argument is provided, THE Sedimental_CLI SHALL use the value for pixel-to-unit conversion (overrides metadata scale_ppm)
6. THE Sedimental_CLI SHALL display a help message when invoked with --help
7. THE Sedimental_CLI SHALL display progress information during processing
8. WHEN processing completes successfully, THE Sedimental_CLI SHALL exit with code 0
9. IF processing fails, THEN THE Sedimental_CLI SHALL exit with a non-zero code and display an error message

### Requirement 7: Web Interface

**User Story:** As a scientist, I want to upload images through a web browser, so that I can use the tool without installing software locally.

#### Acceptance Criteria

1. THE Sedimental_Web SHALL provide a file upload form accepting JPEG images
2. THE Sedimental_Web SHALL allow uploading multiple images in a single request
3. THE Sedimental_Web SHALL provide input fields for Sample_Metadata (sample_id, location, capture_date)
4. WHEN images are uploaded, THE Sedimental_Web SHALL display a processing status indicator
5. WHEN processing completes, THE Sedimental_Web SHALL provide a download link for the Results_CSV
6. WHERE the user requests it, THE Sedimental_Web SHALL provide download links for Segmentation_Mask files
7. IF an upload exceeds the maximum file size, THEN THE Sedimental_Web SHALL display an error message with the size limit
8. THE Sedimental_Web SHALL validate that uploaded files are valid JPEG images before processing

### Requirement 8: Docker Deployment

**User Story:** As a system administrator, I want to deploy the tool as a Docker container, so that I can host it on a server for my team.

#### Acceptance Criteria

1. THE Sedimental_Web SHALL be packaged as a Docker image
2. THE Docker image SHALL include all dependencies for ImageGrains and PyImageJ
3. THE Docker image SHALL expose a configurable port for the web interface
4. WHERE environment variables are set, THE Docker container SHALL use them for configuration
5. THE Docker container SHALL persist uploaded files and results to a mounted volume
6. THE Dockerfile SHALL follow multi-stage build practices to minimize image size
7. WHEN the container starts, THE Sedimental_Web SHALL be ready to accept requests within 60 seconds

### Requirement 9: Batch Processing

**User Story:** As a geologist, I want to process multiple images in a single run, so that I can efficiently analyze large sample sets.

#### Acceptance Criteria

1. WHEN a directory is provided as input, THE Sedimental_CLI SHALL process all JPEG files in the directory
2. THE Sedimental_CLI SHALL aggregate measurements from all images into a single Results_CSV
3. THE Sedimental_CLI SHALL include the source filename for each measurement row
4. WHERE parallel processing is enabled, THE Sedimental_CLI SHALL process multiple images concurrently
5. IF one image fails processing, THEN THE Sedimental_CLI SHALL log the error and continue with remaining images
6. WHEN batch processing completes, THE Sedimental_CLI SHALL report the total number of images processed and any failures

### Requirement 10: Scale Calibration

**User Story:** As a geologist, I want to specify the image scale, so that I can obtain measurements in real-world units like millimeters.

#### Acceptance Criteria

1. WHERE a pixels-per-unit value is provided, THE Measurement_Engine SHALL convert all length measurements to the specified unit
2. WHERE a pixels-per-unit value is provided, THE Measurement_Engine SHALL convert area measurements to squared units
3. THE Results_CSV SHALL include a units column indicating the measurement unit used
4. IF no scale is provided, THEN THE Measurement_Engine SHALL report measurements in pixels
5. THE Sedimental_CLI SHALL accept scale as a command-line argument in pixels-per-millimeter format

### Requirement 11: Error Handling and Logging

**User Story:** As a geologist, I want clear error messages and logs, so that I can troubleshoot issues with my analysis.

#### Acceptance Criteria

1. THE Sedimental_CLI SHALL log all processing steps with timestamps
2. IF an image cannot be read, THEN THE Sedimental_CLI SHALL log the filename and error reason
3. IF segmentation fails, THEN THE Sedimental_CLI SHALL log the failure reason and continue processing
4. IF measurement calculation fails, THEN THE Sedimental_CLI SHALL log which measurement failed and why
5. WHERE a verbose flag is provided, THE Sedimental_CLI SHALL output detailed debug information
6. THE Sedimental_CLI SHALL write logs to both console and a log file
