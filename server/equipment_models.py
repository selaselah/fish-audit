"""Compare explicit equipment models on the contract and physical acceptance records."""

import hashlib
import re
from collections import defaultdict
from reinspection import LINK_KEYS



FORMAT = "printed-equipment-models-v1"
SINCE = "2026.11.25.13"
ORDERED = {"约定设备型号", "合同约定型号", "约定型号", "采购设备型号", "订购型号", "约定规格型号"}
RECEIVED = {"实收设备型号", "实收型号", "实收规格型号", "实际交付型号", "实际验收型号", "本次验收型号", "复验实收型号"}
MODEL = re.compile(r"型号|机型|换型|改型")
ALTERNATIVE = re.compile(r"替代|代用|同等(?:型|品|设备|产品)|等效(?:型|品|设备|产品)|换型|改型|另行选型|变更规格"
                         r"|替换(?:货物|设备|产品)|以实物为准|改供|改交|改用|换货|同意.{0,24}(?:交货|交付|供货)")
CODE = re.compile(r"[A-Za-z0-9]+(?:[-._][A-Za-z0-9]+)*", re.ASCII)
MASK = re.compile(r"X{2,}|\*|[＊×□…]|尾号|遮盖|样机|暂定|待定", re.I)
RANK = {"ok": 0, "missing": 1, "risk": 2, "issue": 3}


def parts(quote):
    label, separator, body = quote.replace("：", ":", 1).partition(":")
    return label.strip(), body.strip() if separator else ""


def source_kind(quote):
    label, value = parts(quote)
    if ALTERNATIVE.search(quote):
        return "qualification", value
    if label in ORDERED:
        return "ordered", value
    if label in RECEIVED:
        return "received", value
    if MODEL.search(quote):
        return "unassigned", value
    return None, ""


def sources(graph, read_text):
    sections = {(u["source"], u["page"]): u["id"] for u in graph.get("audit_documents", []) if "source" in u}
    roles = {unit: role for role, units in graph["documents_by_kind"].items() for unit in units}
    facts_by_page = defaultdict(list)
    for fact in graph["facts"]:
        facts_by_page[fact["doc"], fact["page"]].append(fact)
    gaps = {(g["doc"], g["page"]) for g in graph["gaps"] if g.get("quality") in ("partial", "unreadable")}
    pages, lines = [], []
    for node in graph["nodes"]:
        if node["type"] != "page":
            continue
        doc, suffix = node["id"].rsplit("/p", 1)
        page = int(suffix)
        unit = sections.get((doc, page), doc)
        place = {"doc": doc, "page": page, "unit": unit, "role": roles.get(unit, "unknown")}
        native = node.get("layer") == "text"
        anchored = defaultdict(list)
        page_lines = []
        for fact in facts_by_page[doc, page]:
            loc = fact.get("source_line") or {}
            if native and loc.get("rects") and loc["text"] == fact["quote"]:
                anchored[loc["number"], loc["text"]].append(fact["id"])
                continue
            kind, value = source_kind(fact["quote"])
            if kind or fact["field"] == "equipment_model":
                page_lines.append({**place, "line": None, "kind": kind or "unassigned", "value": value,
                                   "quote": fact["quote"], "facts": [fact["id"]]})
        if native:
            raw = read_text(doc, page)
            if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != node.get("text_sha256"):
                raise ValueError("型号核对所据原页文字与存档不符")
            for number, quote in enumerate(raw.splitlines(), 1):
                kind, value = source_kind(quote)
                if kind:
                    page_lines.append({**place, "line": number, "kind": kind, "value": value,
                                       "quote": quote, "facts": anchored[number, quote]})
        if page_lines or place["role"] in ("contract", "acceptance", "reinspection", "contract_addendum", "unknown"):
            pages.append({**place, "native": native, "text_only": node.get("clause_text_only") is True,
                          "incomplete": (doc, page) in gaps})
        lines.extend(page_lines)
    active = any(MODEL.search(r["quote"]) and r["role"] in ("contract", "acceptance", "reinspection", "contract_addendum", "unknown") for r in lines) or any(g.get("field") == "equipment_model" for g in graph["gaps"])
    return {"format": FORMAT, "pages": pages if active else [], "lines": lines if active else []}


def valid_code(value):
    return (2 <= len(value) <= 60 and CODE.fullmatch(value) and re.search(r"[A-Za-z]", value)
            and re.search(r"[0-9]", value) and not MASK.search(value))


def exact_line(rows, kind):
    matches = [r for r in rows if r["kind"] == kind]
    if len(matches) == 1 and matches[0]["line"] is not None and valid_code(matches[0]["value"]):
        return matches[0]


def evidence(pages, lines):
    return list(dict.fromkeys([*(f"{p['doc']}/p{p['page']}" for p in pages),
                                *(ref for r in lines for ref in r["facts"])]))


def assess(graph, contract, receipts, *, effective):
    from warranty_terms import identity
    ledger = graph.get("equipment_model_sources", {})
    pages = ledger.get("pages", [])
    if not pages:
        return None
    lines = ledger["lines"]
    by_unit = defaultdict(list)
    for row in lines:
        by_unit[row["unit"]].append(row)
    scope = {contract.unit, *(r.unit for r in receipts)}
    ordered = exact_line(by_unit[contract.unit], "ordered")
    global_reasons = []
    if not ordered:
        global_reasons.append("合同缺少可逐字核对的唯一约定型号")
    if any(p["role"] in ("unknown", "contract_addendum") for p in pages):
        global_reasons.append("另有补充协议或未归属资料，需核实现行型号约定")
    if any(r["unit"] not in scope or r["unit"] == contract.unit and r["kind"] != "ordered"
           or r["kind"] == "qualification" and len(receipts) > 1 for r in lines):
        global_reasons.append("另有型号、替代或换型记载，需核对其适用范围和批准依据")
    def unclear(unit):
        return any(not p["native"] or not p["text_only"] or p["incomplete"] for p in pages if p["unit"] == unit)
    if unclear(contract.unit):
        global_reasons.append("合同型号原页有影像、缺栏或待辨内容")
    records = []
    for doc in receipts:
        rows = by_unit[doc.unit]
        received = exact_line(rows, "received")
        reasons = global_reasons.copy()
        association = {"matches": identity(contract, doc), "contract": contract.evidence(*LINK_KEYS),
                       "receipt": doc.evidence(*LINK_KEYS)}
        if not association["matches"]:
            reasons.append("验收单的合同号、双方及标的尚未与本合同原文对应")
        if unclear(doc.unit) or any(r["kind"] != "received" for r in rows):
            reasons.append("验收页有其他型号、影像或范围说明待核")
        if not received:
            reasons.append("须取得本次实收设备的完整、唯一型号原行")
        status, comparison = "missing", "unresolved"
        if not reasons:
            left, right = ordered["value"], received["value"]
            if left == right:
                status, comparison, detail = "ok", "match", "合同约定与实际验收原行均列型号 " + left + "。"
            elif re.sub(r"[-._]", "", left).casefold() == re.sub(r"[-._]", "", right).casefold():
                reasons.append("型号的大小写或分隔符有差别，需查明制造商的编码口径")
            else:
                comparison = "different"
                status = "issue" if effective else "risk"
                detail = f"合同约定型号 {left}，验收原件实收型号 {right}，两处记载不符。"
                if not effective:
                    detail += " 合同生效或现行状态仍待核实。"
        if reasons:
            detail = "。".join(reasons) + "。"
        units = {contract.unit, doc.unit}
        linked_pages = pages if global_reasons else [p for p in pages if p["unit"] in units]
        linked_lines = lines if global_reasons else [r for r in lines if r["unit"] in units]
        records.append({"unit": doc.unit, "status": status, "detail": detail, "received": received,
                        "comparison": comparison, "reasons": reasons, "identity": association,
                        "evidence": list(dict.fromkeys([*evidence(linked_pages, linked_lines),
                                                        *association["contract"], *association["receipt"]]))})
    status = max((r["status"] for r in records), key=RANK.get, default="missing")
    if not records:
        detail = "须取得与本合同对应的验收原件，核对实收设备型号。"
    else:
        detail = " ".join(dict.fromkeys(r["detail"] for r in records if r["status"] == status))
    if status == "issue" and any(p["role"] == "reinspection" for p in pages):
        status = "risk"
        detail += " 有复验记录，请核对原交付、换货及最终接受设备之间的对应关系。"
    refs = list(dict.fromkeys([*evidence(pages, lines), *(ref for item in records for ref in item["evidence"])]))
    return {"status": status, "detail": detail, "ordered": ordered, "records": records, "evidence": refs}


def apply(finding, comparison):
    if comparison["status"] != "ok":
        if finding["status"] == "ok":
            finding["detail"] = comparison["detail"]
        elif comparison["detail"] not in finding["detail"]:
            finding["detail"] += " " + comparison["detail"]
        if RANK[comparison["status"]] > RANK[finding["status"]]:
            finding["status"] = comparison["status"]


def edges(findings):
    result = []
    for finding in findings:
        comparison = finding.get("equipment_models")
        if not comparison or not comparison["ordered"]:
            continue
        left = comparison["ordered"]
        for record in comparison["records"]:
            right = record["received"]
            if record["comparison"] != "unresolved" and right:
                source, target = (f"{r['doc']}/p{r['page']}" for r in (left, right))
                result.append({"type": "equipment_model_comparison", "from": source, "to": target,
                               "ordered_line": left["line"], "received_line": right["line"], "status": record["status"],
                               "evidence": list(dict.fromkeys([source, *left["facts"], target, *right["facts"],
                                                               *record["identity"]["contract"], *record["identity"]["receipt"]]))})
    return result


def verify(report, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("equipment_models")
    if not marker:
        if policy.get("version", "") >= SINCE or "equipment_model_sources" in graph or "equipment_models.py" in policy.get("code_sha256", {}):
            raise ValueError("缺少设备型号核对程序")
        if signing and any(f["rule"] in ("H02", "H04", "H05") and f["status"] == "ok" for f in report["findings"]) and sources(graph, read_text)["pages"]:
            raise ValueError("旧版验收未逐项核对所列设备型号，请按现行程序重审后签收。")
        return
    if (marker != FORMAT or policy.get("version", "") < SINCE or graph.get("equipment_model_sources") != sources(graph, read_text)
            or [e for e in graph["edges"] if e["type"] == "equipment_model_comparison"] != edges(report["findings"])):
        raise ValueError("约定与实收型号的原行、单据或图谱关系与归档不符")
