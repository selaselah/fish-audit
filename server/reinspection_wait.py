"""Reconstruct an express wait between a completed repair and the start of reinspection."""

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta

import trial_run
from delegation import is_page_marker


LEGACY = "contract-reinspection-wait-v1"
FORMAT = "contract-reinspection-wait-v2"
SINCE = "2026.11.26.08"
LOG_SINCE = "2026.11.26.09"
HEADINGS = {"整改复验条件", "复验间隔", "最低复验间隔", "复验前提", "复验时间要求", "复验条件", "试运行要求"}
HINT = re.compile(r"复验.{0,28}(?:间隔|小时|试运行)|(?:间隔|小时|试运行).{0,28}复验|等待期")
MINIMUM = re.compile(
    r"整改完成后(?:至少间隔|最少间隔|须间隔不少于|须满)\s*([1-9][0-9]{0,4})\s*小时(?:方可|才能)开始复验"
)
RUN = re.compile(r"整改完成后须连续试运行\s*([1-9][0-9]{0,4})\s*小时无异常(?:方可|才能)开始复验")
LABELS = {
    "fixed_day": {"整改完成日期"},
    "fixed_time": {"整改完成时刻", "实际整改完成时间"},
    "started": {"复验开始日期", "复验开始时刻", "复验开始时间", "实际复验开始时间"},
    "report_day": {"复验日期", "验收日期", "验收时间", "复验时间"},
}
DATE = re.compile(
    r"([0-9]{4})(?:-([0-9]{1,2})-([0-9]{1,2})|年([0-9]{1,2})月([0-9]{1,2})日)"
    r"(?:[ T]([0-9]{1,2}):([0-9]{2})(?::([0-9]{2}))?)?"
)
CONTRACT_FIELDS = {
    "contract",
    "contract_id",
    "buyer",
    "seller",
    "subject",
    "total",
    "currency",
    "unit",
    "signed_on",
    "effect_on",
    "valid_until",
    "effect_clause",
    "contract_state",
    "buyer_signature",
    "seller_signature",
    "quantity_agreed",
    "acceptance_criteria",
    "payment_term",
    "payment_stage",
}


def parts(raw):
    label, _, body = unicodedata.normalize("NFKC", raw).strip().partition(":")
    return label.strip(), body.strip().rstrip("。")


def stamp(value):
    match = DATE.fullmatch(value)
    if not match:
        return None
    year, month, day, cn_month, cn_day, hour, minute, second = match.groups()
    try:
        at = datetime(
            int(year),
            int(month or cn_month),
            int(day or cn_day),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
        )
        precision = 1 if second is not None else 60 if hour is not None else 86400
        end = at + timedelta(seconds=precision)
    except (ValueError, OverflowError):
        return None
    return {
        "from": at.isoformat(),
        "before": end.isoformat(),
        "precision": {1: "second", 60: "minute", 86400: "day"}[precision],
    }


def classify(role, quote):
    label, body = parts(quote)
    if role in ("contract", "contract_addendum"):
        if label not in HEADINGS and not HINT.search(quote):
            return None
        for kind, pattern in (("minimum", MINIMUM), ("operation", RUN)):
            match = pattern.fullmatch(body)
            if label in HEADINGS and match:
                return {"kind": kind, "hours": int(match[1])}
        return {"kind": "term_unclear"}
    fields = ("fixed_day", "fixed_time") if role == "remediation" else ("started", "report_day")
    for kind in fields:
        if label in LABELS[kind]:
            value = stamp(body)
            if value and kind == "fixed_time" and value["precision"] == "day":
                value = None
            return {"kind": kind, "stamp": value}
    return None


def standard_contract_line(raw, facts):
    from graph import LABELS as fields, PRINTED_TITLES
    from performance import STAGE_PREFIX

    label, body = parts(raw)
    for fact in facts:
        key = fact["field"]
        if (
            key not in CONTRACT_FIELDS
            or fact["status"] not in ("anchored", "confirmed")
            or unicodedata.normalize("NFKC", fact["quote"]) != unicodedata.normalize("NFKC", raw)
        ):
            continue
        if key == "contract" and PRINTED_TITLES.get(raw.strip()) == "contract":
            return True
        value = unicodedata.normalize("NFKC", fact["value"]).strip().rstrip("。")
        if (
            body
            and value in (body, unicodedata.normalize("NFKC", raw).strip().rstrip("。"))
            and (label in fields.get(key, ()) or key == "payment_stage" and STAGE_PREFIX.match(label + ":"))
        ):
            return True
    return False


def sources(graph, read_text, version=FORMAT):
    roles = {
        unit: kind
        for kind in ("contract", "contract_addendum", "remediation", "reinspection")
        for unit in graph["documents_by_kind"].get(kind, [])
    }
    receipts = set(graph["documents_by_kind"].get("acceptance", []))
    facts = defaultdict(list)
    for f in graph["facts"]:
        facts[f["doc"], f["page"]].append(f)
        unit = f.get("unit", f["doc"])
        if unit in receipts and f["field"] in ("original_acceptance", "repair_number", "defect_closure"):
            roles[unit] = "reinspection"
    empty = {"format": version, "pages": [], "lines": []}
    if not {"remediation", "reinspection"}.intersection(roles.values()):
        return empty
    if version == FORMAT:
        for unit in receipts:
            roles.setdefault(unit, "original")
    sections = {(d["source"], d["page"]): d["id"] for d in graph.get("audit_documents", []) if "source" in d}
    docs = {d["id"]: d for d in graph["documents"]}
    pages, lines, extra, operating = [], [], [], []
    for page in graph["nodes"]:
        if page["type"] != "page":
            continue
        doc, suffix = page["id"].rsplit("/p", 1)
        number = int(suffix)
        unit = sections.get((doc, number), doc)
        role = roles.get(unit)
        if not role:
            continue
        native = page.get("layer") == "text"
        where = {"doc": doc, "unit": unit, "page": number, "role": role}
        pages.append({**where, "native": native, "text_only": page.get("clause_text_only") is True})
        physical = []
        if native:
            text = read_text(doc, number)
            if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != page.get(
                "text_sha256"
            ):
                raise ValueError("合同复验间隔所据原页文字摘要不符")
            physical = text.splitlines()
        located = defaultdict(list)

        def observe(raw, line, observations):
            if is_page_marker(raw):
                return
            detail = classify(role, raw) if role != "original" else None
            target = lines
            if not detail:
                if role == "contract" and not standard_contract_line(raw, observations):
                    detail, target = {"kind": "qualification"}, extra
                elif version == FORMAT:
                    detail, target = trial_run.classify(role, *parts(raw)), operating
                if not detail:
                    return
            refs = [f["id"] for f in observations]
            address = f"{page['id']}/l{line}" if line else refs[0]
            entry = {
                **where,
                "id": "retest-time/" + address,
                "line": line,
                "quote": raw,
                "facts": refs,
                "source_sha256": docs[doc]["sha256"],
                "page_sha256": page["sha256"],
                "supported": bool(
                    line
                    and page.get("clause_text_only") is True
                    and all(f["status"] != "disputed" for f in observations)
                ),
                **detail,
            }
            target.append(entry)

        for f in facts[doc, number]:
            loc = f.get("source_line") or {}
            n = loc.get("number")
            if (
                native
                and loc.get("rects")
                and n
                and 0 < n <= len(physical)
                and loc["text"] == physical[n - 1]
            ):
                located[n].append(f)
                if (
                    unicodedata.normalize("NFKC", f["quote"])
                    == unicodedata.normalize("NFKC", physical[n - 1])
                    or version == FORMAT
                    and trial_run.same_printed_subject(f, physical[n - 1])
                ):
                    continue
            if f["quote"] not in physical or f["status"] == "disputed":
                observe(f["quote"], None, [f])
        for i, raw in enumerate(physical, 1):
            observe(raw, i, located[i])
    opaque = any(
        p["role"] in ("contract", "contract_addendum") and not (p["native"] and p["text_only"]) for p in pages
    )
    if not opaque and not any(r["kind"] in ("minimum", "operation", "term_unclear") for r in lines):
        return empty
    operation = any(r["kind"] == "operation" for r in lines)
    return {
        "format": version,
        "pages": [p for p in pages if operation or p["role"] != "original"],
        "lines": [*lines, *extra, *(operating if operation else [])],
    }


def source_graph(ledger):
    nodes, edges = [], []
    for r in ledger["lines"]:
        page = f"{r['doc']}/p{r['page']}"
        nodes.append(
            {
                "id": r["id"],
                "type": "reinspection_time_line",
                "label": r["quote"],
                "doc": r["doc"],
                "page": r["page"],
                "line": r["line"],
            }
        )
        edges.append(
            {"from": page, "to": r["id"], "type": "reinspection_time_basis", "evidence": [page, *r["facts"]]}
        )
    return nodes, edges


def event_lines(ledger, unit, kind):
    return {
        (r["doc"], r["page"], r["line"], r["quote"])
        for r in ledger.get("lines", [])
        if r["unit"] == unit and r["kind"] == kind and r["supported"] and r.get("stamp")
    }


def assess(ledger, finding, contract, graph=None):
    chain = finding.get("reinspection")
    if not chain or not ledger["pages"]:
        return None
    terms = [
        r
        for r in ledger["lines"]
        if r["role"] in ("contract", "contract_addendum") and not r["kind"].startswith("run_")
    ]
    steps = chain["steps"]
    units = {s["unit"] for s in steps}
    lines = [
        r for r in ledger["lines"] if r["role"] in ("contract", "contract_addendum") or r["unit"] in units
    ]
    refs = list(
        dict.fromkeys(ref for r in lines for ref in [r["id"], f"{r['doc']}/p{r['page']}", *r["facts"]])
    )
    refs = list(
        dict.fromkeys(
            [
                *refs,
                *(
                    f"{p['doc']}/p{p['page']}"
                    for p in ledger["pages"]
                    if p["unit"] in units or p["role"] in ("contract", "contract_addendum")
                ),
            ]
        )
    )
    result = {
        "sources": [r["id"] for r in lines],
        "evidence": refs,
        "required_hours": None,
        "above_seconds": None,
        "below_seconds": None,
        "repair_ref": None,
        "start_ref": None,
        "report_ref": None,
        "term_ref": None,
    }

    def outcome(state, status, detail):
        return {**result, "state": state, "status": status, "detail": detail}

    if (
        len(terms) != 1
        or terms[0]["unit"] != contract
        or not terms[0]["supported"]
        or terms[0]["kind"] not in ("operation", "minimum")
        or any(
            p["role"] == "contract_addendum" or p["unit"] == contract and not (p["native"] and p["text_only"])
            for p in ledger["pages"]
        )
    ):
        return outcome("terms_pending", "missing", "复验等待条款、附注或变更的完整范围待核。")
    term = terms[0]
    result.update(required_hours=term["hours"], term_ref=term["id"])
    repair = [s for s in steps if s["role"] == "repair"]
    final = [s for s in steps if s["role"] == "final"]
    if (
        len(repair) != 1
        or len(final) != 1
        or chain["state"] != "closed"
        or finding["status"] != "ok"
        or not repair[0]["date"]
        or not final[0]["date"]
    ):
        return outcome("chain_pending", "missing", "须先核实同一缺陷、整改记录与最终复验的归属、签认和日期。")
    if any(
        p["unit"] in (repair[0]["unit"], final[0]["unit"]) and not (p["native"] and p["text_only"])
        for p in ledger["pages"]
    ):
        return outcome(
            "events_pending", "missing", "整改或复验记录含影像或批注，须核对原页的记时与限定条件。"
        )

    def rows(unit, kind):
        return [r for r in lines if r["unit"] == unit and r["kind"] == kind]

    fix_day = rows(repair[0]["unit"], "fixed_day")
    fixed = rows(repair[0]["unit"], "fixed_time") or fix_day
    signed = rows(final[0]["unit"], "report_day")
    start = rows(final[0]["unit"], "started")
    if any(
        len(group) != 1 or not group[0]["supported"] or not group[0]["stamp"]
        for group in [fixed, fix_day, signed, *([start] if start else [])]
    ):
        return outcome(
            "events_pending",
            "missing",
            "整改完成、复验开始或报告日期存在断字、多个候选、异议或影像，须核对原件。",
        )
    fix, end = fixed[0], signed[0]
    result.update(repair_ref=fix["id"], report_ref=end["id"], start_ref=start[0]["id"] if start else None)
    if (
        fix["stamp"]["from"][:10] != repair[0]["date"]
        or fix_day[0]["stamp"]["from"][:10] != repair[0]["date"]
        or end["stamp"]["from"][:10] != final[0]["date"]
        or start
        and start[0]["stamp"]["from"] >= end["stamp"]["before"]
    ):
        return outcome("conflict", "risk", "时刻与签认日期不一致，或复验开始晚于已出具的复验记录。")

    def at(r, key):
        return datetime.fromisoformat(r["stamp"][key])

    upper = int((at(start[0] if start else end, "before") - at(fix, "from")).total_seconds())
    lower = int((at(start[0], "from") - at(fix, "before")).total_seconds()) if start else None
    result.update(above_seconds=lower, below_seconds=upper)
    minimum = term["hours"] * 3600
    if upper <= minimum:
        return (
            outcome("early", "risk", "即使按原件时点的最宽范围，复验开始与整改完成的间隔仍短于合同要求。")
            if start
            else outcome(
                "report_early", "risk", "已签认的复验单所载日期早于约定间隔届满的时点，须核实实际开验记录。"
            )
        )
    if term["kind"] == "operation":
        if graph is not None and ledger["format"] == FORMAT:
            run = trial_run.assess(
                lines, steps, contract, graph, fix, start[0] if start else None, term["hours"]
            )
            if run:
                return {**result, **run}
        return outcome(
            "operation_pending", "missing", "合同要求连续试运行并无异常，须取得覆盖该时段的运行记录和结果。"
        )
    if not start:
        return outcome("start_missing", "missing", "原件只载复验报告日期，须取得实际开始复验的记录。")
    if lower < minimum:
        return outcome(
            "boundary", "missing", "原件记时精度跨过合同规定的最短间隔，需核对更精确的完成与开始时刻。"
        )
    return outcome("met", "ok", "按整改完成和实际复验开始原行，最短可证间隔已满足该条约定。")


def apply(finding, check):
    finding["reinspection"]["timing"] = check
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *check["evidence"]]))
    if check["status"] == "ok":
        return False
    if finding["status"] == "ok":
        finding.update(status=check["status"], detail=check["detail"])
        finding["reinspection"]["focus"] = "final"
    else:
        if finding["status"] == "missing" and check["status"] == "risk":
            finding["status"] = "risk"
        finding["detail"] += " " + check["detail"]
    finding["reinspection"]["state"] = "open"
    return True


def verify(report, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("reinspection_wait")
    nodes = [n for n in graph["nodes"] if n["type"] == "reinspection_time_line"]
    edges = [e for e in graph["edges"] if e["type"] == "reinspection_time_basis"]
    if marker is None:
        if (
            policy.get("version", "") >= SINCE
            or "reinspection_wait.py" in policy.get("code_sha256", {})
            or "reinspection_wait_sources" in graph
            or nodes
            or edges
            or any("timing" in f.get("reinspection", {}) for f in report["findings"])
        ):
            raise ValueError("缺少合同复验间隔程序标记")
        if signing:
            for f in report["findings"]:
                if f["rule"] == "H02" and f["status"] == "ok" and f.get("reinspection"):
                    contracts = graph["documents_by_kind"].get("contract", [])
                    check = assess(
                        sources(graph, read_text, LEGACY), f, contracts[0] if len(contracts) == 1 else None
                    )
                    if check and check["status"] != "ok":
                        raise ValueError("旧版复验结论尚未核清合同等待期或试运行条件，请重新审计后签收。")
        return
    expected = FORMAT if policy.get("version", "") >= LOG_SINCE else LEGACY
    ledger = sources(graph, read_text, expected)
    if (
        marker != expected
        or marker == LEGACY
        and "trial_run.py" in policy.get("code_sha256", {})
        or policy.get("version", "") < SINCE
        or graph.get("reinspection_wait_sources") != ledger
        or (nodes, edges) != source_graph(ledger)
    ):
        raise ValueError("合同复验间隔原页、时点或证据关系与归档不符")
