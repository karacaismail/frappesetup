"""A burst must fit while the serial HTTP handler is busy."""
from contextlib import ExitStack
from http.client import HTTPResponse
import socket
import threading
import unittest

from identity_sync.server import make_server
from .fakes import Stack
from .test_server import fake_verifier


class ConnectionQueueTest(unittest.TestCase):
    def test_twenty_connections_wait_without_transport_errors(self):
        stack = Stack()
        self.addCleanup(stack.close)
        server = make_server(stack.app, fake_verifier, host="127.0.0.1", port=0)
        self.addCleanup(server.server_close)
        # Pause acceptance to model a handler processing an earlier request.
        # All twenty clients must connect before any queued request is served.
        with ExitStack() as clients:
            connections = []
            for _ in range(20):
                connection = clients.enter_context(socket.create_connection(server.server_address, timeout=1))
                connection.sendall(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                connections.append(connection)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            thread.start()
            try:
                for connection in connections:
                    connection.settimeout(5)
                    with HTTPResponse(connection) as response:
                        response.begin()
                        self.assertEqual(response.status, 200)
                        response.read()
            finally:
                server.shutdown()
                thread.join(5)
            self.assertFalse(thread.is_alive())
