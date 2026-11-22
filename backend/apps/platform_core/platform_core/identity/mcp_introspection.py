"""HTTPS transport for uncached Keycloak introspection."""

import http.client
import socket
import ssl
from threading import BoundedSemaphore, Event, Lock, Thread
from time import monotonic
from urllib.parse import urlsplit

# Python cannot interrupt getaddrinfo. Bound outstanding lookups as well as connected requests.
_MAX_WORKERS = 8
_WORKERS = BoundedSemaphore(_MAX_WORKERS)
_HEADERS = {
	"Content-Type": "application/x-www-form-urlencoded",
	"Accept": "application/json",
	"Accept-Encoding": "identity",
	"Connection": "close",
}


class _Deadline:
	def __init__(self, timeout: float, body: bytes):
		self._end = monotonic() + timeout
		self._lock = Lock()
		self._socket: socket.socket | None = None
		self._body: bytes | None = body

	def remaining(self) -> float:
		remaining = self._end - monotonic()
		if remaining <= 0:
			raise TimeoutError("Introspection deadline elapsed")
		return remaining

	def attach(self, connection: socket.socket) -> None:
		with self._lock:
			self.remaining()
			self._socket = connection

	def take_body(self) -> bytes:
		with self._lock:
			self.remaining()
			body = self._body
			self._body = None
			if body is None:
				raise TimeoutError("Introspection deadline elapsed")
			return body

	def cancel(self) -> None:
		with self._lock:
			connection = self._socket
			self._body = None
		if connection is not None:
			try:
				connection.shutdown(socket.SHUT_RDWR)
			except OSError:
				pass


class _Connection(http.client.HTTPConnection):
	"""Direct TLS so the caller can cut the socket even while headers are being read."""

	default_port = 443

	def __init__(self, host: str, port: int, deadline: _Deadline):
		super().__init__(host, port)
		self._deadline = deadline

	def connect(self) -> None:
		context = ssl.create_default_context()
		self._deadline.remaining()
		addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
		for family, kind, protocol, _canonical, target in addresses:
			timeout = self._deadline.remaining()
			raw = socket.socket(family, kind, protocol)
			try:
				self._deadline.attach(raw)
				raw.settimeout(timeout)
				raw.connect(target)
				secure = context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
				try:
					self._deadline.attach(secure)
					secure.settimeout(self._deadline.remaining())
					secure.do_handshake()
				except OSError:
					secure.close()
					raise
			except ssl.SSLError:
				raw.close()
				raise
			except OSError:
				raw.close()
				continue
			self.sock = secure
			return
		raise OSError("Introspection connection failed")


def _request(url: str, deadline: _Deadline, max_bytes: int) -> bytes:
	address = urlsplit(url)
	if address.scheme != "https" or not address.hostname:
		raise ValueError("Invalid introspection endpoint")
	connection = _Connection(address.hostname, address.port or 443, deadline)
	try:
		connection.connect()
		connection.request("POST", address.path, body=deadline.take_body(), headers=_HEADERS)
		with connection.getresponse() as response:
			if response.status != 200:
				raise OSError("Introspection HTTP error")
			body = response.read(max_bytes + 1)
			if len(body) > max_bytes or (response.length is not None and response.length > 0):
				raise ValueError("Invalid introspection response size")
			return body
	finally:
		connection.close()


def fetch_introspection(url: str, body: bytes, *, timeout: float, max_bytes: int) -> bytes:
	"""Send the POST once, capped by one deadline across DNS, TLS and the complete response."""
	deadline = _Deadline(timeout, body)
	if not _WORKERS.acquire(blocking=False):
		raise OSError("Introspection workers unavailable")
	result: list[bytes] = []
	finished = Event()

	def download() -> None:
		try:
			result.append(_request(url, deadline, max_bytes))
		except (http.client.HTTPException, OSError, ValueError):
			# The provider's text and request contents never reach the Frappe error response.
			pass
		finally:
			_WORKERS.release()
			finished.set()

	worker = Thread(target=download, name="mcp-introspection", daemon=True)
	try:
		worker.start()
	except RuntimeError:
		_WORKERS.release()
		raise OSError("Introspection worker unavailable") from None
	try:
		if not finished.wait(deadline.remaining()):
			raise TimeoutError("Introspection deadline elapsed")
		deadline.remaining()
		if not result:
			raise OSError("Introspection request failed")
		return result[0]
	finally:
		deadline.cancel()
