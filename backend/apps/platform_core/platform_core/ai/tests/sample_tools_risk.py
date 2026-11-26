"""Sample app tools of the risk level tests (AJA-1001). Not used in production."""

from pydantic import BaseModel, ConfigDict

PATH = "platform_core.ai.tests.sample_tools."
OWN = "platform_core.ai.tests.sample_tools_risk."


class Strict(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")


class RiskArguments(Strict):
	name: str
	risk_level: str = "R0"


def _title_tool(name: str, **extra) -> dict:
	return {
		"name": name,
		"description": "Set the title of a test record.",
		"arguments": PATH + "TitleArguments",
		"kind": "write",
		"handler": PATH + "set_title",
		"preview": PATH + "preview_title",
		**extra,
	}


def declare() -> list[dict]:
	return [
		# Declares a level lower than its class gives. The computed level wins.
		_title_tool("low_declared_delete", destructive=True, risk_level="R0"),
		# Declares a level higher than its class gives. The declared level wins.
		_title_tool("high_declared_note", risk_level="R3"),
		# Declares nothing. The level comes from its class.
		_title_tool("plain_note"),
		# Invalid declarations. The layer must not load them.
		_title_tool("unknown_level", risk_level="R9"),
		{
			"name": "level_in_arguments",
			"description": "Invalid: the model must not send the risk level.",
			"arguments": OWN + "RiskArguments",
			"kind": "read",
			"handler": PATH + "count_records",
		},
	]
