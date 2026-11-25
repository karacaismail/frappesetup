"""Serve the small set of HTTPS endpoints needed by the disposable tenant."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import sys


RELAY_TARGETS = {
    # The tenant calls identity-sync through this origin. The login reads share it (AJA-459).
    "sessions": {
        ("POST", "/v1/sessions/revoke"),
        ("GET", "/v1/login-providers"),
        ("POST", "/v1/linked-accounts"),
    },
    "keycloak": {
        ("POST", "/realms/platform/protocol/openid-connect/token"),
        ("GET", "/realms/platform/protocol/openid-connect/certs"),
    },
}


def relay_handler(host, upstream_port, routes):
    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            if (self.command, self.path) not in routes:
                self.send_error(404)
                return
            body = None
            if self.command == "POST":
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    length = 0
                if not 0 < length <= 4096:
                    self.send_error(400)
                    return
                body = self.rfile.read(length)
            connection = http.client.HTTPConnection(host, upstream_port, timeout=2)
            try:
                connection.request(self.command, self.path, body=body, headers={
                    "Content-Type": self.headers.get("Content-Type", "application/json"),
                    "Authorization": self.headers.get("Authorization", ""),
                })
                result = connection.getresponse()
                status = result.status
                content_type = result.getheader("Content-Type", "application/json")
                payload = result.read(65537)
                if len(payload) > 65536:
                    self.send_error(502)
                    return
            except (OSError, http.client.HTTPException):
                self.send_error(502)
                return
            finally:
                connection.close()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Relay


def main():
    directory = Path(__file__).parent
    target, upstream_port = sys.argv[1:3]
    if target == "sessions":
        host, port = "127.0.0.1", 9443
    elif target == "keycloak":
        host, port = "keycloak", 9444
    else:
        raise SystemExit("Invalid preview TLS target.")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(directory / "certificate.pem", directory / "key.pem")


    class PreviewTLS(ThreadingHTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(4)
            return context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False), address

    with PreviewTLS(("0.0.0.0", port), relay_handler(host, int(upstream_port), RELAY_TARGETS[target])) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
