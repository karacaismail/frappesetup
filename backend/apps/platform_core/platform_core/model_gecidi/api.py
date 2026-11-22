"""Public Python interface for the model gateway."""

from platform_core.model_gecidi import gateway
from platform_core.model_gecidi.maintenance import purge_usage_logs as purge_usage_logs


def complete(route, messages, tools=None, schema=None, limit=1024):
	"""Complete a request on a configured route under the current user's permissions."""
	return gateway.complete(route, messages, tools=tools, schema=schema, limit=limit)
