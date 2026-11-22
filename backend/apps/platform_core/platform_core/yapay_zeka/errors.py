"""Katmanın ret türü."""


class ToolDenied(Exception):
	"""Araç çağrısının bilinen bir nedenle reddi.

	`code` değeri sözleşmedeki `DenyReason` listesinden gelir ve günlüğe yazılır.
	"""

	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code
