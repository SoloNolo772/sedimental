# Requirements Document

## Introduction

This document specifies requirements for enhancing the Sedimental single-page application (SPA) with acknowledgements, contact information, improved input fields, branding elements, legal statements, and activity logging clarification. The enhancements maintain the clean design aesthetic while adding necessary attribution, legal, and usability improvements.

## Glossary

- **SPA**: The single-page application served from `sedimental/static/index.html` that provides the web interface for sediment grain analysis
- **Acknowledgements_Section**: A UI section crediting the AI components (ImageJ and ImageGrains) integrated in the application
- **Contact_Link**: A mailto hyperlink enabling users to contact the site maintainer
- **Latitude_Input**: The numeric input field for entering sample location latitude
- **Longitude_Input**: The numeric input field for entering sample location longitude
- **Favicon**: A small icon displayed in browser tabs and bookmarks representing the site
- **Copyright_Statement**: A legal notice asserting intellectual property ownership
- **Data_Ownership_Notice**: A statement informing users about data ownership and preservation responsibilities
- **Decimal_Format**: Coordinate notation using decimal degrees (e.g., 38.8977) rather than degrees/minutes/seconds or cardinal directions
- **Spinner**: Browser-native increment/decrement arrows on number input fields
- **Footer_Section**: A dedicated page section below the main content containing secondary information
- **Page_Layout**: The overall visual arrangement of elements on the SPA
- **Privacy_Modal**: A modal dialog element displayed inline on the SPA that presents the privacy statement without navigating to a separate page
- **Privacy_Link**: A hyperlink in the footer that opens the Privacy_Modal when clicked

## Requirements

### Requirement 1: ImageJ Acknowledgement

**User Story:** As a site visitor, I want to see proper attribution for ImageJ, so that the open-source project receives appropriate credit for its contribution.

#### Acceptance Criteria

1. THE Acknowledgements_Section SHALL display a clickable hyperlink to the ImageJ Git repository at https://github.com/imagej/ImageJ
2. THE Acknowledgements_Section SHALL display a credit for ImageJ containing the project name "ImageJ" and the repository URL https://github.com/imagej/ImageJ as a clickable hyperlink
3. WHEN a user clicks the ImageJ repository link, THE SPA SHALL open the link in a new browser tab

### Requirement 2: ImageGrains Acknowledgement

**User Story:** As a site visitor, I want to see proper attribution for ImageGrains, so that the open-source project receives appropriate credit for its contribution.

#### Acceptance Criteria

1. THE Acknowledgements_Section SHALL display a clickable hyperlink to the ImageGrains Git repository at https://github.com/dmair1989/imagegrains
2. THE Acknowledgements_Section SHALL display a credit for ImageGrains that includes the project name "ImageGrains" and the repository URL as a clickable hyperlink
3. WHEN a user clicks the ImageGrains repository link, THE SPA SHALL open the link in a new browser tab
4. THE Acknowledgements_Section SHALL be visible on the main page of the SPA without requiring user interaction to reveal it

### Requirement 3: Maintainer Contact Link

**User Story:** As a site visitor, I want to contact the site maintainer, so that I can ask questions or report issues.

#### Acceptance Criteria

1. THE SPA SHALL display a contact link containing the maintainer name "Nolan Powers" and the site domain "sedimental.io" in the visible link text
2. THE Contact_Link SHALL use the mailto protocol with the address npowers@umw.edu as the href value
3. THE Contact_Link SHALL have an accessible name that identifies it as a contact link for assistive technology users

### Requirement 4: Latitude/Longitude Decimal Format Clarification

**User Story:** As a user entering sample location data, I want clear guidance that coordinates should be in decimal format, so that I enter data correctly without confusion.

#### Acceptance Criteria

1. THE Latitude_Input SHALL display placeholder text showing a decimal format example within the valid range of -90 to 90 (e.g., "Latitude (e.g., 40.7128)")
2. THE Longitude_Input SHALL display placeholder text showing a decimal format example within the valid range of -180 to 180 (e.g., "Longitude (e.g., -74.0060)")
3. THE SPA SHALL NOT display degree/minutes/seconds or cardinal direction format examples in the coordinate input guidance

### Requirement 5: Remove Coordinate Input Spinners

**User Story:** As a user entering precise coordinates, I want the increment/decrement spinners removed from coordinate fields, so that I can enter high-precision values without accidental modification.

#### Acceptance Criteria

1. THE Latitude_Input SHALL NOT display browser-native spinner controls
2. THE Longitude_Input SHALL NOT display browser-native spinner controls
3. THE Latitude_Input SHALL accept values in the range -90.0000 to 90.0000 with 4 to 8 decimal places of precision
4. THE Longitude_Input SHALL accept values in the range -180.0000 to 180.0000 with 4 to 8 decimal places of precision
5. IF a user enters a latitude value outside the range -90.0 to 90.0, THEN THE Latitude_Input SHALL indicate the value is invalid and prevent form submission
6. IF a user enters a longitude value outside the range -180.0 to 180.0, THEN THE Longitude_Input SHALL indicate the value is invalid and prevent form submission

### Requirement 6: Favicon

**User Story:** As a site visitor, I want to see a distinctive favicon in my browser tab, so that I can easily identify the Sedimental site among my open tabs.

#### Acceptance Criteria

1. THE SPA SHALL include a favicon link element in the HTML head section with the rel attribute set to "icon"
2. THE Favicon file SHALL use a browser-compatible format (ICO, PNG, or SVG)
3. THE Favicon design SHALL depict a recognizable sediment-related element such as a grain shape, layered strata pattern, or particle cluster
4. WHEN a client requests the favicon path, THE web server SHALL return the favicon file with an HTTP 200 status code

### Requirement 7: Copyright Statement

**User Story:** As the site owner, I want a copyright statement displayed, so that intellectual property ownership is clearly asserted.

#### Acceptance Criteria

1. THE SPA SHALL display a copyright statement in the page footer that is visible without scrolling or navigation, assigning ownership to Nolan Powers
2. THE Copyright_Statement SHALL include the year 2026
3. THE Copyright_Statement SHALL contain text indicating ownership of both the page content and the application functionality

### Requirement 8: Data Ownership Notice

**User Story:** As a user of the analysis service, I want to understand data ownership and preservation policies, so that I know my responsibilities for saving results.

#### Acceptance Criteria

1. THE Data_Ownership_Notice SHALL state that all data associated with a submitted analysis job, including uploaded input files and generated output results, belongs to the user who submitted it
2. THE Data_Ownership_Notice SHALL state that data may be deleted from the site at any time without prior notification and that no minimum retention period is guaranteed
3. THE Data_Ownership_Notice SHALL advise users to download and save their results immediately after they are produced
4. THE Data_Ownership_Notice SHALL be displayed to users before they submit data for analysis

### Requirement 9: Activity Logging Without Third-Party Tracking

**User Story:** As the site owner, I want basic activity logging without Google tracking or cookies, so that I can monitor site usage while respecting user privacy.

#### Acceptance Criteria

1. THE SPA SHALL NOT include scripts loaded from Google domains including google-analytics.com, googletagmanager.com, and googlesyndication.com
2. THE SPA SHALL NOT set cookies for the purpose of tracking user behavior across sessions or identifying users for analytics, while functional cookies for session management are permitted
3. IF the site owner enables activity logging, THEN THE SPA SHALL rely on server-side logging through the AWS deployment infrastructure including Caddy access logs and application logs written to the mounted data volume
4. THE SPA SHALL NOT include any third-party analytics or tracking libraries that transmit user data to external services

### Requirement 11: Privacy Statement Modal

**User Story:** As a European user or privacy-conscious visitor, I want to read a clear privacy statement, so that I understand what data is collected and how it is used in compliance with GDPR transparency requirements.

#### Acceptance Criteria

1. THE Footer_Section SHALL display a Privacy_Link with visible text "Privacy" that opens the Privacy_Modal when clicked
2. THE Privacy_Modal SHALL be implemented using the native HTML `<dialog>` element and SHALL NOT require navigation to a separate page
3. WHEN a user clicks the Privacy_Link, THE Privacy_Modal SHALL become visible overlaying the page content
4. THE Privacy_Modal SHALL contain a close button (labelled "×" or "Close") that dismisses the modal when clicked
5. WHEN a user presses the Escape key while the Privacy_Modal is open, THE Privacy_Modal SHALL close
6. THE Privacy_Modal SHALL state what data is collected (uploaded images, metadata, server-side access logs)
7. THE Privacy_Modal SHALL state the legal basis for processing (performance of the analysis service requested by the user)
8. THE Privacy_Modal SHALL state that no data is shared with third parties
9. THE Privacy_Modal SHALL state the data retention policy (temporary storage, may be deleted at any time)
10. THE Privacy_Modal SHALL provide a contact email address for data subject rights requests
11. THE Privacy_Modal SHALL be accessible, with focus moving into the dialog when opened and returning to the Privacy_Link when closed

### Requirement 10: Maintain Clean Design Aesthetic

**User Story:** As a site visitor, I want the enhanced page to remain clean and uncluttered, so that the primary analysis functionality remains prominent.

#### Acceptance Criteria

1. THE Page_Layout SHALL display the main analysis form card above all secondary content elements (Acknowledgements_Section, Copyright_Statement, Data_Ownership_Notice, Contact_Link)
2. THE Footer_Section SHALL be positioned below the main form card and results section, visually separated from the primary content area
3. THE Footer_Section SHALL contain the Acknowledgements_Section, Copyright_Statement, Data_Ownership_Notice, and Contact_Link grouped together
4. THE Footer_Section SHALL use smaller text size than the main form labels to establish visual hierarchy with secondary content subordinate to primary functionality
