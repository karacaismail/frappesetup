"""Local-only HTTP transport for the mobile test clients."""

from ipaddress import ip_address
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class RejectRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		return None


_OPENER = build_opener(ProxyHandler({}), RejectRedirect())


def validate_loopback_url(url):
	address = urlsplit(url)
	if address.scheme not in {"http", "https"} or address.username is not None or not address.hostname:
		raise ValueError("An HTTP URL with a numeric loopback address is required")
	try:
		host = ip_address(address.hostname)
	except ValueError:
		raise ValueError("An HTTP URL with a numeric loopback address is required") from None
	if not host.is_loopback:
		raise ValueError("An HTTP URL with a numeric loopback address is required")


def open_loopback(request, *, timeout):
	validate_loopback_url(request.full_url)
	return _OPENER.open(request, timeout=timeout)
