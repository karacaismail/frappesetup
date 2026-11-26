"""G-138 help content rules. Pure functions without Frappe, so every step is unit tested.

Fallback order: tenant topic, application topic, the Frappe field `description`,
then the generic "no help" answer with a request-help action. A field the user
cannot read gets no help from any step.
"""

from collections.abc import Iterable, Mapping

TENANT = "Tenant"
APP = "App"
PUBLISHED = "Published"
FIELD = "Field"
COMPONENT = "Component"
ROUTE = "Route"
LAYERS = ((TENANT, "tenant"), (APP, "app"))
NO_HELP_MESSAGE = "No help is available for this field."
REQUEST_HELP = "request_help"


def _text(value) -> str:
	return value.strip() if isinstance(value, str) else ""


def _base_language(language: str) -> str:
	return language.split("-", 1)[0]


def _matches_field(topic: Mapping, doctype: str, fieldname: str) -> bool:
	return (
		topic.get("status") == PUBLISHED
		and topic.get("target_type") == FIELD
		and topic.get("document_type") == doctype
		and topic.get("fieldname") == fieldname
	)


def _rank(topic: Mapping, language: str, version: str | None, roles: set[str]) -> tuple | None:
	"""Return the sort key of a topic that applies, or None when it does not apply."""
	topic_language = _text(topic.get("language"))
	if not topic_language:
		language_rank = 0
	elif topic_language == language:
		language_rank = 2
	elif topic_language == _base_language(language):
		language_rank = 1
	else:
		return None
	topic_version = _text(topic.get("version"))
	if topic_version and topic_version != (version or ""):
		return None
	target_roles = set(topic.get("roles") or ())
	if target_roles and not target_roles & roles:
		return None
	return (language_rank, 1 if topic_version else 0, str(topic.get("modified") or ""))


def _answer(source: str, *, topic: Mapping | None = None, content=None, message=None, actions=()) -> dict:
	return {
		"source": source,
		"topic": topic.get("name") if topic else None,
		"title": topic.get("title") if topic else None,
		"content": content,
		"message": message,
		"actions": list(actions),
	}


def resolve_field_help(
	*,
	doctype: str,
	fieldname: str,
	readable: bool,
	topics: Iterable[Mapping],
	description: str | None,
	language: str,
	version: str | None,
	roles: Iterable[str],
) -> dict:
	"""Pick the help of one field. `readable` is the user's read permission on the field."""
	if not readable:
		return _answer("unavailable")
	role_set = set(roles)
	ranked: dict[str, list] = {layer: [] for layer, _source in LAYERS}
	for topic in topics:
		if not _matches_field(topic, doctype, fieldname) or topic.get("layer") not in ranked:
			continue
		rank = _rank(topic, language or "", version, role_set)
		if rank is not None:
			ranked[topic["layer"]].append((rank, topic))
	for layer, source in LAYERS:
		if ranked[layer]:
			best = max(ranked[layer], key=lambda item: item[0])[1]
			return _answer(source, topic=best, content=best.get("content"))
	if _text(description):
		return _answer("description", content=description.strip())
	return _answer("none", message=NO_HELP_MESSAGE, actions=(REQUEST_HELP,))


def target_errors(topic: Mapping, *, field_exists: bool = False, field_is_custom: bool = False) -> list[str]:
	"""List the target problems of a topic. Help on a custom field belongs to the tenant."""
	kind = topic.get("target_type")
	if kind == FIELD:
		missing = [key for key in ("document_type", "fieldname") if not _text(topic.get(key))]
		if missing:
			return missing
		if not field_exists:
			return ["field_missing"]
		if field_is_custom and topic.get("layer") != TENANT:
			return ["custom_field_layer"]
		return []
	if kind == COMPONENT:
		return [] if _text(topic.get("component_id")) else ["component_id"]
	if kind == ROUTE:
		return [] if _text(topic.get("route_pattern")) else ["route_pattern"]
	return ["target_type"]


def _ratio(part: int, total: int) -> float | None:
	return round(part / total, 4) if total else None


def coverage_report(fields: Iterable[Mapping], topics: Iterable[Mapping]) -> dict:
	"""Share of fields with help. A published topic or a field description counts as help."""
	with_topic = {
		(topic.get("document_type"), topic.get("fieldname"))
		for topic in topics
		if topic.get("status") == PUBLISHED and topic.get("target_type") == FIELD
	}
	total = topic_count = description_count = 0
	missing = []
	for field in fields:
		total += 1
		key = (field.get("doctype"), field.get("fieldname"))
		if key in with_topic:
			topic_count += 1
		elif _text(field.get("description")):
			description_count += 1
		else:
			missing.append(
				{"doctype": key[0], "fieldname": key[1], "is_custom": bool(field.get("is_custom"))}
			)
	covered = topic_count + description_count
	return {
		"total": total,
		"with_topic": topic_count,
		"with_description_only": description_count,
		"covered": covered,
		"without_help": total - covered,
		"ratio": _ratio(covered, total),
		"topic_ratio": _ratio(topic_count, total),
		"missing": missing,
	}
