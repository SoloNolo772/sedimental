"""
DOM structure tests for sedimental/static/index.html.

Parses the static HTML file with BeautifulSoup and asserts structural
properties — link hrefs, attributes, input placeholders, legal content,
tracking compliance, and privacy modal presence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Module-level fixture — parse the HTML once for the whole module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def soup() -> BeautifulSoup:
    html = (
        Path(__file__).parent.parent / "sedimental" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# 9.1  Acknowledgement links
# ---------------------------------------------------------------------------


class TestAcknowledgementLinks:
    """Tests for the ImageJ and ImageGrains acknowledgement links.

    **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**
    """

    def _imagej_link(self, soup: BeautifulSoup):
        """Return the <a> element whose text is 'ImageJ'."""
        link = soup.find("a", string="ImageJ")
        assert link is not None, "ImageJ link not found in HTML"
        return link

    def _imagegrains_link(self, soup: BeautifulSoup):
        """Return the <a> element whose text is 'ImageGrains'."""
        link = soup.find("a", string="ImageGrains")
        assert link is not None, "ImageGrains link not found in HTML"
        return link

    # --- href tests --------------------------------------------------------

    def test_imagej_link_href(self, soup: BeautifulSoup) -> None:
        """ImageJ link href must point to the ImageJ GitHub repository.

        **Validates: Requirement 1.1**
        """
        link = self._imagej_link(soup)
        assert link["href"] == "https://github.com/imagej/ImageJ"

    def test_imagegrains_link_href(self, soup: BeautifulSoup) -> None:
        """ImageGrains link href must point to the ImageGrains GitHub repository.

        **Validates: Requirement 2.1**
        """
        link = self._imagegrains_link(soup)
        assert link["href"] == "https://github.com/dmair1989/imagegrains"

    # --- target="_blank" tests ---------------------------------------------

    def test_imagej_link_opens_in_new_tab(self, soup: BeautifulSoup) -> None:
        """ImageJ link must have target="_blank" to open in a new tab.

        **Validates: Requirement 1.2**
        """
        link = self._imagej_link(soup)
        assert link.get("target") == "_blank"

    def test_imagegrains_link_opens_in_new_tab(self, soup: BeautifulSoup) -> None:
        """ImageGrains link must have target="_blank" to open in a new tab.

        **Validates: Requirement 2.2**
        """
        link = self._imagegrains_link(soup)
        assert link.get("target") == "_blank"

    # --- rel="noopener" tests ----------------------------------------------

    def test_imagej_link_has_noopener(self, soup: BeautifulSoup) -> None:
        """ImageJ link must include rel="noopener" for security.

        **Validates: Requirement 1.3**
        """
        link = self._imagej_link(soup)
        rel_values = link.get("rel", [])
        assert "noopener" in rel_values

    def test_imagegrains_link_has_noopener(self, soup: BeautifulSoup) -> None:
        """ImageGrains link must include rel="noopener" for security.

        **Validates: Requirement 2.3**
        """
        link = self._imagegrains_link(soup)
        rel_values = link.get("rel", [])
        assert "noopener" in rel_values


# ---------------------------------------------------------------------------
# 9.2  Contact link
# ---------------------------------------------------------------------------


class TestContactLink:
    """Tests for the contact link in the footer.

    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    def _contact_link(self, soup: BeautifulSoup):
        """Return the <a> element inside <p class="contact">."""
        contact_p = soup.find("p", class_="contact")
        assert contact_p is not None, "<p class='contact'> not found in HTML"
        link = contact_p.find("a")
        assert link is not None, "No <a> element found inside <p class='contact'>"
        return link

    def test_contact_link_href(self, soup: BeautifulSoup) -> None:
        """Contact link href must be mailto:npowers@umw.edu.

        **Validates: Requirement 3.1**
        """
        link = self._contact_link(soup)
        assert link["href"] == "mailto:npowers@umw.edu"

    def test_contact_link_has_aria_label(self, soup: BeautifulSoup) -> None:
        """Contact link must have an aria-label attribute.

        **Validates: Requirement 3.2**
        """
        link = self._contact_link(soup)
        assert link.get("aria-label"), "Contact link is missing an aria-label attribute"

    def test_contact_link_text_contains_nolan_powers(self, soup: BeautifulSoup) -> None:
        """Contact link text must contain 'Nolan Powers'.

        **Validates: Requirement 3.3**
        """
        link = self._contact_link(soup)
        assert "Nolan Powers" in link.get_text()

    def test_contact_link_text_contains_sedimental_io(self, soup: BeautifulSoup) -> None:
        """Contact link text must contain 'sedimental.io'.

        **Validates: Requirement 3.3**
        """
        link = self._contact_link(soup)
        assert "sedimental.io" in link.get_text()


# ---------------------------------------------------------------------------
# 9.3  Coordinate input placeholders
# ---------------------------------------------------------------------------


class TestCoordinatePlaceholders:
    """Tests for decimal-format placeholders on coordinate input fields.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    def _lat_input(self, soup: BeautifulSoup):
        """Return the latitude <input> element."""
        el = soup.find("input", {"id": "location_lat"})
        assert el is not None, "Latitude input (id='location_lat') not found in HTML"
        return el

    def _lon_input(self, soup: BeautifulSoup):
        """Return the longitude <input> element."""
        el = soup.find("input", {"id": "location_lon"})
        assert el is not None, "Longitude input (id='location_lon') not found in HTML"
        return el

    # --- decimal format presence -------------------------------------------

    def test_latitude_placeholder_contains_decimal_example(self, soup: BeautifulSoup) -> None:
        """Latitude placeholder must show a decimal-format example.

        **Validates: Requirement 4.1**
        """
        placeholder = self._lat_input(soup).get("placeholder", "")
        assert placeholder == "Latitude (e.g., 40.7128)", (
            f"Expected 'Latitude (e.g., 40.7128)', got {placeholder!r}"
        )

    def test_longitude_placeholder_contains_decimal_example(self, soup: BeautifulSoup) -> None:
        """Longitude placeholder must show a decimal-format example.

        **Validates: Requirement 4.2**
        """
        placeholder = self._lon_input(soup).get("placeholder", "")
        assert placeholder == "Longitude (e.g., -74.0060)", (
            f"Expected 'Longitude (e.g., -74.0060)', got {placeholder!r}"
        )

    # --- DMS / cardinal direction absence ----------------------------------

    DMS_INDICATORS = ["°", "′", "″", "N", "S", "E", "W"]

    def test_latitude_placeholder_has_no_dms_format(self, soup: BeautifulSoup) -> None:
        """Latitude placeholder must not contain degree/minutes/seconds or cardinal direction symbols.

        **Validates: Requirement 4.3**
        """
        placeholder = self._lat_input(soup).get("placeholder", "")
        for indicator in self.DMS_INDICATORS:
            assert indicator not in placeholder, (
                f"Latitude placeholder contains DMS indicator {indicator!r}: {placeholder!r}"
            )

    def test_longitude_placeholder_has_no_dms_format(self, soup: BeautifulSoup) -> None:
        """Longitude placeholder must not contain degree/minutes/seconds or cardinal direction symbols.

        **Validates: Requirement 4.3**
        """
        placeholder = self._lon_input(soup).get("placeholder", "")
        for indicator in self.DMS_INDICATORS:
            assert indicator not in placeholder, (
                f"Longitude placeholder contains DMS indicator {indicator!r}: {placeholder!r}"
            )


# ---------------------------------------------------------------------------
# 9.4  Coordinate validation attributes
# ---------------------------------------------------------------------------


class TestCoordinateValidationAttributes:
    """Tests for min/max/step validation attributes on coordinate input fields.

    **Validates: Requirements 5.3, 5.4, 5.5, 5.6**
    """

    def _lat_input(self, soup: BeautifulSoup):
        """Return the latitude <input> element."""
        el = soup.find("input", {"id": "location_lat"})
        assert el is not None, "Latitude input (id='location_lat') not found in HTML"
        return el

    def _lon_input(self, soup: BeautifulSoup):
        """Return the longitude <input> element."""
        el = soup.find("input", {"id": "location_lon"})
        assert el is not None, "Longitude input (id='location_lon') not found in HTML"
        return el

    # --- latitude min/max --------------------------------------------------

    def test_latitude_min_attribute(self, soup: BeautifulSoup) -> None:
        """Latitude input must have min="-90".

        **Validates: Requirement 5.3**
        """
        el = self._lat_input(soup)
        assert el.get("min") == "-90", (
            f"Expected min='-90' on latitude input, got {el.get('min')!r}"
        )

    def test_latitude_max_attribute(self, soup: BeautifulSoup) -> None:
        """Latitude input must have max="90".

        **Validates: Requirement 5.4**
        """
        el = self._lat_input(soup)
        assert el.get("max") == "90", (
            f"Expected max='90' on latitude input, got {el.get('max')!r}"
        )

    # --- longitude min/max -------------------------------------------------

    def test_longitude_min_attribute(self, soup: BeautifulSoup) -> None:
        """Longitude input must have min="-180".

        **Validates: Requirement 5.5**
        """
        el = self._lon_input(soup)
        assert el.get("min") == "-180", (
            f"Expected min='-180' on longitude input, got {el.get('min')!r}"
        )

    def test_longitude_max_attribute(self, soup: BeautifulSoup) -> None:
        """Longitude input must have max="180".

        **Validates: Requirement 5.6**
        """
        el = self._lon_input(soup)
        assert el.get("max") == "180", (
            f"Expected max='180' on longitude input, got {el.get('max')!r}"
        )

    # --- step="any" for decimal precision ----------------------------------

    def test_latitude_step_any(self, soup: BeautifulSoup) -> None:
        """Latitude input must have step="any" to allow decimal values.

        **Validates: Requirement 5.3**
        """
        el = self._lat_input(soup)
        assert el.get("step") == "any", (
            f"Expected step='any' on latitude input, got {el.get('step')!r}"
        )

    def test_longitude_step_any(self, soup: BeautifulSoup) -> None:
        """Longitude input must have step="any" to allow decimal values.

        **Validates: Requirement 5.5**
        """
        el = self._lon_input(soup)
        assert el.get("step") == "any", (
            f"Expected step='any' on longitude input, got {el.get('step')!r}"
        )


# ---------------------------------------------------------------------------
# 9.5  Legal content
# ---------------------------------------------------------------------------


class TestLegalContent:
    """Tests for copyright statement, data ownership notice, and footer structure.

    **Validates: Requirements 7.1, 7.2, 7.3, 8.1, 8.2, 8.3**
    """

    def _copyright_p(self, soup: BeautifulSoup):
        """Return the <p class="copyright"> element."""
        el = soup.find("p", class_="copyright")
        assert el is not None, "<p class='copyright'> not found in HTML"
        return el

    def _data_notice_p(self, soup: BeautifulSoup):
        """Return the <p class="data-notice"> element."""
        el = soup.find("p", class_="data-notice")
        assert el is not None, "<p class='data-notice'> not found in HTML"
        return el

    def _footer(self, soup: BeautifulSoup):
        """Return the <footer class="site-footer"> element."""
        el = soup.find("footer", class_="site-footer")
        assert el is not None, "<footer class='site-footer'> not found in HTML"
        return el

    # --- copyright statement -----------------------------------------------

    def test_copyright_contains_year_2026(self, soup: BeautifulSoup) -> None:
        """Copyright statement must include the year 2026.

        **Validates: Requirement 7.2**
        """
        text = self._copyright_p(soup).get_text()
        assert "2026" in text, f"Copyright statement does not contain '2026': {text!r}"

    def test_copyright_contains_nolan_powers(self, soup: BeautifulSoup) -> None:
        """Copyright statement must assign ownership to Nolan Powers.

        **Validates: Requirements 7.1, 7.3**
        """
        text = self._copyright_p(soup).get_text()
        assert "Nolan Powers" in text, (
            f"Copyright statement does not contain 'Nolan Powers': {text!r}"
        )

    def test_copyright_contains_all_rights_reserved(self, soup: BeautifulSoup) -> None:
        """Copyright statement must indicate ownership of content and functionality.

        **Validates: Requirement 7.3**
        """
        text = self._copyright_p(soup).get_text()
        assert "All rights reserved" in text, (
            f"Copyright statement does not contain 'All rights reserved': {text!r}"
        )

    # --- data ownership notice ---------------------------------------------

    def test_data_notice_states_data_belongs_to_user(self, soup: BeautifulSoup) -> None:
        """Data ownership notice must state that data belongs to the user.

        **Validates: Requirement 8.1**
        """
        text = self._data_notice_p(soup).get_text()
        assert "belong" in text.lower(), (
            f"Data notice does not state data belongs to user: {text!r}"
        )

    def test_data_notice_states_data_may_be_deleted(self, soup: BeautifulSoup) -> None:
        """Data ownership notice must state that data may be deleted without notice.

        **Validates: Requirement 8.2**
        """
        text = self._data_notice_p(soup).get_text()
        assert "deleted" in text.lower(), (
            f"Data notice does not mention deletion: {text!r}"
        )

    def test_data_notice_advises_immediate_download(self, soup: BeautifulSoup) -> None:
        """Data ownership notice must advise users to download results immediately.

        **Validates: Requirement 8.3**
        """
        text = self._data_notice_p(soup).get_text()
        assert "download" in text.lower(), (
            f"Data notice does not advise downloading results: {text!r}"
        )

    # --- footer structure --------------------------------------------------

    def test_footer_element_exists(self, soup: BeautifulSoup) -> None:
        """Footer must be a <footer class="site-footer"> element.

        **Validates: Requirement 10.2**
        """
        self._footer(soup)  # assertion inside helper

    def test_footer_contains_footer_content_div(self, soup: BeautifulSoup) -> None:
        """Footer must contain a <div class="footer-content"> wrapper.

        **Validates: Requirement 10.3**
        """
        footer = self._footer(soup)
        content_div = footer.find("div", class_="footer-content")
        assert content_div is not None, (
            "<div class='footer-content'> not found inside <footer class='site-footer'>"
        )

    def test_footer_contains_data_notice(self, soup: BeautifulSoup) -> None:
        """Footer must contain the data ownership notice.

        **Validates: Requirement 8.4**
        """
        footer = self._footer(soup)
        assert footer.find("p", class_="data-notice") is not None, (
            "<p class='data-notice'> not found inside footer"
        )

    def test_footer_contains_acknowledgements(self, soup: BeautifulSoup) -> None:
        """Footer must contain the acknowledgements section.

        **Validates: Requirement 10.3**
        """
        footer = self._footer(soup)
        assert footer.find("p", class_="acknowledgements") is not None, (
            "<p class='acknowledgements'> not found inside footer"
        )

    def test_footer_contains_copyright(self, soup: BeautifulSoup) -> None:
        """Footer must contain the copyright statement.

        **Validates: Requirements 7.1, 10.3**
        """
        footer = self._footer(soup)
        assert footer.find("p", class_="copyright") is not None, (
            "<p class='copyright'> not found inside footer"
        )

    def test_footer_contains_contact(self, soup: BeautifulSoup) -> None:
        """Footer must contain the contact link paragraph.

        **Validates: Requirement 10.3**
        """
        footer = self._footer(soup)
        assert footer.find("p", class_="contact") is not None, (
            "<p class='contact'> not found inside footer"
        )

    def test_footer_contains_privacy_link(self, soup: BeautifulSoup) -> None:
        """Footer must contain a privacy link or button.

        **Validates: Requirement 11.1**
        """
        footer = self._footer(soup)
        privacy = footer.find(id="privacy-link") or footer.find(class_="privacy-link")
        assert privacy is not None, (
            "No privacy link/button found inside footer"
        )


# ---------------------------------------------------------------------------
# 9.6  No third-party tracking
# ---------------------------------------------------------------------------


class TestNoThirdPartyTracking:
    """Tests that the HTML contains no third-party tracking scripts or cookies.

    **Validates: Requirements 9.1, 9.2, 9.4**
    """

    GOOGLE_TRACKING_DOMAINS = [
        "google-analytics.com",
        "googletagmanager.com",
        "googlesyndication.com",
    ]

    COOKIE_TRACKING_PATTERNS = [
        "document.cookie",
        "_ga",
        "_gid",
        "_fbp",
        "gtag(",
        "ga(",
    ]

    def test_no_external_scripts_from_google_domains(self, soup: BeautifulSoup) -> None:
        """HTML must not contain <script src="..."> pointing to Google tracking domains.

        **Validates: Requirements 9.1, 9.2**
        """
        scripts = soup.find_all("script", src=True)
        for script in scripts:
            src = script.get("src", "")
            for domain in self.GOOGLE_TRACKING_DOMAINS:
                assert domain not in src, (
                    f"Found external script from tracking domain {domain!r}: src={src!r}"
                )

    def test_no_inline_script_references_google_domains(self, soup: BeautifulSoup) -> None:
        """Inline <script> blocks must not reference Google tracking domains.

        **Validates: Requirements 9.1, 9.2**
        """
        inline_scripts = soup.find_all("script", src=False)
        for script in inline_scripts:
            content = script.get_text()
            for domain in self.GOOGLE_TRACKING_DOMAINS:
                assert domain not in content, (
                    f"Inline script references tracking domain {domain!r}"
                )

    def test_no_tracking_cookie_patterns_in_scripts(self, soup: BeautifulSoup) -> None:
        """Inline <script> blocks must not contain common tracking cookie patterns.

        **Validates: Requirement 9.4**
        """
        inline_scripts = soup.find_all("script", src=False)
        full_script_content = "\n".join(s.get_text() for s in inline_scripts)
        for pattern in self.COOKIE_TRACKING_PATTERNS:
            assert pattern not in full_script_content, (
                f"Inline script contains tracking cookie pattern {pattern!r}"
            )

    def test_no_tracking_pixel_iframes(self, soup: BeautifulSoup) -> None:
        """HTML must not contain <iframe> elements from Google tracking domains.

        **Validates: Requirement 9.1**
        """
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            src = iframe.get("src", "")
            for domain in self.GOOGLE_TRACKING_DOMAINS:
                assert domain not in src, (
                    f"Found iframe from tracking domain {domain!r}: src={src!r}"
                )


# ---------------------------------------------------------------------------
# 9.7  Privacy modal
# ---------------------------------------------------------------------------


class TestPrivacyModal:
    """Tests for the privacy modal dialog element and its content.

    **Validates: Requirements 11.1, 11.2, 11.4, 11.6, 11.7, 11.8, 11.9, 11.10**
    """

    def _modal(self, soup: BeautifulSoup):
        """Return the <dialog id="privacy-modal"> element."""
        el = soup.find("dialog", {"id": "privacy-modal"})
        assert el is not None, '<dialog id="privacy-modal"> not found in HTML'
        return el

    def _footer(self, soup: BeautifulSoup):
        """Return the <footer class="site-footer"> element."""
        el = soup.find("footer", class_="site-footer")
        assert el is not None, "<footer class='site-footer'> not found in HTML"
        return el

    # --- dialog element presence -------------------------------------------

    def test_privacy_modal_dialog_element_exists(self, soup: BeautifulSoup) -> None:
        """A <dialog id="privacy-modal"> element must exist in the HTML.

        **Validates: Requirement 11.2**
        """
        self._modal(soup)  # assertion inside helper

    def test_privacy_modal_has_correct_class(self, soup: BeautifulSoup) -> None:
        """The privacy modal dialog must have class="privacy-modal".

        **Validates: Requirement 11.2**
        """
        modal = self._modal(soup)
        assert "privacy-modal" in modal.get("class", []), (
            'Expected class="privacy-modal" on <dialog id="privacy-modal">'
        )

    # --- footer privacy link -----------------------------------------------

    def test_privacy_link_exists_in_footer(self, soup: BeautifulSoup) -> None:
        """A Privacy link or button must exist in the footer.

        **Validates: Requirement 11.1**
        """
        footer = self._footer(soup)
        privacy = footer.find(id="privacy-link") or footer.find(class_="privacy-link")
        assert privacy is not None, (
            "No element with id='privacy-link' or class='privacy-link' found in footer"
        )

    def test_privacy_link_has_correct_id(self, soup: BeautifulSoup) -> None:
        """The Privacy button must have id="privacy-link".

        **Validates: Requirement 11.1**
        """
        footer = self._footer(soup)
        el = footer.find(id="privacy-link")
        assert el is not None, 'No element with id="privacy-link" found in footer'

    def test_privacy_link_text_is_privacy(self, soup: BeautifulSoup) -> None:
        """The Privacy button text must be 'Privacy'.

        **Validates: Requirement 11.1**
        """
        footer = self._footer(soup)
        el = footer.find(id="privacy-link") or footer.find(class_="privacy-link")
        assert el is not None, "Privacy link/button not found in footer"
        assert "Privacy" in el.get_text(), (
            f"Privacy link/button text does not contain 'Privacy': {el.get_text()!r}"
        )

    # --- modal close button ------------------------------------------------

    def test_modal_close_button_exists(self, soup: BeautifulSoup) -> None:
        """The privacy modal must contain a close button.

        **Validates: Requirement 11.4**
        """
        modal = self._modal(soup)
        close_btn = modal.find("button", class_="modal-close")
        assert close_btn is not None, (
            'No <button class="modal-close"> found inside privacy modal'
        )

    def test_modal_close_button_has_aria_label(self, soup: BeautifulSoup) -> None:
        """The modal close button must have an aria-label attribute.

        **Validates: Requirement 11.4**
        """
        modal = self._modal(soup)
        close_btn = modal.find("button", class_="modal-close")
        assert close_btn is not None, (
            'No <button class="modal-close"> found inside privacy modal'
        )
        aria_label = close_btn.get("aria-label", "")
        assert aria_label, (
            'Close button inside privacy modal is missing an aria-label attribute'
        )

    # --- modal content sections --------------------------------------------

    def _modal_text(self, soup: BeautifulSoup) -> str:
        """Return the full text content of the privacy modal, lowercased."""
        return self._modal(soup).get_text(separator=" ").lower()

    def test_modal_contains_data_collected_section(self, soup: BeautifulSoup) -> None:
        """Privacy modal must describe what data is collected (images/data collected).

        **Validates: Requirement 11.6**
        """
        text = self._modal_text(soup)
        assert "data collected" in text or "images" in text, (
            "Privacy modal does not mention data collected or images"
        )

    def test_modal_contains_legal_basis_section(self, soup: BeautifulSoup) -> None:
        """Privacy modal must state the legal basis for processing.

        **Validates: Requirement 11.7**
        """
        text = self._modal_text(soup)
        assert "legal basis" in text or "requested" in text, (
            "Privacy modal does not mention legal basis or the service being requested"
        )

    def test_modal_contains_no_third_party_sharing_section(self, soup: BeautifulSoup) -> None:
        """Privacy modal must state that data is not shared with third parties.

        **Validates: Requirement 11.8**
        """
        text = self._modal_text(soup)
        assert "third part" in text, (
            "Privacy modal does not mention third parties"
        )

    def test_modal_contains_retention_section(self, soup: BeautifulSoup) -> None:
        """Privacy modal must describe the data retention policy.

        **Validates: Requirement 11.9**
        """
        text = self._modal_text(soup)
        assert "retention" in text or "deleted" in text, (
            "Privacy modal does not mention retention or deletion of data"
        )

    def test_modal_contains_contact_email(self, soup: BeautifulSoup) -> None:
        """Privacy modal must include the contact email npowers@umw.edu.

        **Validates: Requirement 11.10**
        """
        text = self._modal_text(soup)
        assert "npowers@umw.edu" in text, (
            "Privacy modal does not contain contact email 'npowers@umw.edu'"
        )
