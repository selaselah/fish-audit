"""Preserve breaks inside a printed measurement before a numeric acceptance check."""

import re

from payment_quality import column, metric_reading, printed_rows, verify_units


FORMAT = "printed-measurement-spacing-v1"
KEY = "measurement_number_sources"
RECTS = "measurement_number_rects"
SINCE = (2026, 11, 28, 15)
FIELDS = {"contract": ("acceptance_criteria",), "acceptance": ("inspection_basis", "measured_result"),
          "reinspection": ("inspection_basis", "measured_result")}
LABELS = {"acceptance_criteria": "合同验收标准", "inspection_basis": "检验依据", "measured_result": "实测结果"}
BREAK = re.compile(r"(?<=[0-9])\s+(?=[0-9.])|(?<=[.\-])\s+(?=[0-9])")


def ambiguous(field, text):
    _, value = column(text)
    if not BREAK.search(value):
        return False
    # Removing a gap is used only to recognize a potential numeric token. Its joined value is never reported.
    match = metric_reading("".join(value.split()), True)
    return bool(match and bool(match[2]) == (field != "measured_result"))


def sources(graph, read_text):
    kinds = graph.get("documents_by_kind", {})
    if not kinds.get("contract") or not (kinds.get("acceptance") or kinds.get("reinspection")):
        return []
    units = {unit: fields for kind, fields in FIELDS.items() for unit in kinds.get(kind, ())}
    observations = {f["id"]: f for f in graph["facts"] if f["field"] in units.get(f.get("unit", f["doc"]), ())}
    split = {ref for ref, f in observations.items() if any(ambiguous(f["field"], f[k]) for k in ("value", "quote"))}
    rows = []
    for row in printed_rows(graph, read_text, FIELDS):
        if row["field"] not in units[row["unit"]]:
            continue
        refs = [ref for ref in row["facts"] if ref in observations and observations[ref]["field"] == row["field"]]
        raw = ambiguous(row["field"], row["quote"])
        if raw or split.intersection(refs):
            page = f"{row['doc']}/p{row['page']}"
            item = {**row, "facts": refs, "origin": "original" if raw else "transcription",
                    "id": f"measurement-number/{page}/l{row['line']}"}
            if not raw:
                item["readings"] = [{k:observations[ref][k] for k in ("id","value","quote")} for ref in refs if ref in split]
            rows.append(item)
            split.difference_update(refs)
    for ref, f in observations.items():
        if ref in split:
            rows.append({"id": "measurement-number/"+ref, "doc": f["doc"], "unit": f.get("unit", f["doc"]),
                         "page": f["page"], "line": None, "field": f["field"], "quote": f["quote"],
                         "origin": "transcription", "facts": [ref], "readings": [{k:f[k] for k in ("id","value","quote")}]})
    return rows


def graph_records(rows):
    nodes, edges = [], []
    for r in rows:
        page = f"{r['doc']}/p{r['page']}"
        nodes.append({"id": r["id"], "type": "measurement_number_review", "doc": r["doc"], "page": r["page"],
                      "line": r["line"], "field": r["field"], "origin": r["origin"], "label": r["quote"]})
        edges.append({"from": page, "to": r["id"], "type": "measurement_number_source", "evidence": [page, *r["facts"]]})
    return nodes, edges


def attach(finding, rows, *, paid=None):
    cited = [r for r in rows if r["unit"] in finding["scope"]]
    if not cited:
        return
    refs = [ref for r in cited for ref in (r["id"], f"{r['doc']}/p{r['page']}", *r["facts"])]
    finding["measurement_numbers"] = [r["id"] for r in cited]
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *refs]))
    if finding["status"] == "ok":
        finding["status"] = "missing"
        finding["detail"] = "验收数值需要核对。"
    if paid:
        finding["detail"] += f" 回单所列付款日为 {paid}，需核对付款时所据的验收记录。"
    for r in cited:
        location = f"第 {r['page']} 页" + (f"第 {r['line']} 行" if r["line"] else "的抄录")
        origin = "原行" if r["origin"] == "original" else "抄录"
        requested = {"acceptance_criteria":"签署版合同所列限值", "inspection_basis":"本次检验采用的标准原文",
                     "measured_result":"本次检测的原始读数"}[r["field"]]
        finding["detail"] += f" {LABELS[r['field']]}{location}载“{r['quote']}”。{origin}数字内部有间距，请核对{requested}。"


def expert_rows(graph, findings):
    refs = {ref for f in findings for ref in f.get("measurement_numbers", ())}
    return [r for r in graph.get(KEY, {}).get("rows", ()) if r["id"] in refs]


def verify(report, read_text, *, read_original=None, read_layout=None, signing=False):
    from contract_folios import line_numbers, verify_page_geometry

    g, p, findings = report["graph"], report["policy"], report["findings"]
    current = tuple(map(int, p.get("version", "0").split("."))) >= SINCE
    if "code_sha256" in p and ("measurement_spacing.py" in p["code_sha256"]) != current:
        raise ValueError("验收数值核字方法与底稿版本不符")
    legacy_acceptance = signing and any(f["rule"] == "H02" for f in findings)
    rows = sources(g, read_text) if current or legacy_acceptance else []
    if not current and signing and any(f["rule"] == "H02" and any(r["unit"] in f["scope"] for r in rows) for f in findings):
        raise ValueError("旧版验收资料中有数字间距尚未单列核对，请重审后签收。")
    ledger = {"format": FORMAT, "rows": rows} if rows and current else None
    nodes = [n for n in g["nodes"] if n["type"] == "measurement_number_review"]
    edges = [e for e in g["edges"] if e["type"] == "measurement_number_source"]
    if (g.get(KEY) != ledger or p.get("measurement_numbers") != (FORMAT if ledger else None)
            or (nodes, edges) != graph_records(ledger["rows"] if ledger else [])):
        raise ValueError("验收数值的原行、抄录或图谱关系不符")
    filed = {r["id"]: r for r in rows}
    for f in findings:
        refs = f.get("measurement_numbers", [])
        if refs and (not ledger or f["rule"] not in ("H02", "H04", "H05") or f["status"] == "ok" or
                     any(ref not in filed or ref not in f["evidence"] or filed[ref]["unit"] not in f["scope"] for ref in refs)):
            raise ValueError("验收数值的发现与所引原件不符")
    calls = report.get("calls", {})
    expert = calls.get("expert", {})
    if current and ("input" in expert or expert.get("request_format")):
        packet = expert.get("input")
        if not isinstance(packet, dict):
            raise ValueError("专家输入缺少出具底稿时的审计资料")
        expected = expert_rows(g, findings)
        issued = [(f["rule"], f["measurement_numbers"]) for f in findings if f.get("measurement_numbers")]
        sent = [(f["rule"], f["measurement_numbers"]) for f in packet.get("procedures", ()) if f.get("measurement_numbers")]
        if packet.get("measurement_number_sources") != (expected or None) or issued != sent:
            raise ValueError("专家输入未保留出具底稿所据的验收数值原行")
    if calls.get("pages") or p.get("archived_methods"):
        verify_page_geometry(calls.get("pages", ()), line_numbers(rows), {}, RECTS, "验收数值", read_layout)
    if rows and read_original:
        pages = {(t["doc"], t["page"]): t for t in calls.get("pages", ())}
        located = [{**r, "rects": pages[r["doc"],r["page"]][RECTS][str(r["line"])]}
                   for r in rows if r["line"] is not None]
        verify_units(g, {r["unit"] for r in rows}, read_original, "验收数值原件", extra_lines=located)
