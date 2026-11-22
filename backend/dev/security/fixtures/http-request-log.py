import logging
import frappe

logger = logging.getLogger(__name__)


def log_request(request):
    path = request.full_path
    # ruleid: http-raw-request-log
    frappe.log_error(message=path, title="Request failed")
    # ok: http-raw-request-log
    frappe.log_error(message=request.method, title="Request failed")
    # ruleid: http-raw-request-log
    logger.info("request %s", path)
    # ruleid: http-raw-request-log
    print(f"request {frappe.request.path}")
    # ruleid: http-raw-request-log
    logging.warning("request %s", request.url)
    # ok: http-raw-request-log
    logger.info("method %s", request.method)
    # ok: http-raw-request-log
    logger.info("route %s", "/api/method/example.read")
