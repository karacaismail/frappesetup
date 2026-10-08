"""Testler için yerel sahte Press (127.0.0.1, stdlib HTTP). Gerçek Press'in yalnız runtime'ın kullandığı
uç noktalarını, frappe/press @ebf3e22 dönüş biçimlerine göre taklit eder. Veriler uydurmadır; kişisel
veri veya gerçek kurulum kimliği içermez. Gizli alanlar (user_private_key, build_token, request_data)
bilerek tutulur: runtime'ın bunları hiç istemediği ve hiçbir çıktıya taşımadığı testlerde doğrulanır.
"""
import copy
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

KEY, SECRET = "k1a2b3c4d5e6f70", "s9z8y7x6w5v4u31"
# Sahte gizli değerler çalışma anında birleştirilir: depoda tarayıcıların tanıdığı tam kalıp bulunmaz.
FAKE_PRIVATE_KEY = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nAAAA\n-----END OPENSSH " + "PRIVATE KEY-----"
FAKE_GITHUB_TOKEN = "ghp_" + "SECRETSECRET123"
SECRET_FIELDS = {"user_private_key", "build_token", "request_data", "request_files", "data",
                 "github_access_token", "agent_github_access_token"}


def frappe_error(status, exc_type, message):
    return status, {"exc_type": exc_type, "exception": "{}: {}".format(exc_type, message),
                    "_server_messages": json.dumps([json.dumps({"message": message})])}


def ok(value):
    return 200, {"message": value}


class FakePress:
    def __init__(self, principal="team", team="team-alpha", user="operator@example.test"):
        self.principal = principal
        self.team = team
        self.member_teams = {team}  # kullanıcının üyesi olduğu takımlar
        self.default_team = team    # üyelik dışı başlıkta Press'in sessizce düştüğü takım (utils.get_current_team)
        self.current = team         # bu istek için çözülen takım
        self.user = user
        self.auto_start_benches = True  # False: Deploy yalnız New Bench Queue açar, bench'ler sonra (start_bench)
        self.requests = []  # (method, args, headers)
        self.fail = {}      # method -> (status, exc_type, message)
        self.delay = {}     # method -> seconds
        self.counter = 0
        self.lock = threading.Lock()
        self.reset()

    # -- veri ---------------------------------------------------------------------------------------
    def reset(self):
        self.groups = {"bench-0042": {"name": "bench-0042", "title": "school", "team": "team-alpha",
                                      "version": "Version 16", "status": "Active", "public": 0, "no_sites": 1,
                                      "creation": "2026-10-01 10:00:00.000000", "last_updated": "2026-10-02",
                                      "enabled": 1}}
        self.group_apps = {"bench-0042": [
            {"app": "frappe", "source": "SRC-frappe-1", "enable_auto_deploy": 0},
            {"app": "payments", "source": "SRC-payments-1", "enable_auto_deploy": 0},
        ]}
        self.sources = {
            "SRC-frappe-1": {"name": "SRC-frappe-1", "app": "frappe", "enabled": 1, "branch": "version-16",
                             "repository_url": "https://example.test/frappe/frappe", "public": 1, "team": "team-alpha",
                             "versions": ["Version 16"], "frappe": 1},
            "SRC-erpnext-1": {"name": "SRC-erpnext-1", "app": "erpnext", "enabled": 1, "branch": "version-16",
                              "repository_url": "https://example.test/frappe/erpnext", "public": 1,
                              "team": "team-alpha", "versions": ["Version 16"]},
            "SRC-education-1": {"name": "SRC-education-1", "app": "education", "enabled": 1, "branch": "version-16",
                                "repository_url": "https://example.test/frappe/education", "public": 1,
                                "team": "team-alpha", "versions": ["Version 16"]},
            "SRC-payments-1": {"name": "SRC-payments-1", "app": "payments", "enabled": 1, "branch": "version-16",
                               "repository_url": "https://example.test/frappe/payments", "public": 1,
                               "team": "team-alpha", "versions": ["Version 16"]},
        }
        self.group_servers = {"bench-0042": ["f1-app.example.test"]}
        self.group_tags = {}       # grup → Resource Tag adları (ör. "auto-deploy")
        self.marketplace = {"erpnext", "education", "payments"}  # Published Marketplace App'ler
        self.pipelines = []        # etkin Release Pipeline (yeni deploy akışı); kılavuz akışı açmaz
        self.subscriptions = []    # (site, app, plan): ücretli Marketplace aboneliği izi
        self.queues = {}           # New Bench Queue
        self.candidates = {}
        self.builds = {}
        self.deploys = {}
        self.benches = {"bench-0042-000001": {"name": "bench-0042-000001", "group": "bench-0042",
                                              "status": "Active", "server": "f1-app.example.test",
                                              "candidate": "deploy-0042-000001"}}
        self.jobs = {}
        self.sites = {"school.example.test": {"name": "school.example.test", "host_name": "school.example.test",
                                              "status": "Active", "group": "bench-0042", "team": "team-alpha",
                                              "server": "f1-app.example.test", "frappe_version": "Version 16",
                                              "apps": ["frappe", "payments"], "skip_auto_updates": 0,
                                              "communication_infos": [{"channel": "Email", "type": "Owner",
                                                                       "value": "owner@example.test"}],
                                              "info": {"owner": {"email": "owner@example.test"},
                                                       "created_on": "2026-10-01"}}}
        self.backups = {"school.example.test": [
            {"name": "BKP-1", "creation": "2020-01-01 00:00:00.000000", "status": "Success", "with_files": 0,
             "offsite": 0, "database_size": 1000, "database_url": "https://example.test/signed?token=abc123def456"}]}
        self.error_logs = []
        self.settings = {"suspend_builds": 0, "use_new_deploy_flow": 0, "use_agent_job_callbacks": 1,
                         "enable_mcp": 0, "log_server": None, "monitor_server": None, "build_server": "f1-build",
                         "offsite_backups_count": 30, "github_access_token": FAKE_GITHUB_TOKEN,
                         "deploy_marker": None}
        self.deploy_information = {"bench-0042": {"apps": [
            {"app": "frappe", "source": "SRC-frappe-1", "release": "REL-1", "hash": "aaaa", "next_release": "REL-1",
             "update_available": False},
            {"app": "payments", "source": "SRC-payments-1", "release": "REL-2", "hash": "bbbb",
             "next_release": "REL-2", "update_available": False}]}}

    def _id(self, prefix):
        self.counter += 1
        return "{}{:04d}".format(prefix, self.counter)

    def add_job(self, job_type, status="Pending", site=None, bench=None, reference=None, output="", traceback=""):
        name = self._id("job")
        self.jobs[name] = {"name": name, "job_type": job_type, "status": status, "creation": "2026-10-08 12:00:00",
                           "start": None, "end": None, "duration": None, "server": "f1-app.example.test",
                           "bench": bench, "site": site, "reference_doctype": (reference or (None, None))[0],
                           "reference_name": (reference or (None, None))[1], "request_path": "/agent/x",
                           "request_method": "POST", "output": output, "traceback": traceback,
                           "request_data": '{"registry_password": "hunter2-very-secret"}', "steps": []}
        return name

    def make_candidate(self, group, apps=None, released=True):
        name = "deploy-{}-{:06d}".format(group.split("-")[-1], len(self.candidates) + 2)
        rows = apps or [{"app": a["app"], "source": a["source"]} for a in self.group_apps[group]]
        for row in rows:
            row.setdefault("release", "REL-" + row["app"] if released else None)
            row.setdefault("hash", ("h-" + row["app"]) if released else None)
        self.candidates[name] = {"name": name, "group": group, "team": self.groups[group]["team"],
                                 "creation": "2026-10-08 11:00:00", "apps": rows,
                                 "user_private_key": FAKE_PRIVATE_KEY,
                                 "build_token": "bt-secret-0001"}
        return name

    def start_bench(self, deploy, server, status="Installing", job_status="Running"):
        """New Bench Queue işlenir: o sunucu için Bench ve New Bench işi oluşur (kademeli)."""
        dep = self.deploys[deploy]
        row = next(r for r in dep["benches"] if r["server"] == server)
        bench = "{}-{}-{}".format(dep["group"], deploy, server.split(".")[0])
        self.benches[bench] = {"name": bench, "group": dep["group"], "status": status, "server": server,
                               "candidate": dep["candidate"], "build": self.queues[row["bench"]].get("build")}
        self.queues[row["bench"]].update(status="Started", bench=bench)
        self.add_job("New Bench", job_status, bench=bench)
        return bench

    def candidate_build(self, candidate, platform="x86_64"):
        done = [b["name"] for b in self.builds.values() if b["deploy_candidate"] == candidate
                and b["status"] == "Success" and b.get("platform", "x86_64") == platform]
        return done[-1] if done else None

    def make_build(self, candidate, status="Pending", steps=None):
        name = self._id("bld")
        self.builds[name] = {"name": name, "deploy_candidate": candidate, "group": self.candidates[candidate]["group"],
                             "status": status, "creation": "2026-10-08 11:30:00", "build_start": None,
                             "build_end": None, "build_duration": None, "retry_count": 0, "manually_failed": 0,
                             "build_error": "", "team": self.candidates[candidate]["team"], "deployed": 0,
                             "build_steps": steps or []}
        return name

    # -- uç noktalar --------------------------------------------------------------------------------
    def handle(self, method, args, headers):
        with self.lock:
            self.requests.append((method, copy.deepcopy(args), dict(headers)))
        if method in self.delay:
            time.sleep(self.delay[method])
        if headers.get("Authorization") != "token {}:{}".format(KEY, SECRET):
            return frappe_error(401, "AuthenticationError", "Invalid token")
        if method in self.fail:
            return frappe_error(*self.fail[method])
        handler = getattr(self, "m_" + method.replace(".", "__"), None)
        if handler is None:
            return frappe_error(404, "DoesNotExistError", "No such method " + method)
        with self.lock:
            header = headers.get("X-Press-Team")
            # Press: kullanıcı başlıktaki takımın üyesi değilse hata vermeden varsayılan takıma geçer
            # (press/utils/__init__.py get_current_team). System User başlığı olduğu gibi kullanır.
            if self.principal == "team":
                self.current = header if header in self.member_teams else self.default_team
            else:
                self.current = header or self.default_team
            return handler(args)

    def m_frappe__auth__get_logged_user(self, a):
        return ok(self.user)

    def _group_or_403(self, name):
        group = self.groups.get(name)
        if group is None:
            return None, frappe_error(404, "DoesNotExistError", "Release Group not found")
        if self.principal == "team" and group["team"] != self.current:
            return None, frappe_error(403, "PermissionError", "Not Permitted")
        return group, None

    def m_press__api__account__current_team(self, a):
        # press.api.account.current_team → press.api.client.get("Team", frappe.local.team().name)
        return ok({"name": self.current, "team_title": self.current, "enabled": 1, "user": self.user,
                   "partner_email": "partner@example.test"})

    def m_press__api__bench__all(self, a):
        return ok([dict(g, number_of_apps=len(self.group_apps.get(g["name"], []))) for g in self.groups.values()
                   if g["team"] == self.current])

    def m_press__api__bench__get(self, a):
        group, err = self._group_or_403(a.get("name"))
        return err or ok({k: group[k] for k in ("name", "title", "team", "version", "status", "public", "no_sites",
                                                "creation", "last_updated")})

    def m_press__api__bench__apps(self, a):
        group, err = self._group_or_403(a.get("name"))
        if err:
            return err
        return ok([{"name": r["app"], "title": r["app"].title(), "branch": "version-16", "hash": None,
                    "update_available": False, "last_github_poll_failed": r.get("last_github_poll_failed", 0)}
                   for r in self.group_apps[group["name"]]])

    def m_press__api__bench__dependencies(self, a):
        return ok({"active_dependencies": [{"dependency": "PYTHON_VERSION", "version": "3.14"}]})

    def m_press__api__bench__branch_list(self, a):
        return ok([{"name": "version-16"}, {"name": "develop"}])

    def m_press__api__bench__exists(self, a):
        return ok(any(g["title"] == a.get("title") for g in self.groups.values()))

    def m_press__api__bench__options(self, a):
        apps = {}
        for source in self.sources.values():
            if source["public"] and source["enabled"] and source.get("frappe"):
                apps.setdefault(source["app"], []).append({"name": source["name"]})
        if not apps:
            return frappe_error(417, "ValidationError", "Only enabled, public app sources appear here.")
        return ok({"versions": [{"name": "Version 16", "apps": [{"name": n, "sources": s} for n, s in apps.items()]}],
                   "clusters": [{"name": "Default"}]})

    def m_press__api__bench__installable_apps(self, a):
        group, err = self._group_or_403(a.get("name"))
        if err:
            return err
        # bench.py installable_apps → options()["versions"]: yalnız çerçeve (frappe=1) kaynakları
        installed = {r["app"] for r in self.group_apps[group["name"]]}
        apps = {}
        for source in self.sources.values():
            if source["public"] and source["enabled"] and source.get("frappe") and source["app"] not in installed:
                apps.setdefault(source["app"], []).append({"name": source["name"]})
        return ok([{"name": n, "sources": s} for n, s in apps.items()])

    def m_press__api__bench__all_apps(self, a):
        # bench.py all_apps: Published Marketplace App'ler (grupta olmayan) + grubun sürümündeki public kaynaklar
        group, err = self._group_or_403(a.get("name"))
        if err:
            return err
        installed = {r["app"] for r in self.group_apps[group["name"]]}
        out = []
        for app in sorted(self.marketplace - installed):
            sources = [{"name": s["name"], "branch": s["branch"], "app": s["app"], "version": group["version"]}
                       for s in self.sources.values() if s["app"] == app and s["public"] and s["enabled"]
                       and group["version"] in s["versions"]]
            out.append({"name": app, "app": app, "title": app.title(), "sources": sources})
        return ok(out)

    def m_press__api__bench__new(self, a):
        bench = a["bench"]
        name = "bench-{:04d}".format(43 + len(self.groups))
        self.groups[name] = {"name": name, "title": bench["title"], "team": self.current, "version": bench["version"],
                             "status": "Awaiting Deploy", "public": 0, "no_sites": 0, "creation": "now",
                             "last_updated": "now", "enabled": 1}
        self.group_apps[name] = [{"app": x["name"], "source": x["source"], "enable_auto_deploy": 0}
                                 for x in bench["apps"]]
        return ok(name)

    def m_press__api__bench__add_app(self, a):
        group, err = self._group_or_403(a.get("name"))
        if err:
            return err
        self.group_apps[group["name"]].append({"app": a["app"], "source": a["source"], "enable_auto_deploy": 0})
        return ok(None)

    def m_press__api__bench__fetch_latest_app_update(self, a):
        for app in self.deploy_information[a["name"]]["apps"]:
            if app["app"] == a["app"]:
                app["next_release"] = "REL-new"
                app["update_available"] = True
        return ok(None)

    def m_press__api__bench__deploy_information(self, a):
        group, err = self._group_or_403(a.get("name"))
        if err:
            return err
        info = copy.deepcopy(self.deploy_information.get(a["name"], {"apps": []}))
        builds = [b for b in self.builds.values() if b["group"] == a["name"]]
        last = builds[-1] if builds else None  # last_dc_info: en yeni Deploy Candidate Build
        # release_group.py last_benches_info: Bench.candidate == <son build adı> (build adıyla karşılaştırır; eşleşmez)
        benches = [b for b in self.benches.values() if last and b.get("candidate") == last["name"]]
        running_pipeline = a["name"] in self.pipelines
        info.update(
            last_deploy={"name": last["name"], "status": last["status"]} if last else None,
            deploy_in_progress=bool(last and last["status"] in ("Scheduled", "Pending", "Preparing", "Running"))
            or any(b["status"] in ("Pending", "Installing") for b in benches),
            has_running_release_pipeline=running_pipeline,
            bench_creation_underway=False)
        return ok(info)

    def m_press__api__bench__deploy_status(self, a):
        # bench.py deploy_status: yalnız etkin Release Pipeline'a bakar; pipeline yoksa boşta döner.
        if a["name"] not in self.pipelines:
            return ok({"is_validating": False, "is_deploy_in_progress": False, "candidate": None})
        return ok({"is_validating": True, "is_deploy_in_progress": True, "candidate": None})

    def m_press__api__bench__versions(self, a):
        return ok([{"name": b["name"], "status": b["status"]} for b in self.benches.values() if b["group"] == a["name"]])

    def m_press__api__bench__candidates(self, a):
        group = a["filters"]["group"]
        return ok([{"name": c["name"], "creation": c["creation"], "status": "Draft", "apps": [x["app"] for x in c["apps"]]}
                   for c in self.candidates.values() if c["group"] == group])

    def m_press__api__bench__candidate(self, a):
        builds = [b for b in self.builds.values() if b["deploy_candidate"] == a["name"]]
        if not builds:
            return frappe_error(500, "DoesNotExistError", "Deploy Candidate Build None not found")
        b = builds[-1]
        return ok({"name": a["name"], "status": b["status"], "creation": b["creation"], "build_steps": b["build_steps"],
                   "apps": self.candidates[a["name"]]["apps"], "jobs": []})

    def m_press__api__bench__jobs(self, a):
        group = a["filters"]["name"]
        benches = [b["name"] for b in self.benches.values() if b["group"] == group]
        return ok([self._job_public(j) for j in self.jobs.values() if j["bench"] in benches])

    def _job_public(self, j):
        return {k: j[k] for k in ("name", "job_type", "creation", "status", "start", "end", "duration")}

    def m_press__api__client__get(self, a):
        if a["doctype"] != "Deploy Candidate Build":
            return frappe_error(403, "PermissionError", "Not permitted")
        b = self.builds.get(a["name"])
        if b is None:
            return frappe_error(404, "DoesNotExistError", "not found")
        fields = ("name", "status", "creation", "deployed", "build_steps", "build_start", "build_end",
                  "build_duration", "build_error", "group", "retry_count", "team", "deploy_candidate")
        return ok({k: copy.deepcopy(b.get(k)) for k in fields})

    # Desk ----------------------------------------------------------------------------------------
    def m_frappe__client__get(self, a):
        # Bilerek gizli alanlarla döner; runtime bu ucu operator okumaları için çağırmamalı.
        doc = {"Deploy Candidate": self.candidates, "Agent Job": self.jobs}.get(a["doctype"], {}).get(a["name"])
        return ok(copy.deepcopy(doc)) if doc else frappe_error(404, "DoesNotExistError", "not found")

    def _table(self, doctype, parent):
        if doctype == "Release Group":
            return list(self.groups.values())
        if doctype == "Deploy Candidate":
            # update_deploy_candidate_with_build: Success olan son build platformuna göre intel_build/arm_build olur
            rows = []
            for c in self.candidates.values():
                done = [b for b in self.builds.values() if b["deploy_candidate"] == c["name"] and b["status"] == "Success"]
                pick = {p: [b["name"] for b in done if b.get("platform", "x86_64") == p] for p in ("x86_64", "arm64")}
                rows.append(dict(c, intel_build=(pick["x86_64"] or [None])[-1], arm_build=(pick["arm64"] or [None])[-1]))
            return rows
        if doctype == "Deploy Candidate App":
            return [dict(r, parent=c["name"], parenttype="Deploy Candidate", idx=i + 1)
                    for c in self.candidates.values() for i, r in enumerate(c["apps"])]
        if doctype == "Deploy Candidate Build":
            return [dict(b, platform=b.get("platform", "x86_64"),
                         docker_image=("registry.example.test/{}:{}".format(b["group"], b["name"])
                                       if b["status"] == "Success" else None)) for b in self.builds.values()]
        if doctype == "Release Group Server":
            return [{"server": srv, "parent": g, "parenttype": "Release Group", "idx": i + 1}
                    for g, servers in self.group_servers.items() for i, srv in enumerate(servers)]
        if doctype == "Deploy Candidate Build Step":
            return [dict(s, parent=b["name"], parenttype="Deploy Candidate Build", idx=i + 1)
                    for b in self.builds.values() for i, s in enumerate(b["build_steps"])]
        if doctype == "App Source":
            return list(self.sources.values())
        if doctype == "App Source Version":
            return [{"version": v, "parent": s["name"], "parenttype": "App Source", "idx": i + 1}
                    for s in self.sources.values() for i, v in enumerate(s["versions"])]
        if doctype == "Release Group App":
            return [dict(r, parent=g, parenttype="Release Group", idx=i + 1)
                    for g, rows in self.group_apps.items() for i, r in enumerate(rows)]
        if doctype == "Agent Job":
            return list(self.jobs.values())
        if doctype == "Agent Job Step":
            return [dict(s, agent_job=j["name"]) for j in self.jobs.values() for s in j["steps"]]
        if doctype == "Error Log":
            return self.error_logs
        if doctype == "Deploy":
            return list(self.deploys.values())
        if doctype == "Bench":
            return list(self.benches.values())
        if doctype == "Deploy Bench":
            return [dict(r, parent=d["name"], parenttype="Deploy", idx=i + 1)
                    for d in self.deploys.values() for i, r in enumerate(d.get("benches", []))]
        if doctype == "New Bench Queue":
            return list(self.queues.values())
        if doctype == "Resource Tag":
            return [{"parent": g, "parenttype": "Release Group", "tag_name": t}
                    for g, tags in self.group_tags.items() for t in tags]
        if doctype == "Site":
            return [dict(s, skip_auto_updates=s.get("skip_auto_updates", 0), fatal_site_update=s.get("fatal_site_update"),
                         only_update_at_specified_time=s.get("only_update_at_specified_time", 0))
                    for s in self.sites.values()]
        if doctype == "Server":
            return [{"name": "f1-app.example.test", "title": "app", "status": "Active", "cluster": "Default",
                     "team": "team-alpha", "platform": "x86_64"},
                    {"name": "f2-app.example.test", "title": "app2", "status": "Active", "cluster": "Default",
                     "team": "team-alpha", "platform": "x86_64"},
                    {"name": "f9-app.example.test", "title": "other", "status": "Active", "cluster": "Default",
                     "team": "team-beta", "platform": "arm64"}]
        return None

    def m_frappe__client__get_list(self, a):
        if self.principal != "operator":
            return frappe_error(403, "PermissionError", "Desk access requires a System User")
        rows = self._table(a["doctype"], a.get("parent"))
        if rows is None:
            return frappe_error(403, "PermissionError", "Not permitted: " + a["doctype"])
        filters = a.get("filters") or {}
        out = []
        for row in rows:
            match = True
            for key, cond in filters.items():
                value = row.get(key)
                if isinstance(cond, list) and len(cond) == 2 and cond[0] == "in":
                    match = match and value in cond[1]
                elif isinstance(cond, list) and len(cond) == 2 and cond[0] == "not in":
                    match = match and value not in cond[1]
                elif isinstance(cond, list) and len(cond) == 2 and cond[0] == "like":
                    match = match and cond[1].strip("%") in str(value or "")
                else:
                    match = match and value == cond
            if match:
                out.append({f: copy.deepcopy(row.get(f)) for f in a["fields"]})
        return ok(out[: a.get("limit_page_length", 20)])

    def m_run_doc_method(self, a):
        if self.principal != "operator":
            return frappe_error(403, "PermissionError", "Not permitted")
        dt, dn, method = a["dt"], a["dn"], a["method"]
        args = json.loads(a["args"]) if isinstance(a.get("args"), str) else (a.get("args") or {})
        if (dt, method) == ("Release Group", "create_deploy_candidate"):
            name = self.make_candidate(dn)
            doc = {k: v for k, v in self.candidates[name].items()}
            return ok(doc)
        if (dt, method) == ("Deploy Candidate", "build"):
            name = self.make_build(dn, "Pending")
            self.builds[name]["no_cache"] = args.get("no_cache", False)
            return ok({"error": False, "message": name})
        if (dt, method) == ("Deploy Candidate Build", "deploy"):
            build = self.builds[dn]
            name = self._id("dpl")
            rows = []
            pinned = self.candidate_build(build["deploy_candidate"])  # candidate.intel_build (x86_64 sunucular)
            for server in self.group_servers.get(build["group"], []):
                queue = self._id("nbq")
                self.queues[queue] = {"name": queue, "status": "Queued", "bench": None, "group": build["group"],
                                      "build": pinned}
                rows.append({"server": server, "bench": queue})
            self.deploys[name] = {"name": name, "group": build["group"], "candidate": build["deploy_candidate"],
                                  "creation": "now", "benches": rows}
            if self.auto_start_benches:
                for row in rows:
                    self.start_bench(name, row["server"])
            return ok({"error": False, "message": name})
        return frappe_error(403, "PermissionError", "Method not whitelisted: {}.{}".format(dt, method))

    def m_frappe__client__get_value(self, a):
        fields = a["fieldname"] if isinstance(a["fieldname"], list) else [a["fieldname"]]
        return ok({f: self.settings.get(f) for f in fields})

    def m_frappe__utils__change_log__get_versions(self, a):
        return ok({"frappe": {"title": "Frappe Framework", "version": "15.0.0"},
                   "press": {"title": "Press", "version": "0.7.0"}})

    # site -----------------------------------------------------------------------------------------
    def _site_or_403(self, name):
        site = self.sites.get(name)
        if site is None:
            return None, frappe_error(404, "DoesNotExistError", "Site not found")
        if self.principal == "team" and site["team"] != self.current:
            return None, frappe_error(403, "PermissionError", "Not Permitted")
        return site, None

    def m_press__api__site__get(self, a):
        site, err = self._site_or_403(a["name"])
        return err or ok({k: copy.deepcopy(v) for k, v in site.items() if k != "apps"})

    def m_press__api__site__installed_apps(self, a):
        site, err = self._site_or_403(a["name"])
        return err or ok([{"app": x, "title": x.title(), "branch": "version-16"} for x in site["apps"]])

    def m_press__api__site__available_apps(self, a):
        site, err = self._site_or_403(a["name"])
        if err:
            return err
        return ok([{"name": s["name"], "app": s["app"]} for s in self.sources.values() if s["app"] not in site["apps"]])

    def m_press__api__site__jobs(self, a):
        site = a["filters"]["site"]
        rows = [self._job_public(j) for j in reversed(list(self.jobs.values())) if j["site"] == site]
        for row in rows:
            if row["status"] == "Undelivered":
                row["status"] = "Pending"
        return ok(rows[: a.get("limit_page_length", 20)])

    def m_press__api__site__job(self, a):
        job = self.jobs.get(a["job"])
        if job is None:
            return frappe_error(404, "DoesNotExistError", "not found")
        out = self._job_public(job)
        out["steps"] = job["steps"]
        return ok(out)

    def m_press__api__site__running_jobs(self, a):
        return ok([self._job_public(j) for j in self.jobs.values()
                   if j["site"] == a["name"] and j["status"] in ("Pending", "Running")])

    def m_press__api__site__backups(self, a):
        return ok(copy.deepcopy(self.backups.get(a["name"], [])))

    def m_press__api__site__backup(self, a):
        site, err = self._site_or_403(a["name"])
        if err:
            return err
        self.add_job("Backup Site", "Pending", site=a["name"])
        return ok(None)

    def m_press__api__site__migrate(self, a):
        site, err = self._site_or_403(a["name"])
        if err:
            return err
        self.add_job("Migrate Site", "Pending", site=a["name"])
        site["status"] = "Pending"
        return ok(None)

    def m_press__api__site__install_app(self, a):
        site, err = self._site_or_403(a["name"])
        if err:
            return err
        if a["app"] in site["apps"]:
            return ok(None)  # Site.install_app iş açmadan döner
        if a.get("plan"):
            self.subscriptions.append((a["name"], a["app"], a["plan"]))
        self.add_job("Install App on Site", "Pending", site=a["name"])
        return ok(None)

    def m_press__api__site__get_new_site_options(self, a):
        return ok({"versions": [{"name": "Version 16", "group": {"name": a.get("group")}}]})

    def m_press__api__server__all(self, a):
        return ok([{"name": "f1-app.example.test", "title": "app", "status": "Active", "app_server": "f1"}])

    def m_press__api__server__get(self, a):
        return ok({"name": a["name"], "title": "app", "status": "Active", "team": "team-alpha", "app_server": "f1",
                   "region_info": {"name": "Default"}})


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # sessiz
        pass

    def _respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method, args):
        try:
            status, payload = self.server.fake.handle(method, args, self.headers)
        except Exception as error:  # noqa: BLE001
            status, payload = frappe_error(500, "Exception", "fake press crashed: {}".format(error))
        self._respond(status, payload)

    def do_POST(self):
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        args = json.loads(self.rfile.read(length) or b"{}")
        if parts.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._dispatch(parts.path[len("/api/method/"):], args)

    def do_GET(self):
        parts = urlsplit(self.path)
        args = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self._dispatch(parts.path[len("/api/method/"):], args)


class FakePressServer:
    def __init__(self, fake):
        self.fake = fake
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.fake = fake
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:{}".format(self.httpd.server_address[1])

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
