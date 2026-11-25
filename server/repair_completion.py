"""Reconcile a repair completion entry with the dated original and all its riders."""

import re
from collections import defaultdict

from calculations import normalized
from contract_changes import SOURCE_LABELS
from delegation import covered_rows
from reinspection import LABELS, LINK_KEYS, REPAIR


FORMAT = "repair-completion-v1"
SINCE = "2026.11.25.21"
TITLES = ("整改记录单", "缺陷整改记录", "整改完成记录")
FIELDS = {**{key: SOURCE_LABELS[key] for key in LINK_KEYS},
          **{key: LABELS[key] for key in REPAIR if key != "remediation"}}
NOTES = {"整改备注", "整改说明", "整改补充意见", "补充说明", "备注", "整改保留意见"}
CLEAR = {"无", "无补充意见", "无保留意见", "无其他整改事项"}
QUALIFIED = re.compile(r"仅(?:作|做|做了|作了)?临时|暂作|临时处[理置]|尚未|仍未|未完成|未实施|未更换|待(?:正式|更换|整改|复修|返修)|仅部分|部分完成|暂停整改")


def matches(field, value, quote):
    text = normalized(quote)
    if field == "remediation":
        return text == normalized(value) and text in TITLES
    label, sep, body = text.partition(":")
    return sep and body and label in FIELDS.get(field, ()) and normalized(value) in (text, body)


def kind_of(raw, uncovered):
    label, sep, body = normalized(raw).rstrip("。").partition(":")
    if sep and label in LABELS["repaired_on"]:
        return "date"
    if sep and label in (*LABELS["repair_result"], *LABELS["repair_action"]):
        if QUALIFIED.search(body):
            return "qualification"
        if uncovered:
            return "unreviewed"
        return "state" if label in LABELS["repair_result"] else "action"
    if uncovered:
        if label in NOTES and sep and body in CLEAR:
            return None
        return "qualification" if QUALIFIED.search(raw) else "unreviewed"
    return None


def sources(graph, read_text):
    units = set(graph["documents_by_kind"].get("remediation", []))
    coverage = covered_rows(graph, read_text, units, {"remediation", *FIELDS}, matches, "整改记录")
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    located, visual = defaultdict(list), defaultdict(list)
    for f in graph["facts"]:
        if f.get("unit", f["doc"]) not in units:
            continue
        loc = f.get("source_line") or {}
        if loc.get("rects"):
            located[f["doc"], f["page"], loc["number"], loc["text"]].append(f["id"])
        else:
            visual[f["doc"], f["page"]].append(f)
    pages, lines = [], []
    for page in coverage:
        doc, number = page["doc"], page["page"]
        place = {"unit": page["unit"], "doc": doc, "page": number}
        pages.append({**place, "native": page["native"],
                      "text_only": nodes[f"{doc}/p{number}"].get("clause_text_only") is True})
        unaccounted = {s["line"] for s in page["uncovered"]}
        if page["native"]:
            for line, raw in enumerate(read_text(doc, number).splitlines(), 1):
                kind = kind_of(raw, line in unaccounted)
                if kind:
                    lines.append({**place, "line": line, "kind": kind, "quote": raw, "facts": located[doc, number, line, raw]})
        for f in visual[doc, number]:
            kind = kind_of(f["quote"], not matches(f["field"], f["value"], f["quote"]))
            if kind:
                lines.append({**place, "line": None, "kind": kind, "quote": f["quote"], "facts": [f["id"]]})
    return {"format": FORMAT, "pages": pages, "lines": lines}


def edges(ledger):
    return [{"type": "repair_completion_basis", "from": s["unit"], "to": f"{s['doc']}/p{s['page']}",
             "line": s["line"], "kind": s["kind"], "evidence": [f"{s['doc']}/p{s['page']}", *s["facts"]]}
            for s in ledger["lines"]]


def check(ledger, material, printed_date, *, timing_lines=()):
    pages = [p for p in ledger["pages"] if p["unit"] == material.unit]
    lines = [s for s in ledger["lines"] if s["unit"] == material.unit and
             not (s["kind"] == "unreviewed" and (s["doc"], s["page"], s["line"], s["quote"]) in timing_lines)]
    dates = [s for s in lines if s["kind"] == "date"]
    anchored = material.fields["repaired_on"]
    dated = (len(dates) == 1 and dates[0]["line"] and len(anchored) == 1
             and anchored[0]["id"] in dates[0]["facts"])
    date = printed_date if dated else None
    mixed = [p for p in pages if not p["native"] or not p["text_only"]]
    holds = [s for s in lines if s["kind"] in ("qualification", "unreviewed")]
    if any(s["kind"] == "qualification" and s["line"] for s in holds):
        status, reason = "risk", "整改原件另有临时处理、尚未完成或范围受限的记载，须核对与复验所指措施是否相同。"
    elif mixed or not pages:
        status, reason = "missing", "整改记录含影像或页内批注，需核对整页的完成日期和整改范围。"
    elif not date:
        status, reason = "missing", "整改完成日期缺少唯一、连续且可定位的原行，需核对原件。"
    elif holds or any(sum(s["kind"] == k for s in lines) != 1 for k in ("action", "state")):
        status, reason = "missing", "整改原件另有尚待核对的内容，须查明是否限定完成范围。"
    else:
        status, reason = "ok", "整改完成日期有据，原页未见限制完成范围的附注。"
    refs = [f"{p['doc']}/p{p['page']}" for p in pages] + [ref for s in lines for ref in s["facts"]]
    return {"status": status, "detail": reason, "date": date.isoformat() if date else None, "lines": lines,
            "mixed_pages": mixed, "evidence": list(dict.fromkeys(refs))}


def verify(report, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("repair_completion")
    actual = [e for e in graph["edges"] if e["type"] == "repair_completion_basis"]
    if marker is None:
        if (policy.get("version", "") >= SINCE or "repair_completion.py" in policy.get("code_sha256", {})
                or "repair_completion_sources" in graph or actual):
            raise ValueError("整改原件核对程序或版本缺失")
        if signing and any(f.get("reinspection", {}).get("state") == "closed" for f in report["findings"]):
            from performance import Material, printed_day
            ledger = sources(graph, read_text)
            contracts = graph["documents_by_kind"].get("contract", [])
            if len(contracts) != 1 or not printed_day(Material(graph, contracts[0]), "signed_on"):
                raise ValueError("旧版关闭缺陷所据的签约日期待核，请重新审计后签收。")
            for f in report["findings"]:
                if f.get("reinspection", {}).get("state") != "closed":
                    continue
                for step in f["reinspection"]["steps"]:
                    doc = Material(graph, step["unit"])
                    field = "repaired_on" if step["role"] == "repair" else "accepted_on"
                    date = printed_day(doc, field)
                    if (not date or date.isoformat() != step["date"] or
                            step["role"] == "repair" and check(ledger, doc, date)["status"] != "ok"):
                        raise ValueError("旧版关闭缺陷所据的整改原件或日期待核，请重新审计后签收。")
        return
    expected = sources(graph, read_text)
    if marker != FORMAT or graph.get("repair_completion_sources") != expected or actual != edges(expected):
        raise ValueError("整改记录的原页、日期、附注或证据关系与归档不符")
