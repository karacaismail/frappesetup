"""Sign-out scope on the Keycloak confirmation screen (G-163, sentence 8).

The confirmation screen asks which sessions to close. It offers three separate choices:
1. this session: the form posts to Keycloak's own logout action;
2. another session: a link to the device activity page of the account console;
3. every device: the same page, where the user presses "sign out all devices".

Keycloak's logout action can close only the current session. Closing another session or every
session is a feature of the account console. Keycloak then sends a back-channel logout for each
closed session. The Frappe tests prove that those notifications close the Frappe sessions.
Keycloak is not needed for this file.
"""

from __future__ import annotations

import re
import unittest

from helpers import DIRECTORY

THEME = DIRECTORY / "themes" / "atonota"
TEMPLATE = THEME / "login" / "logout-confirm.ftl"
MESSAGES = {locale: THEME / "login" / "messages" / f"messages_{locale}.properties" for locale in ("tr", "en")}
ACCOUNT_MESSAGES = THEME / "account" / "messages" / "messages_tr.properties"
DEVICE_ACTIVITY = "/account/account-security/device-activity"
SCOPES = ("kc-logout", "kc-logout-other-session", "kc-logout-all-devices")


def _messages(path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _element(template: str, element_id: str) -> str:
    match = re.search(r"<(input|a)\b[^>]*\bid=\"" + re.escape(element_id) + r"\"[^>]*>", template, re.S)
    if match is None:
        raise AssertionError(f"logout-confirm.ftl has no element with id {element_id}")
    return match.group(0)


class LogoutScopeTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.messages = {locale: _messages(path) for locale, path in MESSAGES.items()}

    def test_screen_offers_three_separate_scopes(self):
        elements = [_element(self.template, element_id) for element_id in SCOPES]
        self.assertEqual(len(set(elements)), 3)
        # Every choice has its own heading and its own explanation. The headings are a list,
        # so a screen reader announces three items.
        self.assertRegex(self.template, r"<ul\b[^>]*\bid=\"kc-logout-scopes\"")
        for key in (
            "logoutScopeQuestion",
            "logoutScopeThisTitle",
            "logoutScopeThisText",
            "logoutScopeOtherTitle",
            "logoutScopeOtherText",
            "logoutScopeAllTitle",
            "logoutScopeAllText",
        ):
            self.assertIn(f'msg("{key}")', self.template, key)

    def test_this_session_posts_to_the_keycloak_logout_action(self):
        button = _element(self.template, "kc-logout")
        self.assertIn('type="submit"', button)
        self.assertIn('msg("logoutThisSession")', button)
        form = re.search(r"<form\b[^>]*>.*?</form>", self.template, re.S)
        self.assertIsNotNone(form)
        self.assertIn("${url.logoutConfirmAction}", form.group(0))
        self.assertIn('id="kc-logout"', form.group(0))
        self.assertNotIn("kc-logout-other-session", form.group(0))
        self.assertNotIn("kc-logout-all-devices", form.group(0))

    def test_other_session_and_every_device_open_the_device_activity_page(self):
        for element_id, label in (
            ("kc-logout-other-session", "logoutOtherSession"),
            ("kc-logout-all-devices", "logoutAllDevices"),
        ):
            with self.subTest(element_id):
                link = _element(self.template, element_id)
                self.assertTrue(link.startswith("<a"), link)
                self.assertEqual(
                    self._href(link),
                    """url.resourcesPath?keep_before("/resources/") + "/realms/" + realm.name?url('UTF-8') + \""""
                    + DEVICE_ACTIVITY
                    + '"',
                )
                self.assertIn(f'msg("{label}")', self.template[self.template.index(link) :])

    def _href(self, link: str) -> str:
        """The FreeMarker expression behind the link. A variable is replaced by its assignment."""
        href = re.search(r'href="\$\{([^}]+)\}"', link)
        self.assertIsNotNone(href, link)
        expression = href.group(1).strip()
        assignment = re.search(r"<#assign\s+" + re.escape(expression) + r"\s*=\s*(.+?)>", self.template)
        return assignment.group(1).strip() if assignment else expression

    def test_no_choice_is_preselected_or_hidden(self):
        # The page has no script that switches the choice. Every choice works without JavaScript.
        self.assertNotRegex(self.template, r"<script\b")
        self.assertNotIn('type="radio"', self.template)
        # The session code travels in a hidden input. No choice may be hidden.
        visible = self.template.replace('type="hidden"', "")
        self.assertNotRegex(visible, r"\bhidden\b|display:\s*none|aria-hidden")

    def test_every_text_exists_in_turkish_and_english(self):
        keys = set(re.findall(r'msg\("([A-Za-z]+)"\)', self.template))
        for locale, values in self.messages.items():
            with self.subTest(locale):
                self.assertEqual(sorted(keys - values.keys()), [])
                self.assertEqual([key for key in keys if not values[key]], [])

    def test_every_device_text_names_the_account_console_button(self):
        # The every-device choice tells the user which button to press on the next page.
        # The button text there comes from the account theme. The two texts must stay equal.
        button = _messages(ACCOUNT_MESSAGES)["signOutAllDevices"]
        self.assertIn(button, self.messages["tr"]["logoutScopeAllText"])

    def test_buttons_use_the_formal_imperative(self):
        tr = self.messages["tr"]
        for key in ("logoutThisSession", "logoutOtherSession", "logoutAllDevices"):
            self.assertRegex(tr[key], r"(ın|in|un|ün)$", key)


if __name__ == "__main__":
    unittest.main()
