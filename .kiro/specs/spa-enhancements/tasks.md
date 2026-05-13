# Implementation Plan: SPA Enhancements

## Overview

This implementation plan covers frontend enhancements to the Sedimental SPA including acknowledgements, contact information, improved coordinate inputs, favicon, legal statements, privacy compliance, and a GDPR-compliant privacy statement modal. All changes are made to `sedimental/static/index.html` with one new asset file for the favicon.

## Tasks

- [x] 1. Add CSS styles for new components
    - [x] 1.1 Add spinner removal CSS for coordinate inputs
        - Add `.no-spinner` class with `-webkit-appearance: none` for WebKit browsers
        - Add `-moz-appearance: textfield` for Firefox
        - Target `::-webkit-outer-spin-button` and `::-webkit-inner-spin-button` pseudo-elements
        - _Requirements: 5.1, 5.2_

    - [x] 1.2 Add footer section CSS styles
        - Add `.site-footer` class with max-width 640px, centered, smaller font-size (0.8rem)
        - Add `.data-notice` class with warning background color (#fef3c7) and border
        - Add link styles for footer (color #2563eb, hover underline)
        - Add margin/spacing for `.acknowledgements`, `.copyright`, `.contact` classes
        - _Requirements: 10.4_

- [x] 2. Update coordinate input fields
    - [x] 2.1 Modify latitude input with decimal format placeholder and no-spinner class
        - Change placeholder from "Latitude" to "Latitude (e.g., 40.7128)"
        - Add `class="no-spinner"` to the input element
        - Verify existing `min="-90" max="90" step="any"` attributes are preserved
        - _Requirements: 4.1, 5.1, 5.3_

    - [x] 2.2 Modify longitude input with decimal format placeholder and no-spinner class
        - Change placeholder from "Longitude" to "Longitude (e.g., -74.0060)"
        - Add `class="no-spinner"` to the input element
        - Verify existing `min="-180" max="180" step="any"` attributes are preserved
        - _Requirements: 4.2, 5.2, 5.4_

- [x] 3. Add favicon
    - [x] 3.1 Create favicon asset file
        - Create `sedimental/static/favicon.png` (32x32 pixels)
        - Design should depict sediment-related imagery (grain shape, layered strata, or particle cluster)
        - Use PNG format for cross-browser compatibility
        - _Requirements: 6.2, 6.3_

    - [x] 3.2 Add favicon link element to HTML head
        - Add `<link rel="icon" type="image/png" href="/static/favicon.png">` in the `<head>` section
        - _Requirements: 6.1_

    - [x] 3.3 Write integration test for favicon serving
        - Test that GET `/static/favicon.png` returns HTTP 200
        - Test that response content-type is `image/png`
        - Add test to `tests/test_web_api.py` or create new `tests/test_spa_structure.py`
        - _Requirements: 6.4_

- [x] 4. Checkpoint - Verify coordinate inputs and favicon
    - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Add footer section with legal and attribution content
    - [x] 5.1 Create footer HTML structure
        - Add `<footer class="site-footer">` element after the closing `</div>` of the main card
        - Add `<div class="footer-content">` wrapper inside footer
        - _Requirements: 10.2, 10.3_

    - [x] 5.2 Add data ownership notice
        - Add paragraph with class `data-notice` as first element in footer
        - Include text stating: data belongs to user, may be deleted without notice, advise immediate download
        - Position before acknowledgements to ensure visibility before form submission
        - _Requirements: 8.1, 8.2, 8.3, 8.4_

    - [x] 5.3 Add acknowledgements section with ImageJ and ImageGrains links
        - Add paragraph with class `acknowledgements`
        - Add ImageJ link: `<a href="https://github.com/imagej/ImageJ" target="_blank" rel="noopener">ImageJ</a>`
        - Add ImageGrains link: `<a href="https://github.com/dmair1989/imagegrains" target="_blank" rel="noopener">ImageGrains</a>`
        - Include "Powered by" text to provide context
        - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4_

    - [x] 5.4 Add copyright statement
        - Add paragraph with class `copyright`
        - Include text: "© 2026 Nolan Powers. All rights reserved."
        - _Requirements: 7.1, 7.2, 7.3_

    - [x] 5.5 Add contact link
        - Add paragraph with class `contact`
        - Add mailto link: `<a href="mailto:npowers@umw.edu" aria-label="Contact Nolan Powers at sedimental.io">Nolan Powers – sedimental.io</a>`
        - Include `aria-label` for accessibility
        - _Requirements: 3.1, 3.2, 3.3_

- [x] 6. Verify no third-party tracking
    - [x] 6.1 Audit HTML for tracking scripts and cookies
        - Verify no scripts from google-analytics.com, googletagmanager.com, googlesyndication.com
        - Verify no tracking cookie scripts are present
        - Document that server-side logging via Caddy/application logs is the approved approach
        - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 7. Add privacy statement modal
    - [x] 7.1 Add CSS styles for privacy modal
        - Add styles for `dialog.privacy-modal` (max-width, padding, border-radius, box-shadow)
        - Add `dialog::backdrop` style (semi-transparent dark overlay)
        - Add `.modal-header` flex row with space-between for title and close button
        - Add `.modal-close` button style (borderless, cursor pointer, font-size 1.5rem)
        - _Requirements: 11.2_

    - [x] 7.2 Add privacy modal dialog HTML element
        - Add `<dialog id="privacy-modal" class="privacy-modal">` element in the `<body>` before the `<script>` tag
        - Add modal header with `<h2>Privacy Statement</h2>` and `<button class="modal-close" aria-label="Close privacy statement">×</button>`
        - Add privacy statement content covering: data collected, legal basis, no third-party sharing, retention policy, contact email
        - _Requirements: 11.2, 11.6, 11.7, 11.8, 11.9, 11.10_

    - [x] 7.3 Add Privacy link to footer
        - Add `<button class="privacy-link">Privacy</button>` (or `<a>` styled as link) to the footer-content
        - Position after the contact paragraph
        - Style to match footer link appearance (color #2563eb, no border/background for button variant)
        - _Requirements: 11.1_

    - [x] 7.4 Add JavaScript open/close handlers
        - Add click handler on Privacy link/button: calls `document.getElementById('privacy-modal').showModal()`
        - Add click handler on close button inside modal: calls `dialog.close()`
        - Escape key dismissal is handled natively by `<dialog>` — no extra JS needed
        - _Requirements: 11.3, 11.4, 11.5, 11.11_

- [x] 8. Checkpoint - Verify footer, tracking compliance, and privacy modal
    - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Create DOM structure tests
    - [x] 9.1 Write tests for acknowledgement links
        - Test ImageJ link href is `https://github.com/imagej/ImageJ`
        - Test ImageGrains link href is `https://github.com/dmair1989/imagegrains`
        - Test both links have `target="_blank"` attribute
        - Test both links have `rel="noopener"` attribute
        - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

    - [x] 9.2 Write tests for contact link
        - Test contact link href is `mailto:npowers@umw.edu`
        - Test contact link has `aria-label` attribute
        - Test contact link text contains "Nolan Powers" and "sedimental.io"
        - _Requirements: 3.1, 3.2, 3.3_

    - [x] 9.3 Write tests for coordinate input placeholders
        - Test latitude input placeholder contains decimal format example
        - Test longitude input placeholder contains decimal format example
        - Test placeholders do not contain degree/minutes/seconds format
        - _Requirements: 4.1, 4.2, 4.3_

    - [x] 9.4 Write tests for coordinate validation attributes
        - Test latitude input has `min="-90"` and `max="90"` attributes
        - Test longitude input has `min="-180"` and `max="180"` attributes
        - Test both inputs have `step="any"` for decimal precision
        - _Requirements: 5.3, 5.4, 5.5, 5.6_

    - [x] 9.5 Write tests for legal content
        - Test copyright statement contains "2026" and "Nolan Powers"
        - Test data ownership notice contains required statements about data ownership and deletion
        - Test footer contains all required elements
        - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3_

    - [x] 9.6 Write tests for no third-party tracking
        - Test HTML does not contain scripts from Google domains
        - Test HTML does not contain tracking cookie scripts
        - _Requirements: 9.1, 9.2, 9.4_

    - [x] 9.7 Write tests for privacy modal
        - Test that a `<dialog id="privacy-modal">` element exists in the HTML
        - Test that a Privacy link/button exists in the footer
        - Test that the modal contains required privacy statement sections (data collected, legal basis, no third-party sharing, retention, contact)
        - Test that the modal contains a close button with `aria-label`
        - _Requirements: 11.1, 11.2, 11.4, 11.6, 11.7, 11.8, 11.9, 11.10_

- [x] 10. Final checkpoint - Ensure all tests pass
    - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All changes are frontend-only except the favicon asset file
- The existing FastAPI `StaticFiles` mount at `/static` automatically serves the favicon
- HTML5 native validation handles coordinate range errors; no JavaScript changes needed
- Property-based testing is not applicable for this feature (UI rendering and static content)
- Manual visual testing recommended for: spinner removal, footer positioning, text size hierarchy, link behavior

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "3.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.2"] },
    { "id": 2, "tasks": ["3.3", "5.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "5.4", "5.5"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["7.4"] },
    { "id": 8, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7"] }
  ]
}
```
