"""Operasyon kontratını yükler, doğrular, arar ve kapsamı ölçer.

Kontrat `contracts/` altındaki JSON dosyalarıdır (biçim: INTERFACE.md). Kontrat neyin bilindiğini ve
hangi statüde olduğunu söyler; neyin yürütülebileceğine runtime'daki kod izin listesi karar verir.
`validate()` ikisinin tutarlılığını da denetler.
"""
from __future__ import annotations

import json
import os
import re

from .errors import ContractError
from .schema import check_schema

FAMILIES = ("release", "build_deploy", "bench_site", "jobs_diagnostics", "backups", "infrastructure", "access", "app_dev")
PRESS_FILES = ("release", "build-deploy", "bench-site", "jobs-diagnostics", "backups", "infrastructure", "access")
STATUSES = ("implemented", "read_only", "planned", "unsupported", "not_applicable", "unknown")
KINDS = ("read", "mutation", "analysis", "human", "external")
ROLES = ("team", "operator", "infrastructure_owner", "dns_owner", "account_holder", "app_developer")
TRANSPORTS = ("method", "doc_method", "get_doc", "get_list", "https", "local", "human", "unavailable")
RISKS = ("read", "write", "destructive")
APPROVALS = ("none", "single", "double", "human_only")
STEP_ROLES = ("operation", "verification", "diagnosis", "handoff", "narrative")
SKILLS = ("press-operations", "press-build-triage", "frappe-custom-app", "frappe-app-extension")
AGENTS = ("press-diagnoser", "press-operator", "frappe-app-developer", "frappe-change-reviewer")
TOOLS = ("kit_status", "contract_search", "contract_get", "ui_reference_search", "press_read", "press_triage_build",
         "press_propose", "proposal_get", "press_execute", "press_track", "app_inspect", "app_check",
         "app_propose_change", "app_apply")
MACHINE_PRECONDITIONS = (
    "principal.team", "principal.operator", "release_group.owned_by_team", "release_group.no_deploy_in_progress",
    "release_group.app_absent", "release_group.app_present", "release_group.title_available",
    "release_group.auto_deploy_off", "team.resolved_matches_config", "deploy.artifact_matches_build",
    "app_source.matches_app", "deploy_candidate.belongs_to_group",
    "deploy_candidate.apps_released", "deploy_candidate.no_active_build", "build.success_all_steps",
    "deploy.not_created_for_candidate", "site.owned_by_team", "site.active", "site.no_running_jobs",
    "site.recent_backup", "site.app_available", "proposal.no_unknown_outcome",
)
TRACK_PROBES = ("track.release_group", "track.app_release", "track.candidate", "track.build", "track.deploy",
                "track.site_job", "track.site_backup", "track.agent_job")
OPERATION_KEYS = (
    "id", "family", "title", "kind", "status", "status_reason", "authority", "owner_handoff", "guide_steps", "ui",
    "doctypes", "api", "params", "preconditions", "side_effects", "async", "success", "failure", "risk", "approval",
    "mcp", "skill", "agent", "verification", "notes",
)
_ID = re.compile(r"[a-z][a-z_]*\.[a-z][a-z_]*")
# Adım kapsamı en zayıf işlemin statüsüdür; not_applicable nötrdür.
_STRENGTH = {"implemented": 5, "read_only": 4, "planned": 3, "unsupported": 2, "unknown": 1}


def _read_json(path: str):
    with open(path, "rb") as handle:
        return json.loads(handle.read())


class Contract:
    def __init__(self, directory: str):
        self.directory = directory
        self.operations = {}
        self.order = []
        self.files = {}
        self.load_errors = []
        self.guide = None
        self.sources = {}
        self.extension_points = None
        self._load()

    # -- yükleme ----------------------------------------------------------------------------------
    def _load(self) -> None:
        paths = [os.path.join(self.directory, "press", name + ".json") for name in PRESS_FILES]
        paths.append(os.path.join(self.directory, "frappe-app-operations.json"))
        for path in paths:
            rel = os.path.relpath(path, self.directory)
            if not os.path.exists(path):
                self.load_errors.append(rel + ": missing")
                continue
            try:
                data = _read_json(path)
            except ValueError as error:
                self.load_errors.append(rel + ": invalid JSON (" + str(error) + ")")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("operations"), list):
                self.load_errors.append(rel + ": expected {family, operations[]}")
                continue
            self.files[rel] = data.get("family")
            for op in data["operations"]:
                op_id = op.get("id") if isinstance(op, dict) else None
                if not isinstance(op_id, str):
                    self.load_errors.append(rel + ": operation without id")
                    continue
                if op_id in self.operations:
                    self.load_errors.append(rel + ": duplicate id " + op_id)
                    continue
                self.operations[op_id] = op
                self.order.append(op_id)
                op.setdefault("_file", rel)
        for name, attr in (("guide-map.json", "guide"), ("frappe-extension-points.json", "extension_points")):
            path = os.path.join(self.directory, name)
            if os.path.exists(path):
                try:
                    setattr(self, attr, _read_json(path))
                except ValueError as error:
                    self.load_errors.append(name + ": invalid JSON (" + str(error) + ")")
            else:
                self.load_errors.append(name + ": missing")
        path = os.path.join(self.directory, "sources.json")
        if os.path.exists(path):
            try:
                data = _read_json(path)
                self.sources = {s["id"]: s for s in data.get("sources", []) if isinstance(s, dict) and "id" in s}
            except (ValueError, KeyError, AttributeError) as error:
                self.load_errors.append("sources.json: invalid (" + str(error) + ")")
        else:
            self.load_errors.append("sources.json: missing")

    # -- erişim -----------------------------------------------------------------------------------
    def operation(self, op_id: str) -> dict:
        op = self.operations.get(op_id)
        if op is None:
            raise ContractError("Unknown operation: " + str(op_id), code="unknown_operation")
        return op

    def public(self, op: dict) -> dict:
        return {key: value for key, value in op.items() if not key.startswith("_")}

    def guide_steps(self) -> list:
        if not isinstance(self.guide, dict):
            return []
        return [s for s in self.guide.get("steps", []) if isinstance(s, dict)]

    def step_status(self, step: dict) -> str:
        statuses = []
        for op_id in step.get("operations") or []:
            op = self.operations.get(op_id)
            status = op.get("status") if op else "unknown"
            if status != "not_applicable":
                statuses.append(status)
        if not statuses:
            return "not_applicable"
        return min(statuses, key=lambda s: _STRENGTH.get(s, 0))

    def search(self, query: str, family=None, status=None, limit: int = 20) -> dict:
        terms = [t for t in re.split(r"[\s,]+", (query or "").lower()) if t]
        scored = []
        for op_id in self.order:
            op = self.operations[op_id]
            if family and op.get("family") != family:
                continue
            if status and op.get("status") != status:
                continue
            hay_id = op_id.lower()
            hay = " ".join(str(op.get(k, "")) for k in ("title", "status_reason", "family", "kind", "success")).lower()
            hay += " " + " ".join(op.get("guide_steps") or []).lower()
            hay += " " + " ".join(d.get("doctype", "") for d in op.get("doctypes") or [] if isinstance(d, dict)).lower()
            hay += " " + " ".join(
                "{} {} {}".format(a.get("method", ""), a.get("doctype", ""), a.get("transport", ""))
                for a in op.get("api") or [] if isinstance(a, dict)).lower()
            score = 0
            for term in terms:
                if term == hay_id:
                    score += 10
                elif term in hay_id:
                    score += 4
                elif term in hay:
                    score += 1
            if score or not terms:
                scored.append((score, op_id))
        scored.sort(key=lambda item: (-item[0], self.order.index(item[1])))
        results = [self.compact(self.operations[op_id]) for _, op_id in scored[:limit]]
        steps = []
        for step in self.guide_steps():
            text = " ".join([str(step.get("id", "")), str(step.get("note", ""))]).lower()
            if terms and all(term in text for term in terms):
                steps.append({"guide_step": step.get("id"), "role": step.get("role"),
                              "operations": step.get("operations"), "coverage": self.step_status(step)})
        return {"operations": results, "guide_steps": steps[:limit], "total_matches": len(scored)}

    @staticmethod
    def compact(op: dict) -> dict:
        return {key: op.get(key) for key in ("id", "family", "title", "kind", "status", "risk", "approval", "authority",
                                             "guide_steps")}

    # -- kapsam -----------------------------------------------------------------------------------
    def coverage(self) -> dict:
        by_family = {}
        for op_id in self.order:
            op = self.operations[op_id]
            row = by_family.setdefault(op.get("family"), {s: 0 for s in STATUSES})
            if op.get("status") in row:
                row[op["status"]] += 1
        steps = self.guide_steps()
        step_counts = {s: 0 for s in STATUSES}
        with_implemented = 0
        for step in steps:
            step_counts[self.step_status(step)] = step_counts.get(self.step_status(step), 0) + 1
            if any((self.operations.get(o) or {}).get("status") == "implemented" for o in step.get("operations") or []):
                with_implemented += 1
        return {
            "operations_total": len(self.order),
            "operations_by_family": by_family,
            "guide_steps_total": len(steps),
            "guide_steps_by_weakest_status": step_counts,
            "guide_steps_with_an_implemented_operation": with_implemented,
            "live_press_verification": "not_run",
        }

    # -- doğrulama --------------------------------------------------------------------------------
    def validate(self, runtime_implemented=None, guide_step_ids=None, sitemap_ids=None,
                 runtime_preconditions=None) -> list:
        """Hata listesini döndürür. `runtime_implemented`: {op_id: params_schema} (kod izin listesi);
        `runtime_preconditions`: {op_id: [makine ön koşulu]} (runtime'ın gerçekten çalıştırdığı denetimler)."""
        errors = list(self.load_errors)
        for rel, family in self.files.items():
            if family not in FAMILIES:
                errors.append(rel + ": unknown family " + str(family))
        step_ids = {s.get("id") for s in self.guide_steps()}
        for op_id in self.order:
            errors.extend(self._validate_operation(self.operations[op_id], step_ids, sitemap_ids))
        if self.guide is not None:
            errors.extend(self._validate_guide(guide_step_ids))
        if runtime_implemented is not None:
            for op_id, schema in runtime_implemented.items():
                op = self.operations.get(op_id)
                if op is None:
                    errors.append(op_id + ": implemented in runtime but missing from contract")
                    continue
                if op.get("status") != "implemented":
                    errors.append(op_id + ": implemented in runtime but contract status is " + str(op.get("status")))
                if op.get("params") != schema:
                    errors.append(op_id + ": contract params differ from runtime schema (see server.py schemas)")
            for op_id in self.order:
                if self.operations[op_id].get("status") == "implemented" and op_id not in runtime_implemented:
                    errors.append(op_id + ": contract says implemented but runtime has no executor")
        for op_id, checks in (runtime_preconditions or {}).items():
            op = self.operations.get(op_id)
            if op is None:
                continue
            declared = {p.get("id") for p in op.get("preconditions") or [] if isinstance(p, dict) and p.get("machine")}
            if declared != set(checks):
                errors.append("{}: machine preconditions differ from runtime (contract-only {}, runtime-only {})".format(
                    op_id, sorted(declared - set(checks)), sorted(set(checks) - declared)))
        return errors

    def _validate_operation(self, op: dict, step_ids: set, sitemap_ids) -> list:
        where = "{} ({})".format(op.get("id"), op.get("_file"))
        errors = []
        keys = {k for k in op if not k.startswith("_")}
        missing = set(OPERATION_KEYS) - keys
        extra = keys - set(OPERATION_KEYS)
        if missing:
            errors.append(where + ": missing keys " + ", ".join(sorted(missing)))
        if extra:
            errors.append(where + ": unknown keys " + ", ".join(sorted(extra)))
        if not _ID.fullmatch(str(op.get("id"))):
            errors.append(where + ": id must look like family_object.verb")
        file_family = self.files.get(op.get("_file"))
        if op.get("family") != file_family:
            errors.append(where + ": family differs from file family")
        for key, allowed in (("kind", KINDS), ("status", STATUSES), ("risk", RISKS), ("approval", APPROVALS)):
            if op.get(key) not in allowed:
                errors.append(where + ": invalid " + key + " " + repr(op.get(key)))
        authority = op.get("authority")
        if not isinstance(authority, list) or not authority or any(a not in ROLES for a in authority):
            errors.append(where + ": authority must be a non-empty list of known roles")
        for text_key in ("title", "status_reason", "success"):
            if not isinstance(op.get(text_key), str) or not op.get(text_key).strip():
                errors.append(where + ": " + text_key + " must be non-empty text")
        for step in op.get("guide_steps") or []:
            if step_ids and step not in step_ids:
                errors.append(where + ": unknown guide step " + str(step))
        for ui in op.get("ui") or []:
            if not isinstance(ui, dict) or ui.get("surface") not in ("desk", "dashboard"):
                errors.append(where + ": ui entries need surface desk|dashboard")
                continue
            for node in ui.get("sitemap_node_ids") or []:
                if sitemap_ids is not None and node not in sitemap_ids:
                    errors.append(where + ": unknown sitemap node " + str(node))
        api = op.get("api")
        if not isinstance(api, list):
            errors.append(where + ": api must be a list")
            api = []
        for entry in api:
            if not isinstance(entry, dict) or entry.get("transport") not in TRANSPORTS:
                errors.append(where + ": api entry needs a known transport")
                continue
            if entry.get("principal") not in ROLES:
                errors.append(where + ": api principal must be a known role")
            source = entry.get("source")
            if source is not None:
                if not isinstance(source, dict) or source.get("source_id") not in self.sources:
                    errors.append(where + ": api source must reference sources.json")
                else:
                    lines = source.get("lines")
                    if lines is not None and not (isinstance(lines, list) and len(lines) == 2
                                                  and all(isinstance(n, int) for n in lines) and lines[0] <= lines[1]):
                        errors.append(where + ": api source lines must be [first, last]")
            if entry.get("transport") in ("method", "doc_method", "get_doc", "get_list") and not entry.get("source"):
                errors.append(where + ": network api entries need a source reference")
        params = op.get("params")
        if params is not None:
            try:
                check_schema(params, op.get("id", "?"))
            except ValueError as error:
                errors.append(where + ": params " + str(error))
        if op.get("status") == "implemented" and params is None:
            errors.append(where + ": implemented operations need params")
        for pre in op.get("preconditions") or []:
            if not isinstance(pre, dict) or not isinstance(pre.get("id"), str):
                errors.append(where + ": precondition needs an id")
                continue
            if pre.get("machine") is True and pre["id"] not in MACHINE_PRECONDITIONS:
                errors.append(where + ": unknown machine precondition " + pre["id"])
        async_spec = op.get("async")
        if async_spec is not None:
            if not isinstance(async_spec, dict) or async_spec.get("track") not in TRACK_PROBES:
                errors.append(where + ": async.track must be a known probe")
        failure = op.get("failure")
        if not isinstance(failure, dict) or not {"modes", "timeout", "retry", "rollback"} <= set(failure):
            errors.append(where + ": failure needs modes, timeout, retry, rollback")
        mcp = op.get("mcp")
        if not isinstance(mcp, dict) or any(t not in TOOLS for t in mcp.get("tools", [])):
            errors.append(where + ": mcp.tools must list known tools")
        if op.get("skill") is not None and op.get("skill") not in SKILLS:
            errors.append(where + ": unknown skill " + str(op.get("skill")))
        if op.get("agent") is not None and op.get("agent") not in AGENTS:
            errors.append(where + ": unknown agent " + str(op.get("agent")))
        verification = op.get("verification")
        if not isinstance(verification, dict) or verification.get("live") != "not_run":
            errors.append(where + ": verification.live must stay not_run (no live Press check was performed)")
        elif verification.get("source") not in ("verified", "partial", "unverified"):
            errors.append(where + ": verification.source must be verified|partial|unverified")
        if op.get("status") == "implemented" and op.get("kind") == "mutation" and op.get("approval") in ("none", "human_only"):
            errors.append(where + ": implemented mutations need single or double approval")
        if op.get("status") in ("unsupported", "planned", "unknown") and not op.get("status_reason"):
            errors.append(where + ": status_reason is required")
        if op.get("status") == "unsupported":
            handoff = op.get("owner_handoff")
            if not isinstance(handoff, dict) or not handoff.get("role") or not handoff.get("steps"):
                errors.append(where + ": unsupported operations need an owner_handoff with role and steps")
        return errors

    def _validate_guide(self, guide_step_ids) -> list:
        errors = []
        steps = self.guide_steps()
        declared = (self.guide.get("guide") or {}).get("steps_total")
        if declared is not None and declared != len(steps):
            errors.append("guide-map.json: steps_total {} but {} steps listed".format(declared, len(steps)))
        ids = [s.get("id") for s in steps]
        if len(ids) != len(set(ids)):
            errors.append("guide-map.json: duplicate step ids")
        if guide_step_ids is not None:
            if ids != list(guide_step_ids):
                missing = [s for s in guide_step_ids if s not in ids]
                unknown = [s for s in ids if s not in guide_step_ids]
                errors.append("guide-map.json: steps must match guide.json order; missing {} unknown {}".format(
                    missing[:5], unknown[:5]))
        for step in steps:
            if step.get("role") not in STEP_ROLES:
                errors.append("guide-map.json: {} has invalid role".format(step.get("id")))
            if step.get("guide_status") not in ("live", "historical"):
                errors.append("guide-map.json: {} has invalid guide_status".format(step.get("id")))
            for op_id in step.get("operations") or []:
                if op_id not in self.operations:
                    errors.append("guide-map.json: {} references unknown operation {}".format(step.get("id"), op_id))
            if step.get("role") != "narrative" and not step.get("operations"):
                errors.append("guide-map.json: {} needs operations unless narrative".format(step.get("id")))
        return errors
