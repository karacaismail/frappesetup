"""Press/Frappe HTTP istemcisi (urllib). Yalnız yapılandırılmış hosta, yönlendirme izlemeden konuşur.

- team principal: Press Dashboard API (`/api/method/press.api...`) + `X-Press-Team` başlığı.
- operator principal: Frappe Desk API (`frappe.client.get`, `frappe.client.get_list`, `run_doc_method`).
Kimlik bilgisi yalnız `Authorization` başlığına girer; hata iletileri maskelenir ve kısaltılır.
"""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request

from . import __version__
from .errors import PressError, PressTimeout
from .redaction import truncate

MAX_RESPONSE = 8 * 1024 * 1024
_STATUS_KIND = {401: "authentication", 403: "permission", 404: "not_found", 409: "conflict", 417: "validation",
                429: "rate_limited"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib arayüzü
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused: " + str(code), headers, fp)


def _server_message(payload: dict) -> str:
    """Frappe hata gövdesinden kullanıcıya dönük iletiyi çıkarır; traceback (`exc`) alınmaz."""
    raw = payload.get("_server_messages")
    messages = []
    if isinstance(raw, str):
        try:
            for item in json.loads(raw):
                try:
                    decoded = json.loads(item) if isinstance(item, str) else item
                    messages.append(str(decoded.get("message", decoded)) if isinstance(decoded, dict) else str(decoded))
                except ValueError:
                    messages.append(str(item))
        except ValueError:
            messages.append(raw)
    if not messages and payload.get("exception"):
        messages.append(str(payload["exception"]))
    if not messages and payload.get("message") and isinstance(payload["message"], str):
        messages.append(payload["message"])
    return " | ".join(messages) or "Press returned an error without a message"


class PressClient:
    def __init__(self, press_config, credentials, redactor):
        self.config = press_config
        self.credentials = credentials
        self.redactor = redactor
        redactor.add_secrets(credentials.secret_values())
        handlers = [_NoRedirect()]
        if press_config.base_url.startswith("https://"):
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        self._opener = urllib.request.build_opener(*handlers)
        self.calls = []  # Son çağrılan yöntem adları (argüman/secret içermez); testler ve denetim için.

    @property
    def principal(self) -> str:
        return self.config.principal

    def _headers(self) -> dict:
        headers = {"Authorization": self.credentials.authorization(), "Accept": "application/json",
                   "Content-Type": "application/json", "User-Agent": "press-ai/" + __version__}
        if self.config.team:
            headers["X-Press-Team"] = self.config.team
        return headers

    def _request(self, path: str, body: dict | None, http_method: str):
        url = self.config.base_url + path
        data = json.dumps(body or {}).encode("utf-8") if http_method == "POST" else None
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=http_method)
        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
                status = response.status
        except urllib.error.HTTPError as error:
            raw = error.read(MAX_RESPONSE + 1) if error.fp else b""
            status = error.code
        except (socket.timeout, TimeoutError):
            raise PressTimeout("Press did not answer within {}s; the remote result is unknown".format(
                int(self.config.timeout)), details={"path": path.split("?")[0]}) from None
        except urllib.error.URLError as error:
            reason = error.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise PressTimeout("Press did not answer in time; the remote result is unknown",
                                   details={"path": path.split("?")[0]}) from None
            raise PressError("Cannot reach Press: " + self.redactor.text(str(reason)), kind="network") from None
        if len(raw) > MAX_RESPONSE:
            raise PressError("Press response exceeds the size limit", kind="protocol", http_status=status)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            payload = None
        if not 200 <= status < 300 or (isinstance(payload, dict) and payload.get("exc_type")):
            if 300 <= status < 400:
                raise PressError("Press answered with a redirect ({}); redirects are not followed".format(status),
                                 kind="protocol", http_status=status)
            kind = _STATUS_KIND.get(status, "server" if status >= 500 else "validation")
            message = _server_message(payload) if isinstance(payload, dict) else "HTTP {}".format(status)
            text, _ = truncate(self.redactor.text(message), 1500)
            details = {}
            if isinstance(payload, dict) and payload.get("exc_type"):
                details["exc_type"] = str(payload["exc_type"])[:80]
            raise PressError(text, kind=kind, http_status=status, details=details)
        if not isinstance(payload, dict):
            raise PressError("Press returned a non-JSON response", kind="protocol", http_status=status)
        return payload.get("message")

    # -- uç noktalar -----------------------------------------------------------------------------
    def _note(self, label: str) -> None:
        self.calls.append(label)
        del self.calls[:-200]

    def call(self, method: str, args: dict | None = None, http_method: str = "POST"):
        """`/api/method/<method>`; GET isteklerinde argümanlar sorgu dizgisine konur."""
        self._note(method)
        if http_method == "GET":
            from urllib.parse import urlencode
            query = urlencode({k: json.dumps(v) if isinstance(v, (dict, list)) else v
                               for k, v in (args or {}).items()})
            return self._request("/api/method/" + method + ("?" + query if query else ""), None, "GET")
        return self._request("/api/method/" + method, args or {}, "POST")

    def run_doc_method(self, doctype: str, name: str, method: str, args: dict | None = None):
        """Frappe Desk `run_doc_method` (yalnız @frappe.whitelist doc metotları; doc izniyle)."""
        self._note("run_doc_method:{}.{}".format(doctype, method))
        body = {"dt": doctype, "dn": name, "method": method}
        if args:
            body["args"] = json.dumps(args)
        return self._request("/api/method/run_doc_method", body, "POST")

    def dashboard_get(self, doctype: str, name: str) -> dict:
        """Team: `press.api.client.get` yalnız DocType'ın `dashboard_fields` alanlarını döndürür."""
        return self.call("press.api.client.get", {"doctype": doctype, "name": name})

    def get_list(self, doctype: str, filters: dict, fields: list, limit: int = 20, order_by: str = "creation desc",
                 parent: str | None = None):
        """Operator: Desk liste okuması, yalnız açık alan listesiyle.

        Tam belge okuması (`frappe.client.get`) bilinçli olarak kullanılmaz: Deploy Candidate `user_private_key`
        ve `build_token`, Agent Job `request_data`, Press Settings bazı token alanlarını düz metin döndürür.
        Alt tablolar `parent` ile okunur."""
        args = {"doctype": doctype, "filters": filters, "fields": fields, "limit_page_length": limit,
                "order_by": order_by}
        if parent:
            args["parent"] = parent
        return self.call("frappe.client.get_list", args)

    def get_one(self, doctype: str, name: str, fields: list, parent: str | None = None) -> dict:
        rows = self.get_list(doctype, {"name": name}, fields, 1, "creation desc", parent)
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise PressError("{} {} not found or not permitted".format(doctype, name), kind="not_found")
        return rows[0]

    def children(self, parent_doctype: str, child_doctype: str, parent_name: str, fields: list, limit: int = 200):
        return self.get_list(child_doctype, {"parent": parent_name, "parenttype": parent_doctype}, fields, limit,
                             "idx asc", parent=parent_doctype)
