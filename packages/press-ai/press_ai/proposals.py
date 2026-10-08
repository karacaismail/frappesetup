"""Öneri, insan onayı, tek kullanım, uçuştaki yürütme kilidi ve sonuç kaydı.

Akış: araç bir öneri yazar (yürütmez) → insan ayrı terminalde `server.py approve <id>` ile kesin özeti
yazarak onaylar → araç onayı, özeti, süreyi ve tek kullanımı doğrular, aynı (işlem, hedef) için kilidi alır,
istek göndermeden önce `unknown/dispatching` sonucunu kalıcı yazar ve isteği bir kez gönderir.

Sınır: onay sunucuyla aynı OS kullanıcısıyla yazılır. MCP üzerinden onay yazan araç yoktur; ama aynı hesapta
shell erişimi olan bir süreç onay CLI'sini çalıştırabilir veya durum dizinini düzenleyebilir. Bu düzen bir hız
kesicidir, OS veya kriptografik güvenlik sınırı değildir. Ayrı onay hesabı desteklenmez (yapılandırmada reddedilir).
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import json
import os
import re
import stat
import uuid

from .errors import ApprovalError, KitError
from .util import canonical_json, ensure_private_dir, iso, parse_iso, sha256_hex, utc_now, write_private_file

_ID = re.compile(r"p-[0-9a-f]{20}")
_MAX_RECORD = 1024 * 1024  # 200 KiB içerik tek kez saklanır; JSON kaçışları için pay
_SIGNED_FIELDS = ("id", "kind", "operation", "created_at", "expires_at", "authority", "target", "params", "request",
                  "preview", "approval_level", "confirm_phrase")
_OPEN_STATES = ("accepted", "in_progress", "unknown")


def _check_id(proposal_id) -> str:
    if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
        raise ApprovalError("Invalid proposal id", code="invalid_proposal_id")
    return proposal_id


def digest_of(record: dict) -> str:
    return sha256_hex(canonical_json({key: record.get(key) for key in _SIGNED_FIELDS}))


class ProposalStore:
    def __init__(self, approval_config, clock=utc_now, redactor=None):
        self.config = approval_config
        self.root = approval_config.state_dir
        self.clock = clock
        self.redactor = redactor

    # -- dizinler ---------------------------------------------------------------------------------
    def _dir(self, name: str) -> str:
        ensure_private_dir(self.root)
        path = os.path.join(self.root, name)
        ensure_private_dir(path)
        return path

    def _path(self, name: str, proposal_id: str) -> str:
        return os.path.join(self._dir(name), _check_id(proposal_id) + ".json")

    def _read(self, path: str) -> dict | None:
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ApprovalError("State file is not a regular file: " + os.path.basename(path), code="state_tampered")
        if info.st_uid != os.getuid():
            raise ApprovalError("State file has an unexpected owner: " + os.path.basename(path), code="state_tampered")
        if info.st_size > _MAX_RECORD:
            raise ApprovalError("State file is too large", code="state_tampered")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            try:
                return json.loads(handle.read())
            except ValueError:
                raise ApprovalError("State file is not valid JSON: " + os.path.basename(path),
                                    code="state_tampered") from None

    # -- öneri ------------------------------------------------------------------------------------
    def create(self, kind: str, operation: str, authority: dict, target: str, params: dict, request: dict,
               preview: dict, approval_level: str, confirm_phrase: str | None = None) -> dict:
        if approval_level not in ("single", "double"):
            raise KitError("approval level must be single or double")
        if approval_level == "double" and not confirm_phrase:
            raise KitError("double approval needs a confirm phrase")
        now = self.clock()
        record = {
            "id": "p-" + uuid.uuid4().hex[:20],
            "kind": kind,
            "operation": operation,
            "created_at": iso(now),
            "expires_at": iso(now + _dt.timedelta(seconds=self.config.proposal_ttl)),
            "authority": authority,
            "target": target,
            "params": params,
            "request": request,
            "preview": preview,
            "approval_level": approval_level,
            "confirm_phrase": confirm_phrase,
        }
        record["digest"] = digest_of(record)
        data = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        if len(data) > _MAX_RECORD:
            raise KitError("Proposal is too large to review; narrow the change", code="proposal_too_large")
        write_private_file(self._path("proposals", record["id"]), data, exclusive=True)
        self.audit({"event": "proposal_created", "proposal_id": record["id"], "operation": operation,
                    "target": target, "kind": kind})
        return record

    def load(self, proposal_id: str) -> dict:
        record = self._read(self._path("proposals", proposal_id))
        if record is None:
            raise ApprovalError("Proposal not found", code="proposal_not_found")
        if record.get("digest") != digest_of(record) or record.get("id") != proposal_id:
            raise ApprovalError("Proposal content does not match its digest", code="state_tampered")
        return record

    # -- orijinal core uyarısı ---------------------------------------------------------------------
    def core_gate(self, request_digest: str, summary: dict) -> dict | None:
        """Orijinal core değişikliğinin ilk isteği tek kullanımlık bir uyarı kaydı yazar ve onu döndürür; öneri
        oluşmaz. Aynı istek (aynı özet) uyarı süresi içinde yeniden gelirse kayıt tüketilir ve None döner: öneri CORE
        onayıyla oluşturulabilir. Bu bir onay değildir; onay yine ayrı terminalde insanla yazılır."""
        if not isinstance(request_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", request_digest):
            raise KitError("invalid request digest")
        path = os.path.join(self._dir("core_warnings"), request_digest + ".json")
        now = self.clock()
        existing = self._read(path)
        if existing is not None:
            try:
                os.unlink(path)  # tek kullanım; yarışta ikinci istek yeni bir uyarı alır
                live = existing.get("request_digest") == request_digest and parse_iso(existing["expires_at"]) > now
            except FileNotFoundError:
                live = False
            except (KeyError, TypeError, ValueError):
                live = False
            if live:
                self.audit({"event": "core_warning_repeated", "request_digest": request_digest})
                return None
        record = {"request_digest": request_digest, "created_at": iso(now),
                  "expires_at": iso(now + _dt.timedelta(seconds=self.config.proposal_ttl)), "summary": summary}
        try:
            write_private_file(path, canonical_json(record), exclusive=True)
        except FileExistsError:
            return self._read(path) or record  # aynı anda gelen eş istek uyarıyı yazdı
        self.audit({"event": "core_warning_issued", "request_digest": request_digest,
                    "apps": summary.get("apps"), "files": summary.get("files")})
        return record

    def _approval(self, proposal_id: str) -> dict | None:
        return self._read(self._path("approvals", proposal_id))

    def status(self, proposal_id: str) -> dict:
        record = self.load(proposal_id)
        now = self.clock()
        consumed = self._read(self._path("consumed", proposal_id))
        rejected = self._read(self._path("rejections", proposal_id))
        approval = self._approval(proposal_id)
        if consumed:
            state = "consumed"
        elif rejected:
            state = "rejected"
        elif approval and approval.get("digest") == record["digest"]:
            state = "expired" if now > parse_iso(approval["expires_at"]) else "approved"
        elif now > parse_iso(record["expires_at"]):
            state = "expired"
        else:
            state = "pending"
        result = {"proposal_id": proposal_id, "state": state, "operation": record["operation"],
                  "target": record["target"], "kind": record["kind"], "approval_level": record["approval_level"],
                  "digest12": record["digest"][:12], "created_at": record["created_at"],
                  "expires_at": record["expires_at"], "outcome": self.outcome(proposal_id)}
        if approval:
            result["approved_at"] = approval.get("approved_at")
            result["approval_expires_at"] = approval.get("expires_at")
        if state == "pending":
            result["human_approval_command"] = approval_command(proposal_id)
        return result

    def require_approved(self, proposal_id: str, kind: str) -> dict:
        """Yürütmeden hemen önce: onaylı, süresi dolmamış, tüketilmemiş ve özeti eşleşen öneriyi döndürür."""
        record = self.load(proposal_id)
        if record["kind"] != kind:
            raise ApprovalError("Proposal belongs to a different tool", code="wrong_proposal_kind")
        if self._read(self._path("consumed", proposal_id)):
            raise ApprovalError("Proposal was already executed; create a new proposal", code="already_consumed")
        if self._read(self._path("rejections", proposal_id)):
            raise ApprovalError("Proposal was rejected by a human", code="rejected")
        approval = self._approval(proposal_id)
        if approval is None:
            raise ApprovalError("No human approval yet. A human must run: " + approval_command(proposal_id),
                                details={"human_approval_command": approval_command(proposal_id)})
        if approval.get("proposal_id") != proposal_id or approval.get("digest") != record["digest"]:
            raise ApprovalError("Approval does not match this exact proposal", code="approval_mismatch")
        if approval.get("level") != record["approval_level"]:
            raise ApprovalError("Approval level does not match", code="approval_mismatch")
        now = self.clock()
        if now > parse_iso(approval["expires_at"]) or now > parse_iso(record["expires_at"]):
            raise ApprovalError("Approval or proposal expired; create a new proposal", code="approval_expired")
        return record

    def consume(self, proposal_id: str) -> None:
        """Yürütme öncesi tek kullanım işareti (O_EXCL); ikinci çağrı reddedilir."""
        path = self._path("consumed", proposal_id)
        try:
            write_private_file(path, canonical_json({"consumed_at": iso(self.clock()), "pid": os.getpid()}),
                               exclusive=True)
        except FileExistsError:
            raise ApprovalError("Proposal was already executed; create a new proposal", code="already_consumed")
        self.audit({"event": "proposal_consumed", "proposal_id": proposal_id})

    # -- uçuştaki yürütme kilidi ------------------------------------------------------------------
    def acquire_target_lock(self, operation: str, target: str, proposal_id: str) -> int:
        """Aynı (işlem, hedef) için tek yürütme: açık tutulan kilit dosyasında `flock(LOCK_EX | LOCK_NB)`.
        Kilit süreç ölünce işletim sistemi tarafından bırakılır; dosya silinerek kilit bozulmaz ve PID'e dayanılmaz.
        Dönen tanıtıcı `release_target_lock`'a verilir."""
        name = sha256_hex((operation + "\x00" + target).encode("utf-8"))[:32] + ".lock"
        path = os.path.join(self._dir("locks"), name)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ApprovalError("Lock file is not a private regular file", code="state_tampered")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, PermissionError):
                raise ApprovalError("Another execution for {} on {} is in flight".format(operation, target),
                                    code="in_flight") from None
            os.ftruncate(fd, 0)
            os.write(fd, canonical_json({"proposal_id": proposal_id, "operation": operation, "target": target,
                                         "pid": os.getpid(), "at": iso(self.clock())}))
            return fd
        except BaseException:
            os.close(fd)
            raise

    def release_target_lock(self, handle: int) -> None:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)

    # -- sonuç ------------------------------------------------------------------------------------
    def record_outcome(self, proposal_id: str, outcome: dict) -> dict:
        record = self.load(proposal_id)
        outcome = dict(outcome)
        outcome.update({"proposal_id": proposal_id, "operation": record["operation"], "target": record["target"],
                        "recorded_at": iso(self.clock())})
        path = self._path("outcomes", proposal_id)
        temp = path + ".tmp-" + uuid.uuid4().hex[:8]
        write_private_file(temp, json.dumps(outcome, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        os.replace(temp, path)
        self.audit({"event": "outcome", "proposal_id": proposal_id, "state": outcome.get("state")})
        return outcome

    def outcome(self, proposal_id: str) -> dict | None:
        """Kayıtlı sonuç; tüketilmiş ama sonucu yazılmamış öneri `unknown` sayılır (süreç yarıda ölmüş olabilir)."""
        recorded = self._read(self._path("outcomes", proposal_id))
        if recorded is None and self._read(self._path("consumed", proposal_id)):
            record = self.load(proposal_id)
            return {"proposal_id": proposal_id, "operation": record["operation"], "target": record["target"],
                    "state": "unknown", "phase": "consumed_without_outcome",
                    "meaning": "The proposal was consumed but no outcome was recorded; a human must inspect Press."}
        return recorded

    def unresolved(self, operation: str, target: str) -> list:
        """Aynı işlem ve hedef için sonucu bilinmeyen veya sürmekte olan yürütmeler (kör tekrarı engeller)."""
        found = []
        seen = set()
        for directory in ("outcomes", "consumed"):
            path = self._dir(directory)
            for name in sorted(os.listdir(path)):
                if not name.endswith(".json") or not _ID.fullmatch(name[:-5]) or name[:-5] in seen:
                    continue
                seen.add(name[:-5])
                outcome = self.outcome(name[:-5])
                if (outcome and outcome.get("operation") == operation and outcome.get("target") == target
                        and outcome.get("state") in _OPEN_STATES and not outcome.get("resolved_by_human")):
                    found.append({"proposal_id": outcome["proposal_id"], "state": outcome["state"],
                                  "phase": outcome.get("phase"), "recorded_at": outcome.get("recorded_at")})
        return found

    def list(self) -> list:
        directory = self._dir("proposals")
        items = []
        for name in sorted(os.listdir(directory)):
            if name.endswith(".json") and _ID.fullmatch(name[:-5]):
                try:
                    items.append(self.status(name[:-5]))
                except ApprovalError as error:
                    items.append({"proposal_id": name[:-5], "state": "invalid", "problem": str(error)})
        return items

    # -- insan tarafı (CLI) -----------------------------------------------------------------------
    def write_approval(self, proposal_id: str, record: dict) -> dict:
        now = self.clock()
        if now > parse_iso(record["expires_at"]):
            raise ApprovalError("Proposal expired before approval; create a new proposal", code="approval_expired")
        expires = min(now + _dt.timedelta(seconds=self.config.approval_ttl), parse_iso(record["expires_at"]))
        approval = {
            "proposal_id": proposal_id,
            "digest": record["digest"],
            "level": record["approval_level"],
            "approved_at": iso(now),
            "expires_at": iso(expires),
            "approver_uid": os.getuid(),
        }
        write_private_file(self._path("approvals", proposal_id), canonical_json(approval), exclusive=True)
        self.audit({"event": "approved", "proposal_id": proposal_id})
        return approval

    def write_rejection(self, proposal_id: str, reason: str) -> None:
        self.load(proposal_id)
        write_private_file(self._path("rejections", proposal_id),
                           canonical_json({"rejected_at": iso(self.clock()), "reason": reason[:500]}), exclusive=True)
        self.audit({"event": "rejected", "proposal_id": proposal_id})

    def resolve_outcome(self, proposal_id: str, note: str) -> dict:
        outcome = dict(self.outcome(proposal_id) or {})
        outcome["resolved_by_human"] = {"at": iso(self.clock()), "note": note[:500]}
        return self.record_outcome(proposal_id, outcome)

    # -- denetim ----------------------------------------------------------------------------------
    def audit(self, event: dict) -> None:
        try:
            ensure_private_dir(self.root)
            event = dict(event, at=iso(self.clock()))
            if self.redactor:
                event = self.redactor.value(event)
            path = os.path.join(self.root, "audit.jsonl")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "ab") as handle:
                handle.write(canonical_json(event) + b"\n")
        except OSError:
            # Denetim kaydı yazılamazsa işlem durmaz; sonuç kaydı ayrıca tutulur.
            pass


def approval_command(proposal_id: str) -> str:
    return "python3 -I packages/press-ai/server.py approve {} --config <config.json>".format(proposal_id)
