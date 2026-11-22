"""Check the authorization code boundary before the Keycloak exchange."""

from inspect import unwrap
from unittest import TestCase
from unittest.mock import patch

from werkzeug.exceptions import Forbidden

from press_tr.api import auth


class AuthorizationCodeTest(TestCase):
	def test_code_over_limit_is_rejected_before_exchange(self):
		with (
			patch.object(auth, "consume_login", return_value={"verifier": "verifier"}),
			patch.object(auth, "reject", side_effect=Forbidden),
			patch.object(auth, "exchange_code", side_effect=RuntimeError("Exchange was reached")) as exchange,
		):
			with self.assertRaises(Forbidden):
				unwrap(auth.keycloak_callback)(state="state", code="a" * 2049)
			exchange.assert_not_called()

	def test_code_at_limit_reaches_exchange(self):
		class ReachedExchange(Exception):
			pass

		with (
			patch.object(auth, "consume_login", return_value={"verifier": "verifier"}),
			patch.object(auth, "exchange_code", side_effect=ReachedExchange) as exchange,
		):
			code = "a" * 2048
			with self.assertRaises(ReachedExchange):
				unwrap(auth.keycloak_callback)(state="state", code=code)
			exchange.assert_called_once_with(code, "verifier")
