"""Locate a short model reading of the installment count on its complete printed contract line."""
import re
from hashlib import sha256

from contract_folios import line_numbers, verify_page_geometry
from delegation import is_page_marker
from delivery_batches import NUM, ordinal
from party_readings import matches_model_reads
from payment_acceptance import column

KEY = "installment_count_sources"
FORMAT = "printed-installment-count-v1"
RECTS = "installment_count_rects"
SINCE = (2026, 11, 28, 5)
COUNT = re.compile(r"(?:合同价款)?分(" + NUM + r")期(?:付款|支付|结算)")
HEADINGS = {"付款条款", "付款方式", "结算条款", "结算方式"}


def sources(graph, read_text, read_layout, calls):
    from graph import LABELS, PRINTED_TITLES

    units = graph.get("documents_by_kind", {}).get("contract", [])
    if len(units) != 1:
        return []
    unit = units[0]
    terms = [f for f in graph["facts"] if f.get("unit", f["doc"]) == unit and f["field"] == "payment_term"]
    if len(terms) != 1:
        return []
    fact = terms[0]
    match = COUNT.fullmatch(fact["quote"])
    if (not match or not (count := ordinal(match[1])) or fact["value"] != fact["quote"] or fact["doc"] != unit
            or fact["page"] != 1 or fact.get("source_line") or fact.get("amendment") or fact.get("attestation")
            or fact["status"] != "visual" or fact.get("visual_check") != "clear"):
        return []
    page_id = unit + "/p1"
    address = re.fullmatch(re.escape(page_id) + r"/f([1-9][0-9]*)", fact["id"])
    doc = next((d for d in graph["documents"] if d["id"] == unit), {})
    page = next((n for n in graph["nodes"] if n["id"] == page_id and n["type"] == "page"), {})
    places = [p for p in graph.get("payment_window_sources", {}).get("pages", []) if p["unit"] == unit]
    call = calls.get((unit, 1)) or {}
    records = [e for e in graph["edges"] if e["type"] == "records" and e["to"] == fact["id"]]
    if (not address or records != [{"from":page_id,"to":fact["id"],"type":"records","evidence":[fact["id"]]}]
            or not all(re.fullmatch("[a-f0-9]{64}",str(item.get("sha256",""))) for item in (doc,page))
            or doc.get("ext") != ".pdf" or doc.get("pages") != 1 or doc["sha256"] != fact.get("source_sha256")
            or page.get("layer") != "text" or page.get("clause_text_only") is not True or page["sha256"] != fact.get("page_sha256")
            or len(places) != 1 or places[0]["doc"] != unit or places[0]["page"] != 1 or places[0]["document_kind"] != "contract"
            or not places[0]["native"] or not places[0]["text_only"] or call.get("output", {}).get("quality") != "readable"):
        return []
    row = {"doc": unit, "unit": unit, "page": 1, "field": "payment_term", "model_ref": fact["id"], "model_quote": fact["quote"],
           "value": fact["value"], "count": count, "original_sha256": doc["sha256"], "page_sha256": page["sha256"]}
    if not matches_model_reads(fact, row, call):
        return []
    votes = [r["support"] for r in call["check"]["output"]["checks"] if r["index"] == address[1]]
    if votes != ["clear"]:
        return []
    text = read_text(unit, 1)
    if not isinstance(text, str) or sha256(text.encode()).hexdigest() != page.get("text_sha256"):
        raise ValueError("分期总述所据合同文字与归档页不符")
    lines = text.splitlines()
    first = next((s.strip() for s in lines if s.strip() and not is_page_marker(s)), "")
    headings = [s for s in lines if PRINTED_TITLES.get(s.strip())]
    candidates = [(i, s) for i, s in enumerate(lines, 1) if column(s)[0] in LABELS["payment_term"]]
    if (PRINTED_TITLES.get(first) != "contract" or len(headings) != 1 or len(candidates) != 1
            or text.count(row["value"]) != 1):
        return []
    number, raw = candidates[0]
    label, body = column(raw)
    expected_gap = {"id": page_id, "doc": unit, "page": 1, "line": number, "quote": raw, "quality": "uncovered", "field": "payment_term"}
    if (label not in HEADINGS or body != row["value"] or expected_gap not in graph["gaps"]
            or any(f["doc"] == unit and (f.get("source_line") or {}).get("number") == number for f in graph["facts"])):
        return []
    rects = read_layout(unit, 1).get("lines", {}).get(str(number), [])
    return [{**row, "id": f"installment-count/{page_id}/l{number}", "line": number, "quote": raw, "rects": rects}]


def source_graph(rows):
    nodes, edges = [], []
    for r in rows:
        page = r["doc"] + "/p1"
        nodes.append({"id": r["id"], "type": "installment_count_line", "doc": r["doc"], "page": 1,
                      "line": r["line"], "label": r["quote"], "count": r["count"]})
        edges.append({"from": page, "to": r["id"], "type": "locates_installment_count", "evidence": [page, r["model_ref"]]})
    return nodes, edges


def attach(findings, row):
    if not row["rects"]:
        return
    for f in findings:
        if f["rule"] in ("H03", "H04", "H05", "H06") and row["unit"] in f["scope"] and (f["rule"] == "H03" or f.get("stage")):
            f["installment_count"] = row["id"]
            f["evidence"] = list(dict.fromkeys([*f["evidence"], row["id"], row["model_ref"], row["doc"] + "/p1"]))


def verify_originals(report, read_original):
    from payment_quality import verify_units
    graph = report["graph"]
    rows = graph.get(KEY, {}).get("rows", [])
    if rows:
        verify_units(graph, {r["unit"] for r in rows}, read_original, "合同分期总述", extra_lines=rows)


def verify(report, read_text, *, read_layout=None, signing=False):
    g, policy, findings = report["graph"], report["policy"], report["findings"]
    current = tuple(map(int, policy.get("version", "0").split("."))) >= SINCE
    if "code_sha256" in policy and ("installment_counts.py" in policy["code_sha256"]) != current:
        raise ValueError("分期总述方法与底稿版本不符")
    pages = report.get("calls", {}).get("pages", [])
    calls = {(c["doc"], c["page"]): c for c in pages}
    layout = read_layout or (lambda d, n: {"lines": calls.get((d, n), {}).get(RECTS, {})})
    rows = sources(g, read_text, layout, calls) if current or signing and read_layout else []
    if not current and rows and signing:
        guard_legacy(report, rows)
    saved = rows if current else []
    ledger = {"format": FORMAT, "rows": saved} if saved else None
    nodes = [n for n in g["nodes"] if n["type"] == "installment_count_line"]
    edges = [e for e in g["edges"] if e["type"] == "locates_installment_count"]
    if (g.get(KEY) != ledger or policy.get("installment_count") != (FORMAT if saved else None)
            or (nodes, edges) != source_graph(saved)):
        raise ValueError("合同分期总述的原行、两次模型读取或图关系不符")
    coords = {(r["doc"], 1): {str(r["line"]): r["rects"]} for r in saved if r["rects"]}
    verify_page_geometry(pages, line_numbers(saved), coords, RECTS, "合同分期总述", read_layout)
    if any(calls[r["doc"], 1]["page_sha256"] != r["page_sha256"] for r in saved):
        raise ValueError("分期总述图像与读取调用不符")
    supported = {(e["from"],e["to"]) for e in g["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
    for f in findings:
        row = next((r for r in saved if r["rects"] and f["rule"] in ("H03","H04","H05","H06") and r["unit"] in f["scope"]
                    and (f["rule"] == "H03" or f.get("stage"))), None)
        if f.get("installment_count") != (row["id"] if row else None) or row and any(
                ref not in f["evidence"] or (ref, "finding/" + f["id"]) not in supported
                for ref in (row["id"], row["model_ref"], row["doc"] + "/p1")):
            raise ValueError("履约发现与所据合同分期总述缺少原行依据")


def guard_legacy(report, rows):
    from performance import FORMAT as PERFORMANCE_FORMAT, compute
    if report["policy"].get("performance_checks") != PERFORMANCE_FORMAT:
        return
    banks = set(report["graph"]["documents_by_kind"].get("bank_receipt", []))
    def risks(findings):
        for f in findings:
            if f["rule"] != "H05" or not f.get("stage"):
                continue
            ref = f.get("retest_reference", {})
            if ref.get("status") == "risk":
                yield f["stage"]["clause_ref"], ref["bank"], ref["state"], ref.get("number")
            if f["status"] in ("issue","risk"):
                yield f["stage"]["clause_ref"], tuple(sorted(banks.intersection(f["scope"]))), f["status"]
    revised = compute({**report["graph"], KEY: {"format": FORMAT, "rows": rows}})
    if set(risks(revised)) - set(risks(report["findings"])):
        raise ValueError("补齐分期总述后发现新的实付风险，请重审后签收")
