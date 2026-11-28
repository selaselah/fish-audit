"""Compare a linked report's stated test population with the signed acceptance and contract."""

import re

from inspection_reports import one_field


FORMAT = "inspection-report-scope-v1"
SINCE = (2026, 11, 29, 2)
REPORT_LABELS = {
    "metric": ("检测项目", "检验项目"),
    "scope": ("检测范围", "检验范围"),
    "count": ("实际测温台数", "测温台数", "性能实测数量", "实际检测台数", "检测台数", "检验台数"),
}
SAMPLE_SCOPES = {"送检样机", "仅送检样机", "送检样品", "仅送检样品"}
ALL_SCOPES = {"本合同全部交付设备", "全部交付设备", "本批全部交付设备"}
SAMPLE_SENTENCE = re.compile(r"(?:仅送检|送检)(?:样机|样品)(?:柜温|温度)?(?:符合约定值|符合要求|不符合要求|合格|不合格)[。.]?")
QUALIFICATION = re.compile(r"复测|复检|按测次|重复|另有约定|仅列部分|节选|不含|不计入|免检|免测|除外|另附|改按|折算|豁免")
SCOPE_TOPIC = re.compile(r"检测|检验|测温|测次|抽检|抽测|复测|复检|样机|样品|台数|计数|交付数量|验收数量|免检|免测")
WITHDRAWN = re.compile(r"(?:本(?:检测|检验)?报告|本合同|报告状态[：:]|合同状态[：:]).{0,12}(?:作废|撤回)")


def plain_signed_body(page):
    """Inspect the private in-memory page after the original text and coordinates were read."""
    from pypdfium2 import raw
    from documents import clause_text_only

    total = raw.FPDFPage_GetAnnotCount(page)
    if total <= 0:
        return False
    for i in range(total):
        annot = raw.FPDFPage_GetAnnot(page, i)
        if not annot:
            return False
        try:
            rect = raw.FS_RECTF()
            if (raw.FPDFAnnot_GetSubtype(annot) != raw.FPDF_ANNOT_WIDGET or not raw.FPDFAnnot_GetRect(annot, rect)
                    or rect.left != rect.right or rect.bottom != rect.top):
                return False
        finally:
            raw.FPDFPage_CloseAnnot(annot)
    # Zero-area form widgets cannot obscure a printed quantity. Check the remaining page objects.
    return all(raw.FPDFPage_RemoveAnnot(page, i) for i in reversed(range(total))) and clause_text_only(page)


def fact_for_line(graph, doc, page, field, labels):
    if not page:
        return None
    line = one_field(page[0], labels)
    if not line:
        return None
    facts = [f for f in graph["facts"] if f["doc"]==doc["id"] and f["field"]==field]
    if len(facts)!=1:
        return None
    f, = facts
    loc = f.get("source_line") or {}
    node = next((n for n in graph["nodes"] if n["type"]=="page" and n["id"]==doc["id"]+"/p1"),{})
    if (f["page"]==1 and f["status"] in ("anchored","confirmed") and f["source_sha256"]==doc["sha256"]
            and f.get("page_sha256") and f["page_sha256"]==node.get("sha256")
            and f["quote"]==loc.get("text")==line["quote"] and loc.get("number")==line["line"]
            and loc.get("rects") and loc["rects"]==page[2].get(str(line["line"]))
            and f["value"] in (line["value"],line["quote"])):
        return {"fact":f["id"], **line}
    return None


def report_rows(page):
    rows = {}
    for key, labels in REPORT_LABELS.items():
        line = one_field(page[0], labels)
        if line and (rects := page[2].get(str(line["line"]))):
            rows[key] = {**line,"rects":rects}
    return rows


def comparison(graph, row, ref, receipt, contract, report_page):
    from contract_changes import QUANTITY_LABELS, SOURCE_LABELS
    from inspection_coverage import ALL, LABELS, MINIMUM, count
    from reinspection import LINK_KEYS

    candidate, = ref["candidates"]
    rows = report_rows(report_page)
    sample_result = bool(candidate["conclusion"] and SAMPLE_SENTENCE.fullmatch(candidate["conclusion"]["value"]))
    if "scope" not in rows and "count" not in rows and not sample_result:
        return None
    scope = rows.get("scope",{}).get("value")
    sample = scope in SAMPLE_SCOPES or sample_result
    reported = count(rows["count"]["value"]) if "count" in rows else None
    basis = {}
    record = {"format":FORMAT, "report_rows":rows, "basis":basis, "sample":sample,
              "reported":reported, "received":None, "ordered":None, "required":None, "difference":None,
              "mode":None, "state":"sample" if sample and reported is None else "review"}
    if not receipt:
        return record
    receipt_doc, receipt_page = receipt
    if not receipt_page or not receipt_page[3]:
        return record
    def bind(key, material, field, labels):
        doc, page = material
        line = fact_for_line(graph, doc, page, field, labels)
        if line:
            basis[key] = line
            return line["value"]
    acceptance = bind("acceptance_scope", receipt, "acceptance_scope", SOURCE_LABELS["acceptance_scope"])
    record["received"] = count(bind("accepted", receipt, "quantity_accepted", QUANTITY_LABELS["quantity_accepted"]) or "")
    if not contract or row["role"]!="acceptance":
        return record
    kinds = graph["documents_by_kind"]
    if (kinds.get("acceptance") != [row["doc"]] or any(kinds.get(k) for k in ("contract_addendum","reinspection","remediation"))
            or graph.get("quality_addenda",{}).get("signals")):
        return record
    contract_doc, contract_page = contract
    if not contract_page or not contract_page[1]:
        return record
    linked = {}
    for field in LINK_KEYS:
        values = [fact_for_line(graph, doc, page, field, SOURCE_LABELS[field])
                  for doc,page in ((contract_doc,contract_page),(receipt_doc,receipt_page))]
        if not all(values) or values[0]["value"] != values[1]["value"]:
            return record
        linked["contract_"+field], linked["receipt_"+field] = values
    if linked["receipt_contract_id"]["fact"] != ref["signed_contract"]["fact"]:
        return record
    basis.update(linked)
    ordered = count(bind("ordered", contract, "quantity_agreed", QUANTITY_LABELS["quantity_agreed"]) or "")
    record["ordered"] = ordered
    clause = bind("clause", contract, "inspection_requirement", LABELS["inspection_requirement"])
    if not clause:
        return record
    # Only compare a final lot and the same equipment/measurement under a single unqualified clause.
    subject = linked["contract_subject"]["value"]
    metrics = {subject+metric for metric in ("柜温","柜内温度","温度")}
    qualified = any(WITHDRAWN.search(s) or (SCOPE_TOPIC.search(s) and QUALIFICATION.search(s))
                    for page in (contract_page,receipt_page,report_page) for s in page[0])
    related = graph.get("inspection_coverage_sources",{}).get("rows",())
    used_lines = {line["quote"] for line in (*rows.values(),candidate["number"],candidate["contract"])}
    if candidate["conclusion"]:
        used_lines.add(candidate["conclusion"]["quote"])
    disputed = any(f["status"]=="disputed" and f["doc"]==candidate["doc"] and
                   (f["quote"] in used_lines or f["field"] in ("contract_id","tested_quantity","inspection_requirement")) for f in graph["facts"])
    if (not ordered or ordered != record["received"] or acceptance not in ("全部交付终验","全部交付最终验收","全部标的最终验收")
            or rows.get("metric",{}).get("value") not in metrics or qualified or disputed
            or any(r["kind"] in ("note","inspection_required_serials","substitution","serial_note") for r in related)
            or scope not in SAMPLE_SCOPES | ALL_SCOPES or scope in ALL_SCOPES and sample_result):
        record["state"] = "review"
        return record
    minimum = MINIMUM.fullmatch(clause)
    if clause in ALL:
        record.update(mode="all", required=ordered)
    elif minimum and 0 < int(minimum[1] or minimum[2]) <= ordered:
        record.update(mode="minimum", required=int(minimum[1] or minimum[2]))
    if record["required"] is not None and reported is not None and reported <= ordered:
        gap = max(0, record["required"] - reported)
        record.update(difference=gap, state="short" if gap else "count_only")
    return record


def detail(c):
    tested, required, received = c["reported"], c["required"], c["received"]
    if c["state"] in ("short","count_only"):
        rule = "按合同正文逐台测温条款" if c["mode"]=="all" else "按合同正文抽检下限"
        comparison = f"{rule}应检至少 {required} 台，本报告记载检测 {tested} 台。"
        if c["state"]=="short":
            return comparison + f"该报告所列台数比条款下限少 {c['difference']} 台，请核实其余设备的检测依据。"
        return comparison + "所列台数达到条款下限，请核对设备编号、逐台读数及终验范围。"
    counted = f"验收单记载实收 {received} 台。" if received is not None else ""
    if c["state"]=="sample":
        return counted + "报告原文提到送检样机或样品，尚缺可比对的检测台数，请核实样品与本批交付的对应关系。"
    observed = f"报告记载检测 {tested} 台。" if tested is not None else ""
    return counted + observed + "报告适用的检测对象、条款或数量口径仍需人工核对。"
