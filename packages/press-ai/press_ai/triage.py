"""Deploy Candidate Build teşhisi: ilk Failure adımı + kılavuzdaki gerçek olaylardan türetilen sınıflar.

Kurallar pressguide@2b83441 adımlarına dayanır (adım kimlikleri `guide_steps` alanında). Bir kalıp
eşleşmesi kesin neden değildir: sınıf `pattern` güveniyle döner ve sonraki adım kanıtı doğrulamaktır.
Eşleşme yoksa `unclassified` döner; teşhis uydurulmaz.
"""
from __future__ import annotations

import re

from .redaction import truncate

INTERMEDIATE = ("Draft", "Scheduled", "Pending", "Preparing", "Running")
TERMINAL_SUCCESS = ("Success",)
TERMINAL_FAILURE = ("Failure",)

_ALWAYS = [
    "Pending satırları ayrı hata değildir; yalnız ilk Failure satırı ve çıktısı neden kanıtıdır.",
    "Boş Error Log veya Agent Job filtresi 'hata yok' demek değildir; filtreyi build kimliği ve zamanla doğrula.",
    "Sonuç ve neden görülmeden yeni build açma; aynı candidate için tek build ile doğrula.",
]

# (sınıf, eşleşme işlevi, açıklama, sonraki adımlar, sahip, kılavuz adımları)
_RULES = [
    ("required_app_not_found",
     lambda step, out: re.search(r"required app.{0,80}not (found|installed)|app .{0,60} not found|"
                                 r"no module named ['\"]?[a-z_]+['\"]?", out, re.I),
     "Bağımlı uygulama grupta yok veya App/Source kimliği yanlış (ör. education için ERPNext eksik, "
     "educator gibi yanlış App adı).",
     ["`release_group.get` ile Apps sırasını ve her satırın Source kaydını oku.",
      "Uygulamanın release commit'indeki hooks.py `required_apps` değerini kontrol et.",
      "Eksik bağımlılığı `release_group.add_app` önerisiyle, bağımlı uygulamadan önce ekle; sonra yeni candidate."],
     "operator", ["live-error", "live-apps", "identity-error", "live-failure"]),
    ("npm_range_parse",
     lambda step, out: re.search(r"invalid simple block|npmspec|simplespec", out, re.I),
     "Press'in ön-build doğrulaması bir npm sürüm aralığını (ör. '^20.19.0 || >=22.12.0') Python "
     "SimpleSpec ile ayrıştıramıyor; sorun uygulama/kaynak değil, Press doğrulama kodu.",
     ["App/Source ekleyerek çözmeye çalışma.",
      "Press doğrulama kodu düzeltmesi geliştirici incelemesi ve regresyon testiyle yapılır (`press.code_fix`).",
      "Düzeltmeden sonra aynı candidate için tek build başlat; Pre-build Success tüm build'in başarısı değildir."],
     "app_developer", ["live-npm-range-validation"]),
    ("disk_full",
     lambda step, out: re.search(r"no space left on device|enospc|disk quota exceeded", out, re.I),
     "Build veya agent sunucusunda disk/inode dolu.",
     ["Sunucu ölçümleri (df -h, df -i, docker system df) altyapı sahibine devredilir (`server.disk_check`).",
      "Temizlik yalnız açık onayla ve yalnız kullanılmayan build cache için yapılır (`server.build_cache_cleanup`).",
      "Site, image, container, backup, Redis ve veritabanı silinmez."],
     "infrastructure_owner", ["live-redis-enospc", "hata-tanisi", "live-cleanup-crm"]),
    ("upload_context_http_error",
     lambda step, out: ("upload" in step and ("context" in step or "build context" in step)
                        and re.search(r"\b50[0-4]\b|internal server error|bad gateway", out, re.I)),
     "Build context yüklemesi agent tarafında HTTP 5xx ile reddedildi. Kılavuzdaki olayda neden, Nginx'in "
     "geçici istek gövdesi dosyası için disk alanı kalmamasıydı.",
     ["Build'in Error Log kaydında yöntem, yol ve HTTP yanıtını oku (`error_log.list`, operator).",
      "Nginx error.log satırlarını build kimliği ve /agent/builder/upload ile eşleştir; UTC ile TSİ (+3) farkına dikkat.",
      "Disk ölçümleri ve temizlik altyapı sahibinde (`server.disk_check`); Ping Agent yanıtı upload uç noktasını doğrulamaz."],
     "infrastructure_owner", ["live-upload-row", "live-agent-http500", "hata-tanisi"]),
    ("docker_image_push_failed",
     lambda step, out: (("upload" in step or "push" in step) and ("image" in step or "docker" in step)
                        and re.search(r"repository.{0,80}(does not exist|not found)|repositorynotfound|"
                                      r"name unknown|denied|unauthorized", out, re.I)),
     "Docker image registry'ye gönderilemedi; kılavuzdaki olayda hedef ECR deposu yoktu.",
     ["Upload Docker Image çıktısının son satırını oku; Agent Job Success değeri image push başarısı değildir.",
      "Registry hesabı, bölge ve depo adı eşleşmesini altyapı sahibi doğrular (`registry.repository_check`); secret yazdırılmaz.",
      "Depo yalnız gerçekten yoksa oluşturulur; sonra normal cache ile tek yeni build."],
     "infrastructure_owner", ["live-ecr-push-failure", "live-prebuild-upload-success"]),
    ("clone_failed",
     lambda step, out: ("clone" in step and re.search(r"repository not found|could not read|remote branch .{0,60} not found|"
                                                       r"authentication failed|fatal:", out, re.I)),
     "Uygulama deposu veya dalı build sunucusundan alınamadı.",
     ["App Source'un repository ve branch alanlarını kontrol et (`app_source.branches`).",
      "Dalın gerçekten var olduğunu ve Frappe sürümünü desteklediğini doğrula; hareketli dal tek başına uyum garantisi değildir."],
     "operator", ["branch", "source-form"]),
    ("runtime_incompatible",
     lambda step, out: re.search(r"requires-python|requires a different python|no matching distribution|"
                                 r"resolutionimpossible|unsupported engine|engines\b", out, re.I),
     "Release commit'inin Python/Node gereksinimi grubun runtime'ıyla uyumsuz.",
     ["Candidate release commit'lerindeki pyproject.toml ve package.json gereksinimlerini grup runtime'ıyla karşılaştır "
      "(`release_group.dependencies`).",
      "Uyumsuz uygulamanın uygun dalını veya release'ini seç; branch ucundan değil release commit'inden oku."],
     "operator", ["live-runtime", "live-candidate-content", "live-candidate-two"]),
]


def _ordered(steps: list) -> list:
    if steps and all(isinstance(s, dict) and isinstance(s.get("idx"), int) for s in steps):
        return sorted(steps, key=lambda s: s["idx"])
    return [s for s in steps if isinstance(s, dict)]


def _label(step: dict) -> str:
    parts = [step.get(k) for k in ("stage", "step", "stage_slug", "step_slug", "title", "name")]
    return " ".join(str(p) for p in parts if p).lower().replace("_", " ")


def classify(build: dict, redactor=None) -> dict:
    """`build`: {status, build_steps[]} (Deploy Candidate Build ya da candidate okumasından)."""
    status = build.get("status")
    steps = _ordered(build.get("build_steps") or [])
    summary = {"build": build.get("name"), "status": status, "steps_total": len(steps),
               "steps_by_status": {}}
    for step in steps:
        key = step.get("status") or "Unknown"
        summary["steps_by_status"][key] = summary["steps_by_status"].get(key, 0) + 1
    if status in INTERMEDIATE:
        return dict(summary, state="in_progress", classification="build_in_progress",
                    explanation="Build henüz bitmedi. Preparing/Pending/Running başarı da hata da değildir.",
                    next_steps=["Durumu yeniden oku (`build.get`); yeni build veya deploy başlatma."],
                    owner=None, guide_steps=["preparing", "live-build-start"], always=_ALWAYS)
    if status in TERMINAL_SUCCESS:
        not_success = [s for s in steps if s.get("status") != "Success"]
        if steps and not not_success:
            return dict(summary, state="succeeded", classification="build_succeeded",
                        explanation="Build Success ve tüm adımlar (Upload Docker Image dahil) Success.",
                        next_steps=["Deploy ayrı bir işlemdir: `deploy.start` önerisi, insan onayı, sonra Bench Active ve "
                                    "New Bench Agent Job ayrı doğrulanır."],
                        owner="operator", guide_steps=["live-build-success", "live-bench-active"], always=_ALWAYS)
        return dict(summary, state="unknown", classification="status_steps_inconsistent",
                    explanation="Durum Success ama adımların bir kısmı Success değil ya da adım listesi boş; "
                                "etiket tek başına başarı kanıtı değildir.",
                    next_steps=["Build kaydını ve adımları yeniden oku; registry'de image varlığını altyapı sahibiyle doğrula."],
                    owner="operator", guide_steps=["live-build-success"], always=_ALWAYS)
    if status not in TERMINAL_FAILURE:
        return dict(summary, state="unknown", classification="unknown_status",
                    explanation="Tanınmayan build durumu: {!r}.".format(status), next_steps=["Build kaydını Desk'te aç."],
                    owner="operator", guide_steps=[], always=_ALWAYS)
    first = None
    for index, step in enumerate(steps):
        if step.get("status") == "Failure":
            first = (index, step)
            break
    if first is None:
        error_text = str(build.get("build_error") or "")
        return dict(summary, state="failed", classification="failure_without_failed_step",
                    explanation="Build Failure ama Failure durumlu adım yok (ör. elle durdurma veya agent hatası).",
                    build_error_tail=_tail(error_text, redactor),
                    next_steps=["Build'in Error Log ve Agent Job kayıtlarını build kimliğiyle oku."],
                    owner="operator", guide_steps=["hata-tanisi"], always=_ALWAYS)
    index, step = first
    label = _label(step)
    output = str(step.get("output") or "")
    tail = output[-6000:]
    pending_after = sum(1 for s in steps[index + 1:] if s.get("status") in ("Pending", None, ""))
    base = dict(summary, state="failed",
                first_failure={"position": index + 1, "stage": step.get("stage"), "step": step.get("step"),
                               "stage_slug": step.get("stage_slug"), "step_slug": step.get("step_slug"),
                               "output_tail": _tail(output, redactor)},
                pending_after_first_failure=pending_after)
    for name, matcher, explanation, next_steps, owner, guide in _RULES:
        if matcher(label, tail):
            return dict(base, classification=name, confidence="pattern", explanation=explanation,
                        next_steps=next_steps, owner=owner, guide_steps=guide, always=_ALWAYS)
    return dict(base, classification="unclassified", confidence="none",
                explanation="İlk Failure adımı bilinen bir kılavuz olayıyla eşleşmedi.",
                next_steps=["İlk Failure satırının çıktısını tümüyle oku, ardından build'in Error Log kaydını aç.",
                            "Neden belirlenmeden yeni build açma."],
                owner="operator", guide_steps=["hata-tanisi"], always=_ALWAYS)


def _tail(text: str, redactor) -> str:
    text, _ = truncate(text, 1500)
    return redactor.text(text) if redactor else text
