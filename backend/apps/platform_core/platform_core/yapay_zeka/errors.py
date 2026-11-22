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
