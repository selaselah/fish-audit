"""Locate reservations about final inspection independently of the extracted result box."""

import hashlib
import re
from collections import defaultdict

from calculations import normalized
from performance_versions import FORMAT as CURRENT


FORMAT = "acceptance-reservations-v1"
LABELS = {"验收备注", "验收保留意见", "验收附注", "签收说明", "验收限制", "保留意见", "复验备注", "复验保留意见"}
CLEAR = {"无", "无保留意见", "无验收保留意见", "无其他验收限制"}
LIMIT = re.compile(
    r"(?:仅|只|暂)(?:作|为|确认|代表|完成|办理|进行|核对|验收|查验|检验|检查){0,3}(?:本次)?(?:到货|签收|外观|数量|包装|初验|暂收|点收)"
    r"|(?:不作为|不代表|不构成|不能视为|不等于|不得作为|仅为暂收).{0,8}(?:最终验收|终验|合格验收|验收合格)"
    r"|(?:尚未|未经|未完成|未进行|待完成|待补做)(?:整机|功能|性能|联调|最终|全部|质量|现场|项目){0,3}(?:测试|检测|检验|试验|调试|验收|复验|联调)"
    r"|(?:整机|功能|性能|联调|质量)(?:项目|指标)?(?:待检|未检|待测|未测)"
    r"|(?:最终验收|终验|复验|性能测试|功能测试)(?:将|须|需|应|尚待)?(?:另行|另约|待补|待办|暂缓|尚未|未完成|待完成)"
    r"|(?:有条件|附条件)(?:通过|验收|合格)|(?:临时|暂作|暂予|仅作)签收"
)


def classify(quote):
    text = normalized(quote).rstrip("。")
    label, separator, value = text.partition(":")
    if LIMIT.search(text):
        return "limited"
    if label in LABELS and separator and value not in CLEAR:
        return "unclear"
    return None


def sources(graph, read_text):
    units = {unit for kind in ("acceptance", "reinspection") for unit in graph["documents_by_kind"].get(kind, [])}
    sections = {(d["source"], d["page"]): d["id"] for d in graph.get("audit_documents", []) if "source" in d}
    observations = defaultdict(list)
    for fact in graph["facts"]:
        observations[fact["doc"], fact["page"]].append(fact)
    pages, lines = [], []
    for node in graph["nodes"]:
        if node["type"] != "page":
            continue
        doc, number = node["id"].rsplit("/p", 1)
        page = int(number)
        unit = sections.get((doc, page), doc)
        if unit not in units:
            continue
        place = {"unit": unit, "doc": doc, "page": page}
        native = node.get("layer") == "text"
        pages.append({**place, "native": native, "text_only": node.get("clause_text_only") is True})
        anchored = defaultdict(list)
        for fact in observations[doc, page]:
            loc = fact.get("source_line") or {}
            if native and loc.get("rects"):
                anchored[loc["number"], loc["text"]].append(fact["id"])
            elif kind := classify(fact["quote"]):
                lines.append({**place, "line": None, "kind": kind, "quote": fact["quote"], "facts": [fact["id"]]})
        if native:
            text = read_text(doc, page)
            if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != node.get("text_sha256"):
                raise ValueError("验收保留意见所据的原页文字摘要不符")
            for i, raw in enumerate(text.splitlines(), 1):
                if kind := classify(raw):
                    lines.append({**place, "line": i, "kind": kind, "quote": raw, "facts": anchored[i, raw]})
    return {"format": FORMAT, "pages": pages, "lines": lines}


def edges(ledger):
    return [{"type": "acceptance_reservation", "from": row["unit"], "to": f"{row['doc']}/p{row['page']}",
             "line": row["line"], "evidence": [f"{row['doc']}/p{row['page']}", *row["facts"]]} for row in ledger["lines"]]


def apply(finding, ledger):
    scope = set(finding["scope"])
    pages = [p for p in ledger.get("pages", []) if p["unit"] in scope]
    if not pages:
        return False
    lines = [s for s in ledger["lines"] if s["unit"] in scope]
    mixed = [p for p in pages if not p["native"] or not p["text_only"]]
    refs = [f"{p['doc']}/p{p['page']}" for p in pages] + [ref for row in lines for ref in row["facts"]]
    finding["acceptance_reservations"] = {"pages": pages, "lines": lines, "mixed_pages": mixed}
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *refs]))
    if not (lines or mixed):
        return False
    printed_limit = any(s["line"] and s["kind"] == "limited" for s in lines)
    before = finding["status"]
    if before not in ("issue", "risk"):
        finding["status"] = "risk" if printed_limit else "missing"
    detail = ("验收原页另载检查范围或终验限制，须核实其覆盖的项目及后续正式验收记录。" if printed_limit else
              "验收原页有待辨的保留意见或影像，须核实完整检查范围及正式终验记录。")
    if before == "ok":
        finding["detail"] = detail
    else:
        finding["detail"] += " " + detail
    if finding.get("reinspection"):
        finding["reinspection"]["state"] = "open"
    return True


def verify(report, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("acceptance_reservations")
    if not marker:
        if ("acceptance_reservations.py" in policy.get("code_sha256", {}) or "acceptance_reservation_sources" in graph
                or policy.get("performance_checks") == CURRENT):
            raise ValueError("缺少验收保留意见程序标记")
        if signing:
            for f in report["findings"]:
                if f["rule"] == "H02" and f["status"] == "ok" and not f.get("batch_acceptance"):
                    if apply(dict(f, reinspection=dict(f.get("reinspection") or {})), sources(graph, read_text)):
                        raise ValueError("旧版终验仍有保留意见或原页影像待核，请重新审计后签收。")
        return
    ledger = sources(graph, read_text)
    actual = [e for e in graph["edges"] if e["type"] == "acceptance_reservation"]
    if (marker != FORMAT or policy.get("performance_checks") != CURRENT
            or graph.get("acceptance_reservation_sources") != ledger or actual != edges(ledger)):
        raise ValueError("验收保留意见、整页影像覆盖或证据关系与归档不符")
