"""Risk level of a proposal (AJA-1001). The server sets it from the tool, never from the model.

The rule table is in `docs/decisions/0002-ai-layer.md`, section 7, the risk level table.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from platform_core.ai.registry import AiTool

LEVELS = ("R0", "R1", "R2", "R3")


def computed(*, kind: str, tool_class: str, destructive: bool, billable: bool) -> str:
	"""The level the tool's class and flags give. It is the floor of the tool's level."""
	if kind != "write":
		# Read, definition and flow tools open no proposal.
		return "R0"
	if (destructive and billable) or (tool_class == "admin" and (destructive or billable)):
		return "R3"
	if destructive or billable or tool_class == "admin":
		return "R2"
	return "R1"


def higher(first: str, second: str) -> str:
	return max(first, second, key=LEVELS.index)


def level(tool: "AiTool") -> str:
	"""The level of a tool. A declared level can raise the computed level, never lower it."""
	floor = computed(
		kind=tool.kind,
		tool_class=tool.tool_class,
		destructive=tool.destructive,
		billable=tool.billable,
	)
	return higher(floor, tool.risk_level) if tool.risk_level else floor
