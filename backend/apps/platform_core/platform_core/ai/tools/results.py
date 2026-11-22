"""Result schemas of the built-in tools.

A successful tool call returns this shape in `structuredContent`. `tools/list` publishes it as
`outputSchema`. The contract file `contracts/platform_core-yapay-zeka.openapi.yaml` holds the same
schemas under `x-mcp-results`. A test keeps the two equal.

A denied call does not follow these schemas. It returns `isError: true` and an `error` object.
"""

_STRING = {"type": "string"}
_BOOLEAN = {"type": "boolean"}
_NULLABLE_STRING = {"type": ["string", "null"]}

PREVIEW = {
	"type": "object",
	"required": ["action", "summary"],
	"properties": {
		"action": {
			"type": "string",
			"enum": ["create", "update", "submit", "cancel", "delete", "app_tool", "admin"],
		},
		"summary": _STRING,
		"changes": {
			"type": "array",
			"items": {
				"type": "object",
				"required": ["fieldname", "new"],
				"properties": {"fieldname": _STRING, "label": _NULLABLE_STRING, "old": {}, "new": {}},
			},
		},
		"details": {
			"type": "object",
			"description": "Extra facts of the tool for the human, as plain values.",
		},
	},
}

# Every read result says when it was read, on which site and from what.
_PROVENANCE = {
	"as_of": {"type": "string", "description": "Time of the read, ISO 8601 with a UTC offset."},
	"site": _STRING,
	"source": {
		"type": "string",
		"description": "What the data was read from, for example a DocType or a report.",
	},
}
_PROVENANCE_KEYS = ["as_of", "site", "source"]
_TRUNCATED = {
	"type": "boolean",
	"description": "True when rows or values were left out to stay within the limits.",
}

SEARCH_DOCTYPES = {
	"type": "object",
	"required": ["doctypes", *_PROVENANCE_KEYS],
	"properties": {"doctypes": {"type": "array", "items": _STRING}, **_PROVENANCE},
}

DOCTYPE_SCHEMA = {
	"type": "object",
	"required": [
		"doctype",
		"module",
		"is_submittable",
		"is_single",
		"is_child_table",
		"generic_write_tools",
		"permissions",
		"fields",
		"truncated",
		*_PROVENANCE_KEYS,
	],
	"properties": {
		**_PROVENANCE,
		"truncated": _TRUNCATED,
		"doctype": _STRING,
		"description": _NULLABLE_STRING,
		"module": _STRING,
		"is_submittable": _BOOLEAN,
		"is_single": _BOOLEAN,
		"is_child_table": _BOOLEAN,
		"title_field": _NULLABLE_STRING,
		"generic_write_tools": {"type": "string", "enum": ["open", "closed"]},
		"permissions": {
			"type": "object",
			"required": ["read", "write", "create", "delete", "submit", "cancel"],
			"properties": {
				ptype: _BOOLEAN for ptype in ("read", "write", "create", "delete", "submit", "cancel")
			},
		},
		"fields": {
			"type": "array",
			"items": {
				"type": "object",
				"required": [
					"fieldname",
					"fieldtype",
					"reqd",
					"read_only",
					"permlevel",
					"secret",
					"readable",
					"writable",
				],
				"properties": {
					"fieldname": _STRING,
					"fieldtype": _STRING,
					"label": _STRING,
					"description": _STRING,
					"options": _STRING,
					"reqd": _BOOLEAN,
					"read_only": _BOOLEAN,
					"permlevel": {"type": "integer"},
					"secret": _BOOLEAN,
					"readable": _BOOLEAN,
					"writable": _BOOLEAN,
				},
			},
		},
	},
}

LIST_DOCUMENTS = {
	"type": "object",
	"required": ["documents", "has_next_page", "next_start", "truncated", *_PROVENANCE_KEYS],
	"properties": {
		"documents": {"type": "array", "items": {"type": "object"}},
		"has_next_page": _BOOLEAN,
		"next_start": {
			"type": ["integer", "null"],
			"description": "Value of start for the next page. Null on the last page.",
		},
		"truncated": _TRUNCATED,
		**_PROVENANCE,
	},
}

GET_DOCUMENT = {
	"type": "object",
	"required": ["document", "truncated", *_PROVENANCE_KEYS],
	"properties": {
		"document": {
			"type": "object",
			"description": "Field name to value. A child table is a list of row objects, at most 200 rows.",
		},
		"truncated": _TRUNCATED,
		**_PROVENANCE,
	},
}

RUN_REPORT = {
	"type": "object",
	"required": ["columns", "rows", "truncated", *_PROVENANCE_KEYS],
	"properties": {
		"columns": {
			"type": "array",
			"description": "A column is an object with fieldname, label and fieldtype, or the text Label:Type:Width.",
			"items": {"type": ["object", "string"]},
		},
		"rows": {
			"type": "array",
			"description": "A row is an object keyed by fieldname, or a list in column order.",
			"items": {"type": ["object", "array"]},
		},
		"truncated": _TRUNCATED,
		**_PROVENANCE,
	},
}

APPROVAL_REQUIRED = {
	"type": "object",
	"required": ["status", "proposal_id", "preview", "expires_at", "created_at"],
	"properties": {
		"status": {"type": "string", "enum": ["approval_required"]},
		"proposal_id": _STRING,
		"preview": PREVIEW,
		"expires_at": {"type": "string", "description": "ISO 8601 with a UTC offset."},
		"created_at": {"type": "string", "description": "ISO 8601 with a UTC offset."},
	},
}

PROPOSAL_STATE = {
	"type": "object",
	"required": [
		"proposal_id",
		"status",
		"result",
		"tool",
		"destructive",
		"billable",
		"preview",
		"expires_at",
		"created_at",
	],
	"properties": {
		"proposal_id": _STRING,
		"status": {"type": "string", "enum": ["pending", "rejected", "expired", "consumed"]},
		"result": {"type": "string", "enum": ["", "unknown", "succeeded", "failed"]},
		"tool": _STRING,
		"target_doctype": _NULLABLE_STRING,
		"target_name": _NULLABLE_STRING,
		"destructive": _BOOLEAN,
		"billable": _BOOLEAN,
		"preview": PREVIEW,
		"expires_at": {"type": "string", "description": "ISO 8601 with a UTC offset."},
		"created_at": {"type": "string", "description": "ISO 8601 with a UTC offset."},
		"result_document": _NULLABLE_STRING,
		"error": _NULLABLE_STRING,
	},
}

# Result schema of every built-in tool, by tool name. Write tools all return APPROVAL_REQUIRED.
BY_TOOL = {
	"plt_search_doctypes": SEARCH_DOCTYPES,
	"plt_get_doctype_schema": DOCTYPE_SCHEMA,
	"plt_list_documents": LIST_DOCUMENTS,
	"plt_get_document": GET_DOCUMENT,
	"plt_run_report": RUN_REPORT,
	"plt_get_proposal": PROPOSAL_STATE,
}


def schema_for(tool_name: str, kind: str) -> dict | None:
	"""Return the result schema of a built-in tool."""
	return APPROVAL_REQUIRED if kind == "write" else BY_TOOL.get(tool_name)
