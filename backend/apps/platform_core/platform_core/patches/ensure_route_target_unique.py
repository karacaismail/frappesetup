"""Install route-target uniqueness on upgraded sites."""

from platform_core.model_gecidi.doctype.plt_ai_route_target import plt_ai_route_target


def execute():
	plt_ai_route_target.on_doctype_update()
