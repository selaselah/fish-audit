"""Account for the full reinspection form, including outstanding items outside the result box."""

import re
import unicodedata
from collections import defaultdict

import acceptance_payments
from calculations import AMOUNT, normalized
from delegation import covered_rows, is_page_marker
from delivery_batches import identifier, serials
from equipment_models import valid_code
from reinspection import FINAL, LINK_KEYS


SINCE = "2026.11.26.07"
ITEM_LABELS = {"未结整改项目", "未结项目", "未关闭事项", "待整改事项", "整改明细", "整改项目明细", "缺陷清单", "整改清单"}
SIGN_LABELS = {"签认附言", "签字附言", "签认附注", "签字栏附注", "复验备注", "复验保留意见"}
CLEAR = {"无", "无未结项目", "无未结整改项目", "无未关闭事项", "无保留意见"}
PENDING = re.compile(r"待(?:更换|整改|修复|返修|处理|复验|复检)|尚未(?:更换|修复|完成|关闭)|未关闭|仍有(?:遗留|缺陷|未结|异常)|暂修")
CONDITION = re.compile(r"(?:待|须|需|尚待).{0,35}(?:后|方可).{0,12}(?:最终报告|终验|最终验收|正式签认)"
                       r"|未经.{0,12}(?:验证|试运行)|(?:最终报告|终验报告).{0,6}(?:另行签发|暂缓签发)")
HYPOTHETICAL = re.compile(r"若|如果|如发生|如出现|一旦|假设|预案|无需|无须|不必|并无|并非|无未关闭")
SUPPLEMENTARY = {"equipment_model": valid_code, "delivered_serials": serials, "exchange_number": identifier,
                 "total": AMOUNT.fullmatch, "currency": lambda v: v in {"人民币", "CNY", "RMB"},
                 "unit": lambda v: v in {"元", "人民币元"}}
FIELDS = {*FINAL, *LINK_KEYS, *SUPPLEMENTARY}
DISPLAY_ONLY = re.compile(r"(?:收款账号|缺陷编号|原验收单编号|复验单编号|整改记录编号)(?:展示|显示)说明:(?:本单)?(?:完整展示|完整显示|仅列尾号)")


def row_kind(raw):
    text = unicodedata.normalize("NFKC", raw).strip().rstrip("。")
    label, separator, body = text.partition(":")
    value = body.strip() if separator else text
    if separator and label.strip() in ITEM_LABELS | SIGN_LABELS and value in CLEAR:
        return "clear"
    if HYPOTHETICAL.search(value):
        return "unreviewed"
    if CONDITION.search(value):
        return "conditional"
    if PENDING.search(value):
        return "open"
    if label.strip() in ITEM_LABELS and re.search(r"[,|;、]\s*(?:已关闭|已销项)$", value):
        return "reported_closed"
    return "unreviewed"


def sources(graph, read_text):
    from graph import LABELS, PRINTED_TITLES
    units = set(graph["documents_by_kind"].get("reinspection", []))
    receipts = set(graph["documents_by_kind"].get("acceptance", []))
    for fact in graph["facts"]:
        unit = fact.get("unit", fact["doc"])
        if unit in receipts and fact["field"] in ("original_acceptance", "repair_number", "defect_closure"):
            units.add(unit)

    def matches(field, value, quote):
        label, sep, body = normalized(quote).partition(":")
        if field in ("acceptance", "reinspection"):
            return PRINTED_TITLES.get(label) == field and normalized(value) == label
        if not (sep and body and label in LABELS.get(field, ()) and normalized(value) in (normalized(quote), body)):
            return False
        if field in SUPPLEMENTARY:
            return bool(SUPPLEMENTARY[field](body))
        return not (CONDITION.search(body) or PENDING.search(body)) or field == "repair_subject"

    pages = covered_rows(graph, read_text, units, FIELDS, matches, "复验原件")
    located, visual = defaultdict(list), defaultdict(list)
    for fact in graph["facts"]:
        if fact.get("unit", fact["doc"]) not in units:
            continue
        loc = fact.get("source_line") or {}
        if loc.get("rects") and loc["text"] == fact["quote"]:
            located[fact["doc"], fact["page"], loc["number"], loc["text"]].append(fact)
        elif not is_page_marker(fact["quote"]) and not matches(fact["field"], fact["value"], fact["quote"]):
            visual[fact["doc"], fact["page"]].append(fact)
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    result, lines = [], []
    for page in pages:
        doc, number = page["doc"], page["page"]
        place = {key: page[key] for key in ("unit", "doc", "page")}
        result.append({**place, "native": page["native"], "text_only": nodes[f"{doc}/p{number}"].get("clause_text_only") is True})
        for row in page["uncovered"]:
            raw = row["quote"]
            if DISPLAY_ONLY.fullmatch(normalized(raw).rstrip("。")):
                continue
            # A fully scoped payment-only opinion has its own procedure and does not qualify physical acceptance.
            opinion = acceptance_payments.classify(raw)
            if opinion and opinion["stance"] in ("hold", "assent"):
                continue
            facts = located[doc, number, row["line"], raw]
            kind = row_kind(raw)
            if any(f["status"] == "disputed" for f in facts):
                kind = "unreviewed"
            lines.append({**place, **row, "kind": kind, "facts": [f["id"] for f in facts]})
        for fact in visual[doc, number]:
            lines.append({**place, "line": None, "quote": fact["quote"], "kind": "unreviewed", "facts": [fact["id"]]})
    return {"pages": result, "lines": lines}


def edges(register):
    result = []
    for row in register["lines"]:
        page = f"{row['doc']}/p{row['page']}"
        result.append({"type": "reinspection_register_line", "from": row["unit"], "to": page,
                       "line": row["line"], "kind": row["kind"], "quote": row["quote"], "evidence": [page, *row["facts"]]})
    return result


def assess(finding, register, graph):
    chain = finding.get("reinspection") or {}
    final_units = {s["unit"] for s in chain.get("steps", []) if s["role"] == "final"}
    if not final_units:
        return None
    pages = [p for p in register["pages"] if p["unit"] in final_units]
    lines = [dict(row) for row in register["lines"] if row["unit"] in final_units]
    # Only the defect in the already substantiated chain can explain a second printed closure entry.
    if chain.get("state") == "closed" and len(final_units) == 1:
        expected = []
        for field in ("defect_number", "repair_subject"):
            facts = [f for f in graph["facts"] if f.get("unit", f["doc"]) in final_units and f["field"] == field]
            if len(facts) == 1 and facts[0]["status"] in ("anchored", "confirmed"):
                loc = facts[0].get("source_line") or {}
                if loc.get("rects") and loc["text"] == facts[0]["quote"]:
                    expected.append(unicodedata.normalize("NFKC", loc["text"]).partition(":")[2].strip())
        if len(expected) == 2 and all(expected):
            pattern = re.escape(expected[0]) + r"(?:\s+|\s*\|\s*)" + re.escape(expected[1]) + r"\s*[,|、]\s*(?:已关闭|已销项)"
            for row in lines:
                value = unicodedata.normalize("NFKC", row["quote"]).partition(":")[2].strip().rstrip("。")
                if row["kind"] == "reported_closed" and row["line"] and re.fullmatch(pattern, value):
                    row["kind"] = "matched"
    pending = [s for s in lines if s["kind"] not in ("clear", "matched")]
    mixed = [p for p in pages if not p["native"] or not p["text_only"]]
    if any(s["kind"] in ("open", "conditional") for s in pending):
        status, detail = "risk", "复验原页仍列待办整改或附条件签认，须核对相应措施及最终签认。"
    elif pending or mixed or {p["unit"] for p in pages} != final_units:
        status, detail = "missing", "复验附页、签认附言或另列事项尚缺逐项可核的关闭依据。"
    else:
        status, detail = "ok", ""
    return {"status": status, "detail": detail, "pages": pages, "lines": lines, "mixed_pages": mixed}


def apply(finding, register, graph):
    check = assess(finding, register, graph)
    if not check:
        return False
    chain = finding["reinspection"]
    chain["register"] = check
    pages = [f"{p['doc']}/p{p['page']}" for p in check["pages"]]
    facts = [ref for row in check["lines"] for ref in row["facts"]]
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *pages, *facts]))
    if check["status"] == "ok":
        return False
    if finding["status"] == "ok":
        finding.update(status=check["status"], detail=check["detail"])
    else:
        if finding["status"] == "missing" and check["status"] == "risk":
            finding["status"] = "risk"
        finding["detail"] += " " + check["detail"]
    chain.update(state="open", focus="final")
    return True
