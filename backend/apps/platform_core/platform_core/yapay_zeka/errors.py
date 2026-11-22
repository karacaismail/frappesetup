"""The denial type of the layer."""

# Translation context of every user-visible message of this layer (O-23). A context keeps the
# layer's Turkish text from overriding Frappe's own translation of the same English words.
CONTEXT = "platform_core.yapay_zeka"


class ToolDenied(Exception):
	"""Denial of a tool call for a known reason.

	The `code` value comes from the `DenyReason` list in the contract and is written to the log.
	"""

	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code


# Server log of the layer. A file under the bench's `logs` folder, shared by all sites.
SERVER_LOG = "platform_core.yapay_zeka"


def log_tool_error(tool_name: str, error: Exception) -> None:
	"""Write a refused tool call to the server log: the tool and the error type, never the text.

	The text of a tool's error may carry a field value, which can be personal data. So it is
	neither returned nor stored.
	"""
	import frappe

	frappe.logger(SERVER_LOG, allow_site=False).warning(
		"AI tool %s raised %s", tool_name, type(error).__name__
	)


def traceback_without_text(error: Exception) -> str:
	"""Where an unexpected error happened and its type, for the error log. The error's text is left out."""
	import traceback

	return "".join(traceback.format_tb(error.__traceback__)) + type(error).__name__
