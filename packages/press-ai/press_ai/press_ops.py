"""Press işlemleri: okuma, öneri, onaylı yürütme ve izleme.

Bu modüldeki `READS` ve `MUTATIONS` kod izin listesidir: model yalnız buradaki işlem kimliklerini, burada
tanımlı şemayla ve burada kurulan isteklerle çağırabilir. Kontrat (contracts/) belgeler ve statü taşır;
yeni bir çağrıyı yürütülebilir yapan tek şey bu dosyadaki koddur.

Kaynak: frappe/press @ebf3e2272dc386e9ceb5e064d6c911d7e2adb7c9 (yol/satırlar kontratta). Kurulu Press'in
sürümü farklı olabilir; uç nokta yoksa hata `press_not_found` olarak döner, sonuç uydurulmaz.
"""
from __future__ import annotations

import datetime as _dt
import json
import socket
import ssl
import urllib.error
import urllib.request

from . import triage
from .errors import ApprovalError, ConfigError, KitError, PreconditionError, PressError, PressTimeout
from .redaction import envelope, truncate
from .schema import validate
from .util import canonical_json, iso, parse_iso, sha256_hex

# -- şema parçaları ------------------------------------------------------------------------------
DOCNAME = {"type": "string", "minLength": 1, "maxLength": 140, "pattern": r"[A-Za-z0-9][A-Za-z0-9 ._@:()+-]{0,139}"}
APP = {"type": "string", "minLength": 1, "maxLength": 64, "pattern": r"[a-z][a-z0-9_]{0,63}"}
SITE = {"type": "string", "minLength": 4, "maxLength": 253,
        "pattern": r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+"}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 50}
BOOL = {"type": "boolean"}


def obj(required=(), **properties) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(required), "properties": properties}


def _pick(data, keys) -> dict:
    if not isinstance(data, dict):
        return {}
    return {key: data.get(key) for key in keys if key in data}


def _rows(data) -> list:
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _tail(ctx, text, limit: int) -> str:
    value, _ = truncate(str(text or ""), limit)
    return ctx.redactor.text(value)


# -- okuma işlemleri -----------------------------------------------------------------------------
class ReadOp:
    def __init__(self, op_id, principals, schema, fn):
        self.id, self.principals, self.schema, self.fn = op_id, principals, schema, fn


READS = {}


def read(op_id, principals, schema):
    def register(fn):
        READS[op_id] = ReadOp(op_id, principals, schema, fn)
        return fn
    return register


BOTH = ("team", "operator")
OPERATOR = ("operator",)
TEAM = ("team",)


_FALLBACK_NOTE = ("Press silently falls back to the user's default team when the user is not a member of the team in "
                  "X-Press-Team (press/utils get_current_team); team mutations require both to match.")


def _resolved_team(client) -> str | None:
    """Press'in bu istek için çözdüğü takım (press.api.account.current_team); kişisel alanlar alınmaz."""
    return _pick(client.call("press.api.account.current_team"), ("name",)).get("name")


@read("team.context", BOTH, obj())
def _team_context(ctx, client, p):
    user = client.call("frappe.auth.get_logged_user", http_method="GET")
    out = {"user": user, "principal": client.principal, "team_header": client.config.team}
    if client.principal == "team":
        team = _resolved_team(client)
        out.update(resolved_team=team, team_matches_config=team == client.config.team, note=_FALLBACK_NOTE)
    else:
        out.update(resolved_team=None, team_matches_config=None,
                   note="System User requests keep the configured team header; Press does not resolve a team.")
    return out


@read("release_group.list", BOTH, obj(limit=LIMIT))
def _release_group_list(ctx, client, p):
    keys = ("name", "title", "version", "status", "team", "enabled", "number_of_sites", "number_of_apps", "creation")
    if client.principal == "team":
        groups = client.call("press.api.bench.all")
    else:
        filters = {"enabled": 1}
        if client.config.team:  # System User tüm takımları görür; yapılandırılan takımla daraltılır.
            filters["team"] = client.config.team
        groups = client.get_list("Release Group", filters, ["name", "title", "version", "team", "enabled",
                                                            "creation"], p.get("limit", 20))
    return [_pick(g, keys) for g in _rows(groups)][: p.get("limit", 20)]


_GROUP_KEYS = ("name", "title", "team", "version", "status", "public", "no_sites", "creation", "last_updated")
_APP_KEYS = ("name", "app", "title", "source", "branch", "repository", "repository_owner", "repository_url", "hash",
             "release", "update_available", "next_release", "enabled", "last_github_poll_failed")


def _group(client, name) -> dict:
    return _pick(client.call("press.api.bench.get", {"name": name}), _GROUP_KEYS)


def _group_apps(client, name) -> list:
    return [_pick(a, _APP_KEYS) for a in _rows(client.call("press.api.bench.apps", {"name": name}))]


@read("release_group.get", BOTH, obj(["release_group"], release_group=DOCNAME))
def _release_group_get(ctx, client, p):
    return {"group": _group(client, p["release_group"]), "apps": _group_apps(client, p["release_group"])}


@read("release_group.dependencies", BOTH, obj(["release_group"], release_group=DOCNAME))
def _release_group_dependencies(ctx, client, p):
    return client.call("press.api.bench.dependencies", {"name": p["release_group"]})


@read("app_source.branches", BOTH, obj(["release_group", "app"], release_group=DOCNAME, app=APP))
def _app_source_branches(ctx, client, p):
    return client.call("press.api.bench.branch_list", {"name": p["release_group"], "app": p["app"]})


@read("deploy_candidate.list", BOTH, obj(["release_group"], release_group=DOCNAME, limit=LIMIT))
def _candidate_list(ctx, client, p):
    limit = p.get("limit", 10)
    if client.principal == "team":
        data = client.call("press.api.bench.candidates", {"filters": {"group": p["release_group"]},
                                                          "limit_page_length": limit})
        return {"candidates": [_pick(c, ("name", "creation", "status", "apps")) for c in _rows(data)],
                "note": "Deploy Candidate has no status column at frappe/press@ebf3e22; this list's status may "
                        "be stale. Use deploy_candidate.get or build.get for the build status."}
    rows = _rows(client.get_list("Deploy Candidate", {"group": p["release_group"]}, ["name", "creation"], limit))
    names = [r["name"] for r in rows if r.get("name")]
    builds = _rows(client.get_list("Deploy Candidate Build", {"deploy_candidate": ["in", names or ["__none__"]]},
                                   ["name", "deploy_candidate", "status", "creation"], 100)) if names else []
    for row in rows:
        mine = [b for b in builds if b.get("deploy_candidate") == row.get("name")]
        row["latest_build"] = mine[0] if mine else None
        row["builds"] = len(mine)
    return {"candidates": rows, "note": "A candidate has no status of its own; latest_build carries it."}


_CANDIDATE_APP_FIELDS = ["app", "source", "release", "hash", "idx"]
_BUILD_FIELDS = ["name", "status", "deploy_candidate", "group", "creation", "build_start", "build_end",
                 "build_duration", "retry_count", "manually_failed", "build_error"]
_BUILD_STEP_FIELDS = ["idx", "stage", "step", "stage_slug", "step_slug", "status", "duration", "cached", "output"]


def _candidate_doc(client, name) -> dict:
    """Operator: candidate satırları (app/source/release/hash) ve bağlı build'ler; açık alan listesiyle."""
    head = client.get_one("Deploy Candidate", name, ["name", "group", "team", "creation"])
    apps = [_pick(a, ("app", "source", "release", "hash")) for a in
            _rows(client.children("Deploy Candidate", "Deploy Candidate App", name, _CANDIDATE_APP_FIELDS))]
    builds = client.get_list("Deploy Candidate Build", {"deploy_candidate": name},
                             ["name", "status", "creation", "build_start", "build_end"], 20)
    return {"name": head.get("name"), "group": head.get("group"), "team": head.get("team"),
            "creation": head.get("creation"), "apps": apps, "builds": _rows(builds)}


@read("deploy_candidate.get", BOTH, obj(["deploy_candidate"], deploy_candidate=DOCNAME))
def _candidate_get(ctx, client, p):
    if client.principal == "operator":
        return _candidate_doc(client, p["deploy_candidate"])
    data = client.call("press.api.bench.candidate", {"name": p["deploy_candidate"]})
    out = _pick(data, ("name", "status", "creation", "build_start", "build_end", "build_duration", "apps", "jobs"))
    out["build_steps"] = [_step(ctx, s) for s in _rows((data or {}).get("build_steps"))]
    out["note"] = "status is the latest build's status (press.api.bench.candidate)"
    return out


def _step(ctx, s) -> dict:
    row = _pick(s, ("idx", "stage", "step", "stage_slug", "step_slug", "status", "duration", "cached"))
    row["output_tail"] = _tail(ctx, s.get("output"), 600)
    return row


def _build(ctx, client, name) -> dict:
    if client.principal == "team":
        doc = client.dashboard_get("Deploy Candidate Build", name) or {}
        steps = _rows(doc.get("build_steps"))
    else:
        doc = client.get_one("Deploy Candidate Build", name, _BUILD_FIELDS)
        steps = _rows(client.children("Deploy Candidate Build", "Deploy Candidate Build Step", name,
                                      _BUILD_STEP_FIELDS))
    out = _pick(doc, ("name", "status", "deploy_candidate", "group", "creation", "build_start", "build_end",
                      "build_duration", "retry_count", "deployed", "manually_failed"))
    out["build_error_tail"] = _tail(ctx, doc.get("build_error"), 800)
    out["build_steps"] = [dict(_step(ctx, s), output=s.get("output")) for s in steps]
    return out


@read("build.get", BOTH, obj(["build"], build=DOCNAME))
def _build_get(ctx, client, p):
    build = _build(ctx, client, p["build"])
    for step in build["build_steps"]:
        step.pop("output", None)
    return build


_DEPLOY_INFO_KEYS = ("deploy_in_progress", "has_running_release_pipeline", "bench_creation_underway", "last_deploy",
                     "update_available")


def _deploy_information(client, group) -> dict:
    """ReleaseGroup.deploy_information (press.api.bench.deploy_information): deploy_in_progress son build'i,
    o build'in bench'lerini ve yerinde güncelleme işlerini kapsar. press.api.bench.deploy_status yalnız Release
    Pipeline'a bakar; Desk/press-ai build'i pipeline açmadığı için meşgul durumu kaçırır."""
    info = client.call("press.api.bench.deploy_information", {"name": group})
    return info if isinstance(info, dict) else {}


_BENCH_BUSY = ["Pending", "Installing"]


def _group_activity(client, group) -> dict:
    """Grupta süren deploy/bench işi. deploy_information'a ek olarak bench'ler doğrudan okunur: Press'in
    last_benches_info'su Bench.candidate'ı build adıyla karşılaştırır (release_group.py) ve bench kurulumunu
    görmez; bench_creation_underway yalnız Release Pipeline varken hesaplanır."""
    info = _deploy_information(client, group)
    out = _pick(info, ("deploy_in_progress", "has_running_release_pipeline", "bench_creation_underway", "last_deploy"))
    if client.principal == "operator":
        out["benches_in_progress"] = _rows(client.get_list(
            "Bench", {"group": group, "status": ["in", _BENCH_BUSY]}, ["name", "status", "server", "candidate"], 20))
        out["queued_bench_creations"] = _rows(client.get_list(
            "New Bench Queue", {"group": group, "status": "Queued"}, ["name", "status"], 20))
    else:
        out["benches_in_progress"] = [_pick(b, ("name", "status")) for b in _rows(
            client.call("press.api.bench.versions", {"name": group})) if b.get("status") in _BENCH_BUSY]
        out["queued_bench_creations"] = None
        out["note"] = "A team principal cannot read New Bench Queue; a deploy whose benches are not created yet is invisible."
    out["busy"] = bool(out.get("deploy_in_progress") or out.get("has_running_release_pipeline")
                       or out.get("bench_creation_underway") or out["benches_in_progress"]
                       or out["queued_bench_creations"])
    return out


@read("deploy.status", BOTH, obj(["release_group"], release_group=DOCNAME))
def _deploy_status(ctx, client, p):
    group = p["release_group"]
    info = _deploy_information(client, group)
    out = _pick(info, _DEPLOY_INFO_KEYS)
    activity = _group_activity(client, group)
    out.update(busy=activity["busy"], benches_in_progress=activity["benches_in_progress"],
               queued_bench_creations=activity["queued_bench_creations"])
    if client.principal == "team":
        out["benches"] = [_pick(b, ("name", "status")) for b in _rows(
            client.call("press.api.bench.versions", {"name": group}))]
    else:
        out["benches"] = _rows(client.get_list("Bench", {"group": group, "status": ["not in", ["Archived"]]},
                                               ["name", "status", "server", "candidate", "build", "creation"], 20))
    out["note"] = ("busy = deploy_in_progress, a running Release Pipeline, bench creation, a Pending/Installing bench "
                   "or (operator) a queued bench creation. Build, bench and site states are separate; an Active bench "
                   "is not site success.")
    return out


@read("bench.list", BOTH, obj(["release_group"], release_group=DOCNAME))
def _bench_list(ctx, client, p):
    return client.call("press.api.bench.versions", {"name": p["release_group"]})


@read("site.create_options", BOTH, obj(["release_group"], release_group=DOCNAME))
def _site_create_options(ctx, client, p):
    return client.call("press.api.site.get_new_site_options", {"group": p["release_group"]})


_SITE_KEYS = ("name", "host_name", "status", "group", "team", "server", "frappe_version", "latest_frappe_version",
              "setup_wizard_complete", "pending_for_long", "archive_failed", "site_migration", "version_upgrade")


def _site(client, name) -> dict:
    data = client.call("press.api.site.get", {"name": name}) or {}
    out = _pick(data, _SITE_KEYS)
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    out["info"] = _pick(info, ("created_on", "last_deployed", "auto_updates_enabled"))
    return out


def _installed_apps(client, name) -> list:
    rows = client.call("press.api.site.installed_apps", {"name": name})
    return [_pick(a, ("app", "name", "title", "branch", "hash", "release", "version")) for a in _rows(rows)]


@read("site.get", BOTH, obj(["site"], site=SITE))
def _site_get(ctx, client, p):
    return {"site": _site(client, p["site"]), "installed_apps": _installed_apps(client, p["site"])}


def _site_jobs(client, site, limit=20) -> list:
    rows = client.call("press.api.site.jobs", {"filters": {"site": site}, "limit_page_length": limit})
    return [_pick(j, ("name", "job_type", "status", "creation", "start", "end", "duration")) for j in _rows(rows)]


@read("site.jobs", BOTH, obj(["site"], site=SITE, limit=LIMIT))
def _site_jobs_read(ctx, client, p):
    return {"jobs": _site_jobs(client, p["site"], p.get("limit", 20)),
            "note": "Press shows Undelivered jobs as Pending in this list."}


@read("site.https_check", BOTH, obj(["site"], site=SITE))
def _site_https_check(ctx, client, p):
    # Yalnız bu principal'ın Press'te görebildiği siteye istek atılır (rastgele hosta değil).
    site = _site(client, p["site"])
    if site.get("name") != p["site"]:
        raise KitError("Press did not confirm this site for the configured principal", code="press_not_found")
    return https_probe(p["site"], ctx.https_timeout)


def https_probe(host: str, timeout: float) -> dict:
    """TLS doğrulaması açık iki GET: Frappe `ping` ve `/login`. Yönlendirme izlenmez; içerik döndürülmez."""
    context = ssl.create_default_context()
    result = {"host": host, "tls_verification": "enabled"}
    try:
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
                result["tls_valid"] = True
                result["certificate"] = {"not_after": cert.get("notAfter"),
                                         "issuer": dict(x[0] for x in cert.get("issuer", ()) if x)}
                result["tls_version"] = tls.version()
    except ssl.SSLError as error:
        result.update(tls_valid=False, error="TLS verification failed: " + type(error).__name__)
        return result
    except OSError as error:
        result.update(tls_valid=None, error="Connection failed: " + type(error).__name__)
        return result
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), _NoFollow())
    for key, path in (("ping", "/api/method/ping"), ("login_page", "/login")):
        try:
            with opener.open(urllib.request.Request("https://" + host + path, method="GET"), timeout=timeout) as resp:
                body = resp.read(4096)
                entry = {"http_status": resp.status}
                if key == "ping":
                    try:
                        entry["message"] = json.loads(body.decode("utf-8")).get("message")
                    except (ValueError, AttributeError):
                        entry["message"] = None
                result[key] = entry
        except urllib.error.HTTPError as error:
            result[key] = {"http_status": error.code}
        except (OSError, urllib.error.URLError) as error:
            result[key] = {"error": type(error).__name__}
    result["meaning"] = ("TLS and HTTP answers only. Login, setup wizard and installed apps are separate checks; "
                         "'Active' in Press is not proof that the site works.")
    return result


class _NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect not followed", headers, fp)


_JOB_KEYS = ("name", "job_type", "status", "creation", "start", "end", "duration", "server", "bench", "site",
             "reference_doctype", "reference_name", "request_path", "request_method")
_JOB_FILTERS = ("reference_doctype", "reference_name", "job_type", "server", "bench", "site", "status")


@read("agent_job.list", BOTH, obj([], site=SITE, release_group=DOCNAME, reference_doctype=DOCNAME,
                                  reference_name=DOCNAME, job_type=DOCNAME, server=DOCNAME, status=DOCNAME, limit=LIMIT))
def _agent_job_list(ctx, client, p):
    limit = p.get("limit", 20)
    if client.principal == "team":
        if p.get("site"):
            return _site_jobs(client, p["site"], limit)
        if p.get("release_group"):
            rows = client.call("press.api.bench.jobs", {"filters": {"name": p["release_group"]},
                                                        "limit_page_length": limit})
            return [_pick(j, _JOB_KEYS) for j in _rows(rows)]
        raise KitError("The team principal lists jobs per site or release_group", code="invalid_params")
    filters = {key: p[key] for key in _JOB_FILTERS if key in p}
    if p.get("release_group"):
        filters["bench"] = ["in", [b.get("name") for b in _rows(client.get_list(
            "Bench", {"group": p["release_group"]}, ["name"], 50))] or ["__none__"]]
    rows = client.get_list("Agent Job", filters, list(_JOB_KEYS), limit)
    return {"jobs": [_pick(j, _JOB_KEYS) for j in _rows(rows)], "filters": filters,
            "note": "An empty filtered list is not proof that no job ran; widen the filter by server and time. "
                    "Agent Job has no team field: a System User sees every team's jobs unless filtered by the "
                    "team's site, bench or release_group."}


@read("agent_job.get", BOTH, obj(["job"], job=DOCNAME))
def _agent_job_get(ctx, client, p):
    if client.principal == "team":
        data = client.call("press.api.site.job", {"job": p["job"]}) or {}
        out = _pick(data, _JOB_KEYS)
    else:
        # request_data / request_files / data alanları registry parolası veya build token taşıyabilir: okunmaz.
        data = client.get_one("Agent Job", p["job"], list(_JOB_KEYS) + ["output", "traceback"])
        out = _pick(data, _JOB_KEYS)
        out["output_tail"] = _tail(ctx, data.get("output"), 1200)
        out["traceback_tail"] = _tail(ctx, data.get("traceback"), 1200)
        data["steps"] = client.get_list("Agent Job Step", {"agent_job": p["job"]},
                                        ["step_name", "status", "start", "end", "duration", "output"], 50,
                                        "creation asc")
    out["steps"] = [dict(_pick(s, ("step_name", "status", "start", "end", "duration")),
                         output_tail=_tail(ctx, s.get("output"), 600)) for s in _rows(data.get("steps"))]
    return out


@read("error_log.list", OPERATOR, obj([], reference_doctype=DOCNAME, reference_name=DOCNAME,
                                      method_contains={"type": "string", "minLength": 3, "maxLength": 80,
                                                       "pattern": r"[A-Za-z0-9 ._:/-]{3,80}"},
                                      limit=LIMIT, include_text=BOOL))
def _error_log_list(ctx, client, p):
    filters = {key: p[key] for key in ("reference_doctype", "reference_name") if key in p}
    if p.get("method_contains"):
        filters["method"] = ["like", "%" + p["method_contains"] + "%"]
    rows = _rows(client.get_list("Error Log", filters, ["name", "creation", "method", "reference_doctype",
                                                         "reference_name"], p.get("limit", 10)))
    if p.get("include_text"):
        for row in rows[:3]:
            doc = client.get_one("Error Log", row["name"], ["name", "error"])
            row["error_tail"] = _tail(ctx, doc.get("error"), 2000)
    return {"logs": rows, "filters": filters,
            "note": "Traceback text is redacted and truncated; it can still contain personal data. An empty filtered "
                    "list does not mean there was no error. Error Log is not scoped to a team; filter by the "
                    "reference document."}


@read("press.version", OPERATOR, obj())
def _press_version(ctx, client, p):
    return client.call("frappe.utils.change_log.get_versions", http_method="GET")


@read("site.backups", BOTH, obj(["site"], site=SITE))
def _site_backups(ctx, client, p):
    keys = ("name", "creation", "status", "with_files", "offsite", "database_size", "public_size", "private_size")
    rows = client.call("press.api.site.backups", {"name": p["site"]})
    return {"backups": [_pick(b, keys) for b in _rows(rows)],
            "note": "Download URLs are omitted on purpose. Only backups whose files are available are listed."}


@read("server.list", BOTH, obj(limit=LIMIT))
def _server_list(ctx, client, p):
    keys = ("name", "title", "status", "cluster", "team", "app_server", "db_server", "region_info")
    if client.principal == "team":
        rows = client.call("press.api.server.all")
    else:
        filters = {"team": client.config.team} if client.config.team else {}
        rows = client.get_list("Server", filters, ["name", "title", "status", "cluster", "team"], p.get("limit", 20))
    return [_pick(s, keys) for s in _rows(rows)][: p.get("limit", 20)]


@read("server.get", BOTH, obj(["server"], server=DOCNAME))
def _server_get(ctx, client, p):
    return _pick(client.call("press.api.server.get", {"name": p["server"]}),
                 ("name", "title", "status", "team", "app_server", "region_info"))


_SETTINGS_FIELDS = ["suspend_builds", "use_new_deploy_flow", "use_agent_job_callbacks", "enable_mcp", "log_server",
                    "monitor_server", "build_server", "offsite_backups_count"]


@read("press_settings.flags", OPERATOR, obj())
def _press_settings(ctx, client, p):
    data = client.call("frappe.client.get_value", {"doctype": "Press Settings", "fieldname": _SETTINGS_FIELDS})
    return {"fields": _pick(data, _SETTINGS_FIELDS),
            "note": "Only non-secret flags and links are read; credentials in Press Settings are never requested."}


# -- ön koşullar ---------------------------------------------------------------------------------
class Checks:
    """Bir öneri veya yürütme turunda ön koşulları hesaplar; aynı okumayı tekrarlamaz."""

    def __init__(self, ctx, client, params):
        self.ctx, self.client, self.params = ctx, client, params
        self.cache = {}

    def get(self, key, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]

    def group_name(self):
        """İşlemin grubu: doğrudan parametre ya da candidate/build kaydındaki grup (kiracı kapsamı için)."""
        if "release_group" in self.params:
            return self.params["release_group"]
        if "deploy_candidate" in self.params:
            return _candidate(self).get("group")
        if "build" in self.params:
            return _build_doc(self).get("group")
        return None

    def group(self):
        return self.get("group", lambda: _group(self.client, self.group_name()))

    def group_apps(self):
        return self.get("group_apps", lambda: _group_apps(self.client, self.group_name()))

    def site(self):
        return self.get("site", lambda: _site(self.client, self.params["site"]))

    def run(self, ids) -> list:
        results = []
        for check_id in ids:
            try:
                ok, evidence = PRECONDITIONS[check_id](self)
            except PressTimeout:
                ok, evidence = None, {"error": "timeout while checking"}
            except PressError as error:
                ok, evidence = None, {"error": error.code, "message": str(error)}
            results.append({"id": check_id, "ok": ok, "evidence": envelope(evidence, self.ctx.redactor)})
        return results


def _owned(checks, team_value):
    team = checks.client.config.team
    if not team:
        return True, {"note": "operator without a configured team: Press does not scope System User reads"}
    return team_value == team, {"expected_team": team, "actual_team": team_value}


def _pre_team_resolved(checks):
    if checks.client.principal != "team":
        return True, {"note": "System User requests keep the configured team header"}
    team = checks.get("resolved_team", lambda: _resolved_team(checks.client))
    expected = checks.client.config.team
    return bool(team) and team == expected, {"configured_team": expected, "resolved_team": team,
                                             "note": _FALLBACK_NOTE}


def _pre_principal(name):
    def check(checks):
        actual = checks.client.principal
        return actual == name, {"principal": actual}
    return check


def _pre_group_owned(checks):
    return _owned(checks, checks.group().get("team"))


def _pre_no_deploy(checks):
    group = checks.group_name()
    if not group:
        return None, {"note": "release group could not be determined"}
    activity = checks.get("group_activity", lambda: _group_activity(checks.client, group))
    if "deploy_in_progress" not in activity:
        return None, {"note": "deploy_information did not report deploy_in_progress"}
    return not activity["busy"], activity


def _app_names(apps):
    return {a.get("app") or a.get("name") for a in apps}


def _pre_app_absent(checks):
    names = _app_names(checks.group_apps())
    return checks.params["app"] not in names, {"apps_in_group": sorted(n for n in names if n)}


def _pre_app_present(checks):
    names = _app_names(checks.group_apps())
    return checks.params["app"] in names, {"apps_in_group": sorted(n for n in names if n)}


def _pre_auto_deploy_off(checks):
    """Yeni App Release, satırda enable_auto_deploy açıksa build+deploy'u birlikte tetikler
    (press/press/doctype/app_release/app_release.py after_insert → auto_deploy)."""
    if checks.client.principal != "operator":
        return None, {"note": "The team principal cannot read Release Group App.enable_auto_deploy; a new release "
                              "could start build and deploy together. Use the operator principal or the Dashboard."}
    rows = _rows(checks.client.children("Release Group", "Release Group App", checks.params["release_group"],
                                        ["app", "source", "enable_auto_deploy"]))
    row = next((r for r in rows if r.get("app") == checks.params["app"]), None)
    if row is None:
        return False, {"note": "app row not found in the group"}
    source = row.get("source")
    # auto_deploy her grupta bu kaynağı enable_auto_deploy=1 ile kullanan satırlar için çalışır (app_release.py).
    auto_rows = _rows(checks.client.get_list("Release Group App", {"source": source, "enable_auto_deploy": 1},
                                             ["parent", "app", "source"], 100, "idx asc", parent="Release Group"))
    evidence = {"app": row.get("app"), "source": source,
                "groups_with_auto_deploy": sorted({r.get("parent") for r in auto_rows if r.get("parent")})}
    marker = (checks.client.call("frappe.client.get_value", {"doctype": "Press Settings",
                                                             "fieldname": ["deploy_marker"]}) or {}).get("deploy_marker")
    evidence.update(deploy_marker_configured=bool(marker),
                    rule="A new App Release starts build and deploy together where enable_auto_deploy is on (after_insert "
                         "→ auto_deploy); a release is proposed only when there is none.")
    if evidence["groups_with_auto_deploy"]:
        return False, evidence
    if marker:
        # <işaret>-<grup> etiketsiz adlandırılan grubu, <işaret> takımın auto-deploy gruplarını dağıtır; hangisi
        # olacağını yeni commit'in mesajı belirler (app_release.py _has_auto_deploy_marker). Önceden doğrulanamaz.
        return None, dict(evidence, note="Press Settings deploy_marker is set: the next commit message decides whether "
                                         "Press builds and deploys a named group or the team's auto-deploy groups. A "
                                         "human checks the commit or clears the marker first.")
    return True, evidence


def _pre_title_available(checks):
    exists = checks.client.call("press.api.bench.exists", {"title": checks.params["title"]})
    return exists is False or exists == 0, {"exists": exists}


def _pre_source_matches(checks):
    p = checks.params
    if "apps" in p:  # release_group.create: her app/source çifti seçilen sürümde sunulmalı
        options = checks.get("bench_options", lambda: checks.client.call("press.api.bench.options"))
        versions = {v.get("name"): v for v in _rows((options or {}).get("versions"))}
        version = versions.get(p["version"])
        if not version:
            return False, {"version": p["version"], "available_versions": sorted(v for v in versions if v)}
        offered = {(a.get("name"), s.get("name")) for a in _rows(version.get("apps")) for s in _rows(a.get("sources"))}
        missing = [x for x in p["apps"] if (x["app"], x["source"]) not in offered]
        if missing:
            return None, {"unverifiable_pairs": missing,
                          "note": "press.api.bench.options lists framework sources only (only_frappe=True). Create "
                                  "the group with the framework source, then add other apps with release_group.add_app."}
        return True, {"verified_pairs": p["apps"]}
    if checks.client.principal == "operator":
        # Desk: App Source kaydı doğrudan okunur (uygulama, etkinlik, sürüm satırları).
        source = checks.client.get_one("App Source", p["source"], ["name", "app", "enabled", "branch",
                                                                    "repository_url", "public", "team"])
        versions = [v.get("version") for v in _rows(checks.client.children(
            "App Source", "App Source Version", p["source"], ["version"]))]
        group_version = checks.group().get("version")
        evidence = {"source": p["source"], "source_app": source.get("app"), "enabled": source.get("enabled"),
                    "source_versions": versions, "group_version": group_version}
        ok = source.get("app") == p["app"] and bool(source.get("enabled")) and group_version in versions
        return ok, evidence
    # Team: App Source Dashboard'da okunamaz (press.api.client ALLOWED_DOCTYPES). installable_apps/options yalnız
    # çerçeve kaynaklarını döndürür; uygulama kaynakları all_apps ile (Published Marketplace, grubun sürümü) görülür.
    rows = checks.client.call("press.api.bench.all_apps", {"name": p["release_group"]})
    pairs = {(a.get("app") or a.get("name"), s.get("name")) for a in _rows(rows) for s in _rows(a.get("sources"))}
    if (p["app"], p["source"]) in pairs:
        return True, {"app": p["app"], "source": p["source"], "verified_via": "press.api.bench.all_apps"}
    return None, {"app": p["app"], "source": p["source"], "verified_via": None,
                  "note": "Only public Marketplace sources for the group's version can be verified by a team principal. "
                          "Private App Source records are not readable by the team; verify in the Dashboard or use "
                          "the operator principal."}


def _candidate(checks):
    return checks.get("candidate", lambda: _candidate_doc(checks.client, checks.params["deploy_candidate"]))


def _pre_candidate_released(checks):
    apps = _candidate(checks)["apps"]
    missing = [a.get("app") for a in apps if not a.get("release") or not a.get("hash")]
    return bool(apps) and not missing, {"apps": len(apps), "without_release_or_hash": missing}


def _pre_candidate_no_active_build(checks):
    active = [b for b in _candidate(checks)["builds"] if b.get("status") in triage.INTERMEDIATE]
    return not active, {"active_builds": [b.get("name") for b in active]}


def _build_doc(checks):
    return checks.get("build", lambda: _build(checks.ctx, checks.client, checks.params["build"]))


def _pre_build_success(checks):
    build = _build_doc(checks)
    steps = build["build_steps"]
    not_success = [(s.get("stage"), s.get("step"), s.get("status")) for s in steps if s.get("status") != "Success"]
    ok = build.get("status") == "Success" and bool(steps) and not not_success
    return ok, {"status": build.get("status"), "steps": len(steps), "not_success": not_success[:5]}


_PLATFORM_FIELD = {"x86_64": "intel_build", "arm64": "arm_build"}


def _deploy_artifact(checks) -> dict:
    """Press'in kuracağı imaj: her grup sunucusu için platform → candidate.intel_build / arm_build
    (deploy.py _get_build_for_bench). deploy() çağrılan build'i kullanmaz."""
    def compute():
        build = _build_doc(checks)
        candidate = checks.client.get_one("Deploy Candidate", build.get("deploy_candidate"),
                                          ["name", "group", "intel_build", "arm_build"])
        group = build.get("group") or candidate.get("group")  # create_deploy grubu build'den alır
        servers = [r.get("server") for r in _rows(checks.client.children(
            "Release Group", "Release Group Server", group, ["server"])) if r.get("server")]
        platforms = {s.get("name"): s.get("platform") for s in _rows(checks.client.get_list(
            "Server", {"name": ["in", servers or ["__none__"]]}, ["name", "platform"], 50))}
        image = checks.client.get_one("Deploy Candidate Build", checks.params["build"],
                                      ["name", "docker_image", "platform"])
        per_server = {}
        for server in servers:
            field = _PLATFORM_FIELD.get(platforms.get(server))
            per_server[server] = {"platform": platforms.get(server), "deploys_build": candidate.get(field) if field else None}
        return {"build": checks.params["build"], "docker_image": image.get("docker_image"),
                "deploy_candidate": candidate.get("name"), "servers": per_server,
                "auto_update_sites": sorted(s["name"] for s in _group_sites(checks) if s["auto_updates_enabled"])}
    return checks.get("artifact", compute)


def _artifact_digest(artifact) -> str:
    """Ham (maskelenmemiş) artifact'ın özeti; karşılaştırma maskeleme kaybından etkilenmez."""
    return sha256_hex(canonical_json(artifact))


def _pre_artifact_matches(checks):
    artifact = _deploy_artifact(checks)
    servers = artifact["servers"]
    mismatched = {s: v for s, v in servers.items() if v.get("deploys_build") != artifact["build"]}
    ok = bool(servers) and not mismatched and bool(artifact.get("docker_image"))
    digest = _artifact_digest(artifact)
    evidence = {"artifact": artifact, "artifact_sha256": digest, "mismatched_servers": mismatched,
                "rule": "Press deploys candidate.intel_build/arm_build for each server platform, not the build passed "
                        "to deploy(); it must be this build, with an image. The auto-update site set is pinned too."}
    proposal_id = checks.cache.get("_proposal_id")
    if ok and proposal_id:  # yürütme: onaylanan (digest'e bağlı) artifact ile birebir aynı olmalı
        impact = (checks.ctx.store.load(proposal_id).get("preview") or {}).get("impact") or {}
        evidence["approved_artifact_sha256"] = impact.get("artifact_sha256")
        ok = impact.get("artifact_sha256") == digest
    return ok, evidence


def _pre_deploy_absent(checks):
    build = _build_doc(checks)
    candidate = build.get("deploy_candidate")
    rows = checks.client.get_list("Deploy", {"candidate": candidate}, ["name", "status", "creation"], 5)
    return not _rows(rows), {"deploy_candidate": candidate, "existing_deploys": [r.get("name") for r in _rows(rows)]}


def _pre_site_owned(checks):
    return _owned(checks, checks.site().get("team"))


def _pre_site_active(checks):
    status = checks.site().get("status")
    return status == "Active", {"status": status}


def _pre_site_no_running_jobs(checks):
    rows = checks.client.call("press.api.site.running_jobs", {"name": checks.params["site"]})
    running = [_pick(j, ("name", "job_type", "status")) for j in _rows(rows)]
    return not running, {"running_jobs": running}


def backup_age_verdict(creation, now_utc):
    """Yedek 24 saatten yeni mi? Press zamanı kendi saat diliminde yazar ve bu istemci o dilimi bilmez.

    `creation` UTC sanılarak okunur; gerçek fark = saf fark + ofset, ofset UTC-12..UTC+14 aralığındadır.
    Saf fark -14 sa ile +10 sa arasındaysa yaş her dilimde 24 saatten azdır (True); +36 saatten büyükse
    her dilimde 24 saatten fazladır (False); arada kalan durum doğrulanamaz (None).
    """
    from .util import parse_frappe_datetime
    moment = parse_frappe_datetime(creation)
    if moment is None:
        return None
    naive = now_utc - moment
    if _dt.timedelta(hours=-14) <= naive <= _dt.timedelta(hours=10):
        return True
    if naive > _dt.timedelta(hours=36):
        return False
    return None


def _pre_recent_backup(checks):
    rows = _rows(checks.client.call("press.api.site.backups", {"name": checks.params["site"]}))
    ok_rows = [r for r in rows if r.get("status") in (None, "Success")]
    if not ok_rows:
        return False, {"latest_backup": None, "rule": "a successful backup newer than 24h is required; "
                                                      "propose site.backup first"}
    latest = ok_rows[0]
    verdict = backup_age_verdict(latest.get("creation"), checks.ctx.clock())
    return verdict, {"latest_backup": _pick(latest, ("name", "creation", "with_files", "offsite")),
                     "rule": "newer than 24h in every possible Press timezone; otherwise take a fresh backup "
                             "(site.backup) and track it to success first"}


def _pre_app_available(checks):
    rows = checks.client.call("press.api.site.available_apps", {"name": checks.params["site"]})
    names = {a.get("app") or a.get("name") for a in _rows(rows)}
    installed = _app_names(_installed_apps(checks.client, checks.params["site"]))
    app = checks.params["app"]
    return app in names and app not in installed, {"available": app in names, "already_installed": app in installed}


def _pre_no_unknown(checks):
    target = checks.cache.get("_target")
    operation = checks.cache.get("_operation")
    pending = checks.ctx.store.unresolved(operation, target)
    pending = [x for x in pending if x["proposal_id"] != checks.cache.get("_proposal_id")]
    return not pending, {"unresolved_executions": pending,
                         "rule": "resolve earlier outcomes with press_track before trying again"}


PRECONDITIONS = {
    "principal.team": _pre_principal("team"),
    "principal.operator": _pre_principal("operator"),
    "team.resolved_matches_config": _pre_team_resolved,
    "deploy.artifact_matches_build": _pre_artifact_matches,
    "release_group.owned_by_team": _pre_group_owned,
    "release_group.no_deploy_in_progress": _pre_no_deploy,
    "release_group.app_absent": _pre_app_absent,
    "release_group.app_present": _pre_app_present,
    "release_group.title_available": _pre_title_available,
    "release_group.auto_deploy_off": _pre_auto_deploy_off,
    "app_source.matches_app": _pre_source_matches,
    "deploy_candidate.belongs_to_group": lambda c: (None, {"note": "not used by the implemented operations"}),
    "deploy_candidate.apps_released": _pre_candidate_released,
    "deploy_candidate.no_active_build": _pre_candidate_no_active_build,
    "build.success_all_steps": _pre_build_success,
    "deploy.not_created_for_candidate": _pre_deploy_absent,
    "site.owned_by_team": _pre_site_owned,
    "site.active": _pre_site_active,
    "site.no_running_jobs": _pre_site_no_running_jobs,
    "site.recent_backup": _pre_recent_backup,
    "site.app_available": _pre_app_available,
    "proposal.no_unknown_outcome": _pre_no_unknown,
}


# -- mutasyonlar ---------------------------------------------------------------------------------
class Mutation:
    def __init__(self, op_id, principals, schema, preconditions, request, target, approval, impact, track,
                 snapshot=None, confirm=None):
        self.id = op_id
        self.principals = principals
        self.schema = schema
        self.preconditions = list(preconditions) + ["proposal.no_unknown_outcome"]
        self.request = request
        self.target = target
        self.approval = approval
        self.impact = impact
        self.track = track
        self.snapshot = snapshot
        self.confirm = confirm


def _method(method, args):
    return {"transport": "method", "method": method, "args": args}


def _doc_method(doctype, name, method, args=None):
    return {"transport": "doc_method", "doctype": doctype, "name": name, "method": method, "args": args or {}}


def _job_names(checks):
    return [j["name"] for j in _site_jobs(checks.client, checks.params["site"], 20)]


MUTATIONS = {
    "release_group.create": Mutation(
        "release_group.create", TEAM,
        obj(["title", "version", "cluster", "apps"], title=DOCNAME, version=DOCNAME, cluster=DOCNAME,
            server={"type": ["string", "null"], "minLength": 1, "maxLength": 140,
                    "pattern": DOCNAME["pattern"]},
            apps={"type": "array", "minItems": 1, "maxItems": 50,
                  "items": obj(["app", "source"], app=APP, source=DOCNAME)}),
        ["principal.team", "team.resolved_matches_config", "release_group.title_available", "app_source.matches_app"],
        lambda p: _method("press.api.bench.new", {"bench": {
            "title": p["title"], "version": p["version"], "cluster": p["cluster"], "saas_app": "",
            "server": p.get("server"), "apps": [{"name": a["app"], "source": a["source"]} for a in p["apps"]]}}),
        lambda p: p["title"], "single",
        lambda c: {"creates": "Release Group '{}' ({}, {} apps)".format(c.params["title"], c.params["version"],
                                                                        len(c.params["apps"])),
                   "running_sites_affected": 0,
                   "note": "No bench exists until a candidate is built and deployed separately."},
        "track.release_group"),
    "release_group.add_app": Mutation(
        "release_group.add_app", BOTH,
        obj(["release_group", "app", "source"], release_group=DOCNAME, app=APP, source=DOCNAME),
        ["team.resolved_matches_config", "release_group.owned_by_team", "release_group.app_absent",
         "app_source.matches_app", "release_group.no_deploy_in_progress"],
        lambda p: _method("press.api.bench.add_app", {"name": p["release_group"], "source": p["source"],
                                                      "app": p["app"]}),
        lambda p: p["release_group"], "single",
        lambda c: {"changes": "Adds app '{}' with source '{}' to the group's Apps table".format(
            c.params["app"], c.params["source"]),
            "running_sites_affected": 0,
            "note": "Takes effect only in the next Deploy Candidate; order dependencies before dependants."},
        "track.release_group"),
    "app_release.create": Mutation(
        "app_release.create", BOTH,
        obj(["release_group", "app"], release_group=DOCNAME, app=APP),
        ["team.resolved_matches_config", "release_group.owned_by_team", "release_group.app_present",
         "release_group.auto_deploy_off"],
        lambda p: _method("press.api.bench.fetch_latest_app_update", {"name": p["release_group"], "app": p["app"]}),
        lambda p: "{}/{}".format(p["release_group"], p["app"]), "single",
        lambda c: {"changes": "Press fetches the latest commit of the group's source for '{}' and records an App "
                              "Release (create_release(force=True))".format(c.params["app"]),
                   "auto_deploy": "None found for this source (see release_group.auto_deploy_off); the release "
                                  "alone does not build or deploy."},
        "track.app_release",
        snapshot=lambda c: {"deploy_information": _deploy_info_app(c.client, c.params),
                            "release_error_logs": _release_error_logs(c.client, c.params)}),
    "deploy_candidate.create": Mutation(
        "deploy_candidate.create", OPERATOR,
        obj(["release_group"], release_group=DOCNAME),
        ["principal.operator", "release_group.owned_by_team", "release_group.no_deploy_in_progress"],
        lambda p: _doc_method("Release Group", p["release_group"], "create_deploy_candidate"),
        lambda p: p["release_group"], "single",
        lambda c: {"creates": "Draft Deploy Candidate for '{}' with the latest release of every app".format(
            c.params["release_group"]), "builds": False, "deploys": False,
            "apps": [a.get("app") or a.get("name") for a in c.group_apps()]},
        "track.candidate"),
    "build.start": Mutation(
        "build.start", OPERATOR,
        obj(["deploy_candidate"], deploy_candidate=DOCNAME, no_cache=BOOL),
        ["principal.operator", "release_group.owned_by_team", "deploy_candidate.apps_released",
         "deploy_candidate.no_active_build"],
        lambda p: _doc_method("Deploy Candidate", p["deploy_candidate"], "build",
                              {"no_cache": bool(p.get("no_cache", False))}),
        lambda p: p["deploy_candidate"], "single",
        lambda c: {"creates": "Deploy Candidate Build (build only, no deploy)",
                   "apps": _candidate(c)["apps"], "uses": "build server CPU, disk and registry push",
                   "no_cache": bool(c.params.get("no_cache", False))},
        "track.build"),
    "deploy.start": Mutation(
        "deploy.start", OPERATOR,
        obj(["build"], build=DOCNAME),
        ["principal.operator", "release_group.owned_by_team", "build.success_all_steps",
         "deploy.artifact_matches_build", "deploy.not_created_for_candidate", "release_group.no_deploy_in_progress"],
        lambda p: _doc_method("Deploy Candidate Build", p["build"], "deploy"),
        lambda p: p["build"], "double",
        lambda c: _deploy_impact(c), "track.deploy",
        confirm=lambda p, c: "DEPLOY {} AUTO-UPDATE {}".format(p["build"], _auto_update_count(c))),
    "site.backup": Mutation(
        "site.backup", BOTH,
        obj(["site"], site=SITE, with_files=BOOL),
        ["team.resolved_matches_config", "site.owned_by_team", "site.active", "site.no_running_jobs"],
        lambda p: _method("press.api.site.backup", {"name": p["site"], "with_files": bool(p.get("with_files", False))}),
        lambda p: p["site"], "single",
        lambda c: {"creates": "Backup Site job for {}".format(c.params["site"]),
                   "with_files": bool(c.params.get("with_files", False)), "site_stays_online": True},
        "track.site_backup", snapshot=lambda c: {"job_names": _job_names(c)}),
    "site.migrate": Mutation(
        "site.migrate", BOTH,
        obj(["site"], site=SITE, skip_failing_patches=BOOL),
        ["team.resolved_matches_config", "site.owned_by_team", "site.active", "site.no_running_jobs",
         "site.recent_backup"],
        lambda p: _method("press.api.site.migrate", {"name": p["site"],
                                                    "skip_failing_patches": bool(p.get("skip_failing_patches", False))}),
        lambda p: p["site"], "double",
        lambda c: {"changes": "Runs bench migrate on the live site (patches, schema sync); site status becomes "
                              "Pending while the job runs",
                   "skip_failing_patches": bool(c.params.get("skip_failing_patches", False)),
                   "warning": ("Skipping failing patches can leave data inconsistent."
                               if c.params.get("skip_failing_patches") else None)},
        "track.site_job", snapshot=lambda c: {"job_names": _job_names(c)},
        confirm=lambda p, c: "MIGRATE " + p["site"]),
    "site.install_app": Mutation(
        "site.install_app", BOTH,
        obj(["site", "app"], site=SITE, app=APP),
        ["team.resolved_matches_config", "site.owned_by_team", "site.active", "site.no_running_jobs",
         "site.app_available", "site.recent_backup"],
        # plan bilinçli olarak hep None: plan verilirse Press Marketplace aboneliği açar (site.py install_marketplace_conf);
        # ücretli plan kararı hesap sahibinindir.
        lambda p: _method("press.api.site.install_app", {"name": p["site"], "app": p["app"], "plan": None}),
        lambda p: "{}:{}".format(p["site"], p["app"]), "double",
        lambda c: {"changes": "Installs app '{}' on live site {} (install hooks and app migrations run)".format(
            c.params["app"], c.params["site"]),
            "subscription": "No Marketplace plan is sent; Press records a free app subscription. Paid plans are "
                            "the account holder's decision in the Dashboard."},
        "track.site_job", snapshot=lambda c: {"job_names": _job_names(c)},
        confirm=lambda p, c: "INSTALL {} {}".format(p["app"], p["site"])),
}

_TRACK_JOB_TYPE = {"site.migrate": "Migrate Site", "site.install_app": "Install App on Site",
                   "site.backup": "Backup Site"}


def _release_error_logs(client, p):
    """Operator: kaynağın 'Create Release Error' kayıtları (create_release hatayı yutar ve loglar). Team okuyamaz: None."""
    if client.principal != "operator":
        return None
    rows = _rows(client.children("Release Group", "Release Group App", p["release_group"], ["app", "source"]))
    source = next((r.get("source") for r in rows if r.get("app") == p["app"]), None)
    if not source:
        return None
    logs = client.get_list("Error Log", {"reference_doctype": "App Source", "reference_name": source,
                                         "method": "Create Release Error"}, ["name"], 50)
    return sorted(r.get("name") for r in _rows(logs) if r.get("name"))


def _deploy_info_app(client, p) -> dict:
    info = client.call("press.api.bench.deploy_information", {"name": p["release_group"]}) or {}
    for app in _rows(info.get("apps")):
        if (app.get("app") or app.get("name")) == p["app"]:
            return _pick(app, ("app", "source", "release", "hash", "next_release", "update_available"))
    return {}


_AUTO_UPDATE_STATUSES = ("Active", "Inactive", "Suspended")
_SITE_SCAN_LIMIT = 500


def _group_sites(checks) -> list:
    """Press schedule_updates kümesi: Active/Inactive/Suspended, skip_auto_updates kapalı, fatal_site_update yok
    (site_update.py sites_with_available_update). Broken siteler otomatik güncellenmez ama listelenir."""
    def compute():
        group = _build_doc(checks).get("group")
        rows = _rows(checks.client.get_list(
            "Site", {"group": group, "status": ["in", list(_AUTO_UPDATE_STATUSES) + ["Broken"]]},
            ["name", "status", "skip_auto_updates", "fatal_site_update", "only_update_at_specified_time"],
            _SITE_SCAN_LIMIT)) if group else []
        if len(rows) >= _SITE_SCAN_LIMIT:
            raise KitError("The group has {} or more sites; the deploy preview cannot list every site Press may "
                           "auto-update. A human reviews this deploy in Press.".format(_SITE_SCAN_LIMIT),
                           code="preview_incomplete")
        return [{"name": r.get("name"), "status": r.get("status"),
                 "auto_updates_enabled": (r.get("status") in _AUTO_UPDATE_STATUSES and not r.get("skip_auto_updates")
                                          and not r.get("fatal_site_update")),
                 "only_at_specified_time": bool(r.get("only_update_at_specified_time"))} for r in rows]
    return checks.get("group_sites", compute)


def _auto_update_count(checks) -> int:
    return len(_deploy_artifact(checks)["auto_update_sites"])


def _deploy_impact(checks) -> dict:
    build = _build_doc(checks)
    group = build.get("group")
    sites = _group_sites(checks)
    count = _auto_update_count(checks)
    artifact = _deploy_artifact(checks)
    return {"deploys_build": build.get("name"), "deploy_candidate": build.get("deploy_candidate"),
            "release_group": group, "artifact": artifact, "artifact_sha256": _artifact_digest(artifact),
            "effect": "Creates a Deploy: new benches on the group's servers from the pinned artifact.",
            "sites_in_group": sites, "active_sites_in_group": sum(1 for s in sites if s["status"] == "Active"),
            "site_auto_updates": ("Press schedules site updates every 15 minutes (press/hooks.py schedule_updates) for "
                                  "Active, Inactive and Suspended sites with auto updates on and no fatal update. {} "
                                  "site(s) here can be moved to the new bench, with migrations, without another "
                                  "approval. Broken sites are not auto-updated.".format(count))}


# -- araç uygulamaları ---------------------------------------------------------------------------
def _contract_excerpt(ctx, op_id) -> dict:
    try:
        op = ctx.contract.operation(op_id)
    except KitError:
        return {"contract": "missing"}
    return {key: op.get(key) for key in ("title", "side_effects", "success", "failure", "status") if key in op}


def press_read(ctx, args):
    op_id = args["operation"]
    params = args.get("params") or {}
    if op_id == "build.triage":
        raise KitError("Use press_triage_build for build.triage", code="wrong_tool")
    op = READS.get(op_id)
    if op is None:
        kind = "mutation (use press_propose)" if op_id in MUTATIONS else "not executable by this server"
        raise KitError("Operation {} is a {}".format(op_id, kind), code="not_a_read",
                       details={"contract": _contract_excerpt(ctx, op_id)})
    validate(params, op.schema)
    client = ctx.press()
    if client.principal not in op.principals:
        raise ConfigError("{} needs the {} principal".format(op_id, "/".join(op.principals)), code="wrong_principal")
    data = op.fn(ctx, client, params)
    return {"operation": op_id, "principal": client.principal, "result": envelope(data, ctx.redactor)}


def press_triage_build(ctx, args):
    client = ctx.press()
    if bool(args.get("build")) == bool(args.get("candidate")):
        raise KitError("Give exactly one of build or candidate", code="invalid_params")
    if args.get("build"):
        build = _build(ctx, client, args["build"])
    elif client.principal == "operator":
        candidate = _candidate_doc(client, args["candidate"])
        builds = candidate["builds"]
        if not builds:
            return {"state": "not_started", "classification": "no_build",
                    "explanation": "The candidate has no build yet.", "candidate": candidate["name"]}
        build = _build(ctx, client, builds[0]["name"])
    else:
        data = client.call("press.api.bench.candidate", {"name": args["candidate"]}) or {}
        build = {"name": None, "status": data.get("status"), "build_steps": _rows(data.get("build_steps"))}
    result = triage.classify(build, ctx.redactor)
    if client.principal == "operator" and build.get("name") and result.get("state") == "failed":
        try:
            logs = client.get_list("Error Log", {"reference_name": build["name"]},
                                   ["name", "creation", "method"], 5)
            result["error_logs"] = _rows(logs)
            result["error_logs_note"] = "Read the text with press_read error_log.list include_text=true."
        except (PressError, PressTimeout) as error:
            result["error_logs"] = {"unavailable": error.code}
    return {"operation": "build.triage", "principal": client.principal, "result": envelope(result, ctx.redactor)}


def _authority(ctx) -> dict:
    press = ctx.config.press
    return {"base_host": press.host, "principal": press.principal, "team": press.team}


def _require_enabled(ctx, op_id):
    if op_id not in MUTATIONS:
        raise KitError("{} is not executable by this server".format(op_id), code="not_executable",
                       details={"contract": _contract_excerpt(ctx, op_id)})
    if ctx.config.press is None:
        raise ConfigError("Press is not configured")
    if op_id not in ctx.config.press.enabled_mutations:
        raise ConfigError("{} is not in press.enabled_mutations; a human must enable it in the config file".format(
            op_id), code="mutation_disabled")
    return MUTATIONS[op_id]


def _run_checks(ctx, client, mutation, params, proposal_id=None):
    checks = Checks(ctx, client, params)
    checks.cache.update(_target=mutation.target(params), _operation=mutation.id, _proposal_id=proposal_id)
    results = checks.run(mutation.preconditions)
    return checks, results


def press_propose(ctx, args):
    op_id = args["operation"]
    params = args.get("params") or {}
    mutation = _require_enabled(ctx, op_id)
    validate(params, mutation.schema)
    client = ctx.press()
    if client.principal not in mutation.principals:
        raise ConfigError("{} needs the {} principal".format(op_id, "/".join(mutation.principals)),
                          code="wrong_principal")
    checks, results = _run_checks(ctx, client, mutation, params)
    failed = [r for r in results if r["ok"] is not True]
    if failed:
        raise PreconditionError("Preconditions not met; nothing was proposed", details={"checks": results})
    request = mutation.request(params)
    preview = {"checks": results, "impact": ctx.redactor.value(mutation.impact(checks)),
               "contract": _contract_excerpt(ctx, op_id),
               "track": mutation.track, "outcome_rule": "Execution returns 'accepted'. Only press_track can report "
                                                        "success, from Press state."}
    record = ctx.store.create("press", op_id, _authority(ctx), mutation.target(params), params, request, preview,
                              mutation.approval, mutation.confirm(params, checks) if mutation.confirm else None)
    return {"proposal_id": record["id"], "state": "pending", "digest12": record["digest"][:12],
            "approval_level": record["approval_level"], "expires_at": record["expires_at"],
            "preview": envelope(preview, ctx.redactor), "request": request,
            "human_approval_command": _approval_command(record["id"]),
            "note": "Nothing was executed. A human must approve this exact proposal in a separate terminal."}


def _approval_command(proposal_id):
    from .proposals import approval_command
    return approval_command(proposal_id)


def press_execute(ctx, args):
    record = ctx.store.require_approved(args["proposal_id"], "press")
    mutation = _require_enabled(ctx, record["operation"])
    if record["authority"] != _authority(ctx):
        raise ApprovalError("Proposal was made for a different Press host, principal or team", code="authority_changed")
    validate(record["params"], mutation.schema)
    if record["request"] != mutation.request(record["params"]):
        raise ApprovalError("Stored request does not match the operation", code="state_tampered")
    client = ctx.press()
    # Aynı (işlem, hedef) için tek yürütme: ön koşullar kilit altında yeniden okunur (bkz. ProposalStore).
    lock = ctx.store.acquire_target_lock(record["operation"], record["target"], record["id"])
    try:
        checks, results = _run_checks(ctx, client, mutation, record["params"], record["id"])
        failed = [r for r in results if r["ok"] is not True]
        if failed:
            raise PreconditionError("Preconditions changed since approval; nothing was executed",
                                    details={"checks": results})
        snapshot = mutation.snapshot(checks) if mutation.snapshot else {}
        ctx.store.consume(record["id"])
        request = record["request"]
        outcome = {"executed_at": iso(ctx.clock()), "snapshot": snapshot, "track": mutation.track, "checks": results}
        # İstek gönderilmeden önce kalıcı iz: süreç ölse bile sonuç 'unknown' kalır, kör tekrar engellenir.
        ctx.store.record_outcome(record["id"], dict(outcome, state="unknown", phase="dispatching"))
        try:
            if request["transport"] == "method":
                response = client.call(request["method"], request["args"])
            else:
                response = client.run_doc_method(request["doctype"], request["name"], request["method"],
                                                 request["args"])
            outcome.update(state="accepted", phase="sent", response=ctx.redactor.value(_compact_response(response)),
                           references=_references(record["operation"], record["params"], response),
                           meaning="Press accepted the request. This is not success; call press_track.")
        except PressTimeout as error:
            outcome.update(state="unknown", phase="sent", error=error.as_dict(),
                           meaning="No answer in time. The change may or may not have happened. Do not retry; "
                                   "call press_track or ask a human to inspect Press.")
        except PressError as error:
            state = "unknown" if (error.http_status or 0) >= 500 or error.kind in ("network", "protocol") else \
                "rejected_by_press"
            outcome.update(state=state, phase="sent", error=error.as_dict(),
                           meaning=("Press refused the request; nothing should have changed."
                                    if state == "rejected_by_press" else
                                    "Press failed while handling the request; the effect is unknown. Do not retry."))
        ctx.store.record_outcome(record["id"], outcome)
    finally:
        ctx.store.release_target_lock(lock)
    return _wrap_result(dict(outcome, proposal_id=record["id"], operation=record["operation"], target=record["target"]),
                        ctx.redactor)


_CONTROL_KEYS = ("proposal_id", "operation", "target", "state", "phase", "track", "executed_at", "meaning", "note",
                 "last_checked_at", "recorded_at", "resolved_by_human", "checks")


def _wrap_result(result, redactor) -> dict:
    """Denetim alanları açık kalır; Press'ten türeyen her şey (yanıt, kanıt, snapshot, referans, hata) zarfa girer.
    `checks` içindeki kanıt zaten zarflıdır."""
    out = {k: v for k, v in result.items() if k in _CONTROL_KEYS}
    data = {k: v for k, v in result.items() if k not in _CONTROL_KEYS}
    if data:
        out.update(envelope(data, redactor))
    return out


def _compact_response(response):
    if isinstance(response, dict):
        return _pick(response, ("name", "error", "message", "status", "group", "doctype"))
    return response


def _references(op_id, params, response) -> dict:
    refs = {}
    if isinstance(response, dict):
        if isinstance(response.get("message"), str):
            refs["created"] = response["message"]
        if response.get("name"):
            refs["created"] = response["name"]
        if response.get("error"):
            refs["press_reported_error"] = True
    elif isinstance(response, str):
        refs["created"] = response
    refs.update({k: params[k] for k in ("release_group", "deploy_candidate", "build", "site", "app") if k in params})
    if op_id == "release_group.create" and isinstance(response, str):
        refs["release_group"] = response
    return refs


# -- izleme --------------------------------------------------------------------------------------
_SITE_JOB_WINDOW = _dt.timedelta(minutes=10)


def press_track(ctx, args):
    proposal_id = args["proposal_id"]
    record = ctx.store.load(proposal_id)
    outcome = ctx.store.outcome(proposal_id)
    if outcome is None:
        return {"proposal_id": proposal_id, "state": "not_executed", "proposal": ctx.store.status(proposal_id)}
    if outcome.get("phase") == "consumed_without_outcome" or not outcome.get("executed_at"):
        # consume → 'dispatching' kaydı → gönderim sırası: kayıt yoksa istek hiç gönderilmedi. Probe çalışmaz, yazılmaz.
        return {"proposal_id": proposal_id, "operation": record["operation"], "target": record["target"],
                "state": "unknown", "phase": "not_sent",
                "meaning": "Consumed before dispatch; nothing was sent. A human resolves it with server.py resolve."}
    if outcome.get("state") in ("succeeded", "failed", "no_op", "rejected_by_press"):
        return _wrap_result(dict(outcome, note="Final state recorded earlier."), ctx.redactor)
    if record["authority"] != _authority(ctx):
        raise ApprovalError("Proposal was made for a different Press host, principal or team", code="authority_changed")
    client = ctx.press()
    probe = TRACKERS[outcome.get("track") or MUTATIONS[record["operation"]].track]
    try:
        state, evidence = probe(ctx, client, record, outcome)
    except PressTimeout:
        state, evidence = outcome.get("state", "unknown"), {"note": "Press read timed out; state unchanged"}
    except PressError as error:
        state, evidence = outcome.get("state", "unknown"), {"note": "Press read failed", "error": error.as_dict()}
    if outcome.get("state") == "unknown" and state == "in_progress":
        evidence["note"] = "A matching job/record was found after an unknown result."
    updated = dict(outcome, state=state, evidence=ctx.redactor.value(evidence), last_checked_at=iso(ctx.clock()))
    ctx.store.record_outcome(proposal_id, updated)
    return _wrap_result(dict(updated, proposal_id=proposal_id, operation=record["operation"]), ctx.redactor)


def _elapsed(ctx, outcome) -> _dt.timedelta:
    return ctx.clock() - parse_iso(outcome["executed_at"])


def _track_release_group(ctx, client, record, outcome):
    params = record["params"]
    name = (outcome.get("references") or {}).get("release_group") or params.get("release_group")
    if not name:
        return "unknown", {"note": "Press did not return the group name"}
    group = _group(client, name)
    apps = _group_apps(client, name)
    if record["operation"] == "release_group.add_app":
        match = [a for a in apps if (a.get("app") or a.get("name")) == params["app"]]
        if not match:
            return "failed", {"group": name, "note": "app is not in the group after the call"}
        source = match[0].get("source")
        if source and source != params["source"]:
            return "unknown", {"group": name, "source_in_group": source, "expected": params["source"]}
        return "succeeded", {"group": name, "app": match[0]}
    expected = (record.get("authority") or {}).get("team")
    if expected and group.get("team") and group.get("team") != expected:
        return "failed", {"group": group, "configured_team": expected,
                          "note": "The group was created under another team (Press team fallback); a human decides."}
    return "succeeded", {"group": group, "apps": [a.get("app") or a.get("name") for a in apps],
                         "note": "Group exists. No bench is deployed until build and deploy succeed separately."}


def _track_app_release(ctx, client, record, outcome):
    before = (outcome.get("snapshot") or {}).get("deploy_information") or {}
    after = _deploy_info_app(client, record["params"])
    if not after:
        return "unknown", {"note": "app not found in deploy information", "before": before}
    changed = (after.get("next_release") != before.get("next_release")
               or after.get("update_available") != before.get("update_available"))
    if changed:
        return "succeeded", {"before": before, "after": after}
    if _elapsed(ctx, outcome) < _dt.timedelta(minutes=2):
        return "in_progress", {"before": before, "after": after, "note": "release may still be created"}
    row = next((a for a in _group_apps(client, record["params"]["release_group"])
                if (a.get("app") or a.get("name")) == record["params"]["app"]), {})
    if row.get("last_github_poll_failed"):
        return "failed", {"before": before, "after": after, "last_github_poll_failed": True,
                          "note": "Press could not poll the source; create_release returned without a release "
                                  "(the error is logged as 'Create Release Error'). Fix source access first."}
    logs_before = (outcome.get("snapshot") or {}).get("release_error_logs")
    if logs_before is None:
        return "unknown", {"before": before, "after": after, "note": "No new release visible and Create Release Error "
                                                                     "logs cannot be read by this principal."}
    new_logs = sorted(set(_release_error_logs(client, record["params"]) or []) - set(logs_before))
    if new_logs:
        return "failed", {"before": before, "after": after, "create_release_errors": new_logs,
                          "note": "create_release failed and Press logged it; read error_log.list for these entries."}
    return "no_op", {"before": before, "after": after, "last_github_poll_failed": False,
                     "note": "No new release and no new Create Release Error; the source may already be at its "
                             "latest commit."}


def _track_candidate(ctx, client, record, outcome):
    name = (outcome.get("references") or {}).get("created")
    if not name:
        return "unknown", {"note": "Press did not return the candidate name"}
    candidate = _candidate_doc(client, name)
    missing = [a.get("app") for a in candidate["apps"] if not a.get("release") or not a.get("hash")]
    evidence = {"candidate": candidate["name"], "group": candidate["group"], "apps": candidate["apps"],
                "builds": candidate["builds"]}
    if missing:
        evidence["warning"] = "Apps without release/hash: build.start will refuse: {}".format(missing)
    return "succeeded", evidence


def _track_build(ctx, client, record, outcome):
    refs = outcome.get("references") or {}
    name = refs.get("created")
    if not name or refs.get("press_reported_error"):
        return "failed" if refs.get("press_reported_error") else "unknown", {"references": refs}
    result = triage.classify(_build(ctx, client, name), ctx.redactor)
    return {"in_progress": "in_progress", "succeeded": "succeeded", "failed": "failed"}.get(
        result["state"], "unknown"), {"build": name, "triage": result}


def _track_deploy(ctx, client, record, outcome):
    refs = outcome.get("references") or {}
    name = refs.get("created")
    build = _build(ctx, client, record["params"]["build"])
    if not name:
        rows = _rows(client.get_list("Deploy", {"candidate": build.get("deploy_candidate")},
                                     ["name", "status", "creation"], 5))
        if not rows:
            return "failed", {"note": "Press returned no Deploy and none exists for the candidate; read Error Log "
                                      "('Deploy Creation Error')."}
        name = rows[0]["name"]
    deploy = client.get_one("Deploy", name, ["name", "group", "candidate", "creation"])
    # Beklenen sunucular Deploy Bench satırlarıdır; Deploy Bench.bench @ebf3e22'de New Bench Queue'ya bağlıdır.
    # Kuyruk işlendikçe her sunucuda Bench (candidate alanı) ve New Bench işi kademeli oluşur.
    rows = _rows(client.children("Deploy", "Deploy Bench", name, ["server", "bench"]))
    queue_names = [r.get("bench") for r in rows if r.get("bench")]
    queues = {q.get("name"): q for q in _rows(client.get_list(
        "New Bench Queue", {"name": ["in", queue_names]}, ["name", "status", "bench"], 50))} if queue_names else {}
    bench_names = [q.get("bench") for q in queues.values() if q.get("bench")]
    benches = {b.get("name"): b for b in _rows(client.get_list(
        "Bench", {"name": ["in", bench_names]}, ["name", "status", "server", "build"], 50))} if bench_names else {}
    approved = (((record.get("preview") or {}).get("impact") or {}).get("artifact") or {}).get("servers") or {}
    servers = []
    for row in rows:
        queue = queues.get(row.get("bench")) or {}
        # Yalnız bu deploy'un kuyruğunun işaret ettiği bench sayılır; aynı candidate'ın başka bench'i değil.
        bench = benches.get(queue.get("bench")) if queue.get("bench") else None
        job = None
        if bench:
            jobs = _rows(client.get_list("Agent Job", {"bench": bench.get("name"), "job_type": "New Bench"},
                                         ["name", "status"], 1))
            job = jobs[0] if jobs else None
        expected_build = (approved.get(row.get("server")) or {}).get("deploys_build")
        servers.append({"server": row.get("server"), "queue": row.get("bench"), "queue_status": queue.get("status"),
                        "bench": (bench or {}).get("name"), "bench_status": (bench or {}).get("status"),
                        "bench_build": (bench or {}).get("build"), "approved_build": expected_build,
                        "artifact_matches": (None if not bench or not expected_build
                                             else (bench or {}).get("build") == expected_build),
                        "new_bench_job": job})
    evidence = {"deploy": name, "expected_servers": [r.get("server") for r in rows], "benches": servers}
    if not rows:
        return "unknown", dict(evidence, note="Deploy has no Deploy Bench rows; a human must inspect Press")
    if any(s["artifact_matches"] is False for s in servers):
        return "failed", dict(evidence, note="A bench was built from a different build than the approved artifact.")
    if any(s["queue_status"] == "Failure" or s["bench_status"] in ("Broken", "Archived")
           or (s["new_bench_job"] or {}).get("status") in ("Failure", "Delivery Failure") for s in servers):
        return "failed", evidence
    if all(s["bench_status"] == "Active" and (s["new_bench_job"] or {}).get("status") == "Success"
           and s["artifact_matches"] is not False for s in servers):
        return "succeeded", dict(evidence, note="Bench Active on every expected server is not site success; check "
                                                "sites separately.")
    return "in_progress", dict(evidence, note="Waiting for every expected server's bench and New Bench job.")


def _track_site_job(ctx, client, record, outcome):
    params = record["params"]
    expected = _TRACK_JOB_TYPE[record["operation"]]
    before = set((outcome.get("snapshot") or {}).get("job_names") or [])
    jobs = _site_jobs(client, params["site"], 20)
    new = [j for j in jobs if j["name"] not in before and j.get("job_type") == expected]
    if not new:
        if record["operation"] == "site.install_app":
            installed = _app_names(_installed_apps(client, params["site"]))
            if params["app"] in installed:
                return "no_op", {"note": "No new job, app already installed (Press returns without a job)."}
        if _elapsed(ctx, outcome) < _SITE_JOB_WINDOW:
            return "in_progress", {"note": "No new '{}' job visible yet".format(expected)}
        return "unknown", {"note": "No new '{}' job appeared within {} minutes; a human must inspect Press. "
                                   "Do not retry.".format(expected, int(_SITE_JOB_WINDOW.total_seconds() // 60))}
    if len(new) > 1:
        return "unknown", {"candidates": new,
                           "note": "More than one new '{}' job appeared (a scheduled job may have started); this "
                                   "execution's job cannot be identified. A human must inspect.".format(expected)}
    job = new[0]
    evidence = {"job": job}
    status = job.get("status")
    if status in ("Pending", "Running", "Undelivered"):
        return "in_progress", evidence
    if status != "Success":
        return "failed", evidence
    site = _site(client, params["site"])
    evidence["site_status"] = site.get("status")
    if record["operation"] == "site.install_app":
        installed = _app_names(_installed_apps(client, params["site"]))
        evidence["app_installed"] = params["app"] in installed
        if not evidence["app_installed"]:
            return "unknown", evidence
    if site.get("status") != "Active":
        return "unknown", dict(evidence, note="Job Success but site is not Active")
    return "succeeded", evidence


def _track_agent_job(ctx, client, record, outcome):
    name = (outcome.get("references") or {}).get("created")
    if not name:
        return "unknown", {"note": "no job reference"}
    job = _agent_job_get(ctx, client, {"job": name})
    status = job.get("status")
    state = {"Success": "succeeded", "Failure": "failed", "Delivery Failure": "failed"}.get(
        status, "in_progress" if status in ("Pending", "Running", "Undelivered") else "unknown")
    return state, {"job": job}


TRACKERS = {
    "track.release_group": _track_release_group,
    "track.app_release": _track_app_release,
    "track.candidate": _track_candidate,
    "track.build": _track_build,
    "track.deploy": _track_deploy,
    "track.site_job": _track_site_job,
    "track.site_backup": _track_site_job,
    "track.agent_job": _track_agent_job,
}


def implemented_schemas() -> dict:
    """Kod izin listesindeki işlemlerin params şeması (kontrattaki `params` ile birebir aynı olmalı)."""
    schemas = {op_id: op.schema for op_id, op in READS.items()}
    schemas.update({op_id: m.schema for op_id, m in MUTATIONS.items()})
    schemas["build.triage"] = TRIAGE_SCHEMA
    return schemas


TRIAGE_SCHEMA = obj([], build=DOCNAME, candidate=DOCNAME)
