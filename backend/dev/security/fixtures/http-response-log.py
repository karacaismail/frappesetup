import frappe
import logging

logger = logging.getLogger(__name__)


def record_response(response):
    body = response.text
    # ruleid: http-raw-response-log
    frappe.log_error(title="Request failed", message=body)
    # ok: http-raw-response-log
    frappe.log_error(message=response.status_code)
    # ruleid: http-raw-response-log
    logger.error("response %s", body)
    # ruleid: http-raw-response-log
    logging.warning("response %s", response.json())
    # ruleid: http-raw-response-log
    print(response.read())
    # ok: http-raw-response-log
    logger.warning("status %s", response.status_code)
    # ok: http-raw-response-log
    return response.content
