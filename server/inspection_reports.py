"""Locate the inspection attachment explicitly cited in a verified acceptance signature."""

from hashlib import sha256
import re

from quality_references import PARTIAL, incomplete_number


REFERENCE = re.compile(
    r"(?:已收到检测资料[，,。])?终验质量结论以正式(?P<kind>检测报告|检验报告)"
    r"(?:[（(]编号[：:]\s*(?P<number>[^()（）\r\n]{1,80})[）)])?为准[。.]?"
)
NUMBER = re.compile(r"(?=.{1,64}\Z)(?=.*[0-9])[A-Za-z0-9]+(?:[-./][A-Za-z0-9]+)*")
TITLES = {"检测报告":"检测报告", "正式检测报告":"检测报告", "检验报告":"检验报告", "正式检验报告":"检验报告"}
MESSAGES = {
    "unlocated":"本版尚未定位到可核对的报告原页，请查验附件或补件。",
    "unidentified":"签名未给出可比对的完整报告编号，请核实所指附件。",
    "multiple":"有多份同类报告，请核实所指附件。",
    "uncertain":"所签验收单或报告原页的编号待核，请人工确认归属。",
    "other_contract":"报告原页与所签验收单的合同编号不同，请核实归属。",
    "different":"同一合同下，报告原页编号与签名所引编号不同，请核实所指报告。",
    "matched":"已定位到报告号、合同号一致的原页，请核实检测范围和终验结论。",
}
EDGE_TYPES = {"requires_inspection_report", "inspection_attachment_page", "inspection_contract_number"}


def full_number(value):
    return isinstance(value, str) and NUMBER.fullmatch(value) is not None and not incomplete_number(value)


def requirement(row):
    if row["role"] not in ("acceptance", "reinspection"):
        return None
    match = REFERENCE.fullmatch(row["reason"].strip())
    if match:
        number = (match["number"] or "").strip()
        return match["kind"], number if full_number(number) else None
    return None


def native_page(raw, node=None, *, report=False):
    import pypdfium2 as pdfium
    from documents import MAX_EDGE, clause_text_only, layer_type, text_geometry
    from pdf_execution import PDFIUM_LOCK

    with PDFIUM_LOCK:
        with pdfium.PdfDocument(raw) as pdf:
            if len(pdf) != 1:
                if node is not None:
                    raise ValueError("检测报告核对所据的 PDF 页数与原件不符")
                return None
            page = pdf[0]
            try:
                layer = layer_type(page)
                typeset = layer == "text" and clause_text_only(page)
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_bounded()
                    lines = text.splitlines()
                    locations = {}
                    if report and typeset and any(line.strip() in TITLES for line in lines[:4]):
                        picture = page.render(scale=min(2.6, MAX_EDGE / max(page.get_size())))
                        try:
                            locations = text_geometry(text_page, text, picture, page)
                        finally:
                            picture.close()
                finally:
                    text_page.close()
            finally:
                page.close()
    if node is not None and (node.get("text_sha256") != sha256(text.encode()).hexdigest()
            or node.get("layer") != layer or node.get("clause_text_only") is not typeset):
        raise ValueError("检测报告核对所据的原页文字或版式与原件不符")
    return (lines, typeset, locations) if layer == "text" else None


def one_field(lines, labels, *, identifier=False):
    fields = []
    for n, line in enumerate(lines, 1):
        parts = re.split("[：:]", line, maxsplit=1)
        if identifier and PARTIAL.search(line) and any(line.strip().startswith(label) for label in (*labels, "编号说明")):
            return None
        if len(parts) == 2 and parts[0].strip() in labels:
            fields.append({"line":n, "quote":line, "value":parts[1].strip()})
    if len(fields) == 1:
        item, = fields
        if item["value"] and len(item["quote"]) <= 256 and (not identifier or full_number(item["value"])):
            return item
    return None


def attachment(doc, node, page):
    if not page or not page[1]:
        return None
    lines = page[0]
    headings = [(n, line) for n, line in enumerate(lines, 1) if line.strip() in TITLES]
    if len(headings) != 1:
        return None
    n, title = headings[0]
    locations = page[2]
    if n > 4 or not locations.get(str(n)):
        return None
    def located(labels, *, identifier=False):
        item = one_field(lines, labels, identifier=identifier)
        if item and (rects := locations.get(str(item["line"]))):
            return {**item, "rects":rects}
    return {"doc":doc["id"], "page":1, "original_sha256":doc["sha256"], "page_sha256":node["sha256"],
            "kind":TITLES[title.strip()], "title":{"line":n,"quote":title,"rects":locations[str(n)]},
            "number":located({"报告编号", "检测报告编号", "检验报告编号"}, identifier=True),
            "contract":located({"合同编号"}, identifier=True),
            "conclusion":located({"检测结论", "检验结论"})}


def signed_contract(graph, row, page):
    if not page:
        return None
    entry = one_field(page[0], {"合同编号"}, identifier=True)
    if not entry:
        return None
    all_facts = [f for f in graph["facts"] if f["doc"] == row["doc"] and f["field"] == "contract_id"]
    if len(all_facts) == 1:
        f, = all_facts
        loc = f.get("source_line") or {}
        if (f["status"] in ("anchored","confirmed") and f["page"] == 1 and f["source_sha256"] == row["original_sha256"]
                and f["value"] == entry["value"] and f["quote"] == loc.get("text") == entry["quote"]
                and loc.get("number") == entry["line"] and loc.get("rects")):
            return {**entry, "fact":f["id"]}
    return None


def classify(number, contract, candidates):
    if not candidates:
        return "unlocated"
    if not number:
        return "unidentified"
    if len(candidates) != 1:
        return "multiple"
    report, = candidates
    if not contract or not report["number"] or not report["contract"]:
        return "uncertain"
    if report["contract"]["value"] != contract["value"]:
        return "other_contract"
    return "matched" if report["number"]["value"] == number else "different"


def attach(graph, rows, read_original):
    required = [(row, req) for row in rows if (req := requirement(row))]
    if not required:
        return
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"] == "page"}
    owners = {row["doc"] for row, _ in required}
    receipts, candidates = {}, []
    for doc in graph["documents"]:
        if doc["ext"] != ".pdf" or doc.get("pages") != 1:
            continue
        node = nodes[doc["id"] + "/p1"]
        raw = read_original(doc)
        if sha256(raw).hexdigest() != doc["sha256"]:
            raise ValueError("检测报告核对所据的提交件摘要不符")
        page = native_page(raw, node, report=doc["id"] not in owners)
        if doc["id"] in owners:
            receipts[doc["id"]] = (raw, page)
        elif candidate := attachment(doc, node, page):
            candidates.append(candidate)
    for row, (kind, number) in required:
        raw, signed_page = receipts.get(row["doc"], (None, None))
        if raw and row.get("coverage") == "ENTIRE_REVISION":
            signed_page = native_page(raw[:row["ends_at"]])
        contract = signed_contract(graph, row, signed_page)
        reports = [c for c in candidates if c["kind"] == kind]
        row["report_reference"] = {
            "id":"inspection-report/" + row["id"].split("/", 1)[1], "kind":kind, "number":number,
            "signed_contract":contract, "candidates":reports, "state":classify(number, contract, reports),
        }


def sources(ref):
    yield ref["id"]
    if ref["signed_contract"]:
        yield ref["signed_contract"]["fact"]
    for doc in ref["candidates"]:
        yield doc["doc"]
        yield doc["doc"] + "/p1"


def relations(row, ref):
    yield {"from":row["id"], "to":ref["id"], "type":"requires_inspection_report", "evidence":[row["id"]]}
    if contract := ref["signed_contract"]:
        yield {"from":contract["fact"], "to":ref["id"], "type":"inspection_contract_number", "evidence":[contract["fact"]]}
    for doc in ref["candidates"]:
        page = doc["doc"] + "/p1"
        yield {"from":page, "to":ref["id"], "type":"inspection_attachment_page", "evidence":[doc["doc"],page]}
