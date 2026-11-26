"""Distinguish a printed acceptance name from evidence of execution in the submitted PDF."""

from collections import defaultdict
from hashlib import sha256

from pdf_execution import PDFIUM_LOCK, inspect_original

FORMAT = "pdf-acceptance-execution-v1"
SINCE = (2026, 11, 26, 27)
DETAIL = {
    "typeset": "验收 PDF 仅见排印内容，未检出嵌入式电子签名。需核对带签认痕迹的验收原件或对应签署记录。",
    "visual": "验收 PDF 含影像、图形或批注，签字栏的独立签认痕迹仍待对照原件核实。",
    "current": "电子签名覆盖本版验收 PDF，须核实签署人的身份、权限及其签认的验收范围。",
    "earlier": "电子签名只覆盖较早版本的验收 PDF，需取得最终签认版本并核对变更。",
    "mismatch": "验收 PDF 的电子签名与已签内容校验不符，需核对签署平台原件。",
    "review": "验收 PDF 的签署凭证尚未完整核实，需核对原件及签署记录。",
}


def page_content(raw, expected):
    import pypdfium2 as pdfium
    from documents import clause_text_only, layer_type

    # PDFium is not thread-safe. The web server can receive multiple signing requests at once.
    with PDFIUM_LOCK:
        try:
            with pdfium.PdfDocument(raw) as pdf:
                if len(pdf) != expected:
                    return {}
                contents = {}
                for i in range(len(pdf)):
                    page = pdf[i]
                    try:
                        layer = layer_type(page)
                        text = page.get_textpage()
                        try:
                            has_text = text.count_chars()>0
                        finally:
                            text.close()
                        contents[i+1] = {"layer":layer,"has_text":has_text,"typeset":layer=="text" and clause_text_only(page)}
                    finally:
                        page.close()
                return contents
        except (ValueError, OSError, RuntimeError, pdfium.PdfiumError):
            return {}


def sources(graph, read_original):
    from config import MAX_PAGES

    kinds = graph.get("documents_by_kind", {})
    receipts = set(kinds.get("acceptance", ())) | set(kinds.get("reinspection", ()))
    units = defaultdict(list)
    for unit in graph.get("audit_documents", graph["documents"]):
        if unit["id"] in receipts:
            units[unit.get("source", unit["id"])].append(unit)
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    rows = []
    for doc in graph["documents"]:
        if doc.get("ext")!=".pdf" or doc["id"] not in units:
            continue
        count = doc.get("pages")
        if count is None:
            count = sum(ref.startswith(doc["id"]+"/p") for ref in nodes)
        if type(count) is not int or not 1<=count<=MAX_PAGES:
            raise ValueError("验收 PDF 页数与可核对的原页范围不符")
        raw = read_original(doc) if read_original else None
        if raw is not None and sha256(raw).hexdigest()!=doc["sha256"]:
            raise ValueError("验收 PDF 原件与入库摘要不符")
        integrity, signatures = inspect_original(raw) if raw is not None else ("review", [])
        contents = page_content(raw, count) if raw is not None else {}
        for unit in units[doc["id"]]:
            numbers = [unit["page"]] if "source" in unit else range(1,count+1)
            pages = {}
            for number in numbers:
                key = f"{doc['id']}/p{number}"
                page = nodes.get(key)
                if not page:
                    raise ValueError("验收签认所据物理页缺失")
                pages[number] = {"ref":key,"sha256":page["sha256"],**contents.get(number, {"layer":"unknown","has_text":False,"typeset":False})}
            fields = [f for f in graph["facts"] if (f.get("unit") or f["doc"])==unit["id"]
                      and f["doc"]==doc["id"] and f["page"] in pages and f["field"]=="acceptance_signer"]
            state = integrity if contents else "review"
            if state=="unsigned":
                if all(p["typeset"] for p in pages.values()):
                    state = "typeset" if any(p["has_text"] for p in pages.values()) else "review"
                else:
                    state = "visual"
            rows.append({"id":"acceptance-pdf/"+unit["id"],"unit":unit["id"],"doc":doc["id"],
                         "original_sha256":doc["sha256"],"state":state,"signatures":signatures,
                         "pages":list(pages.values()),"fields":[f["id"] for f in fields]})
    return {"format":FORMAT,"records":rows}


def source_graph(ledger):
    nodes, edges = [], []
    for row in ledger["records"]:
        nodes.append({"id":row["id"],"type":"acceptance_pdf_inspection","label":"验收 PDF 签署凭证",
                      "doc":row["doc"],"sha256":row["original_sha256"],"state":row["state"]})
        refs = [row["doc"], *(p["ref"] for p in row["pages"]), *row["fields"]]
        edges.append({"from":row["unit"],"to":row["id"],"type":"acceptance_pdf_source","evidence":refs})
    return nodes, edges


def relevant(graph, units):
    return [r for r in graph.get("acceptance_pdf_sources", {}).get("records", ()) if r["unit"] in units]


def apply(item, records):
    if not records:
        return False
    refs = [ref for r in records for ref in (r["id"],r["doc"],*(p["ref"] for p in r["pages"]),*r["fields"])]
    item["acceptance_execution"] = [r["id"] for r in records]
    item["evidence"] = list(dict.fromkeys([*item["evidence"],*refs]))
    details = list(dict.fromkeys(DETAIL[r["state"]] for r in records))
    if item["status"]=="ok":
        item.update(status="missing",detail=" ".join(details))
    else:
        item["detail"] += "".join(" "+d for d in details if d not in item["detail"])
    if item["status"]!="issue" and any(r["state"]=="mismatch" for r in records):
        item["status"] = "risk"
    return True


def verify(report, read_original, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("acceptance_pdf")
    nodes = [n for n in graph["nodes"] if n["type"]=="acceptance_pdf_inspection"]
    edges = [e for e in graph["edges"] if e["type"]=="acceptance_pdf_source"]
    if not marker:
        version = tuple(map(int,(policy.get("version") or "0").split(".")))
        if (version>=SINCE or "acceptance_execution.py" in policy.get("code_sha256", {}) or nodes or edges or
                "acceptance_pdf_sources" in graph or any("acceptance_execution" in f for f in report["findings"])):
            raise ValueError("缺少本版验收 PDF 签署凭证程序")
        if signing:
            positives = [f for f in report["findings"] if f["rule"] in ("H02","H04","H05") and f["status"]=="ok"]
            if positives:
                for r in sources(graph, read_original)["records"]:
                    basis = set(r["fields"]) | {p["ref"] for p in r["pages"]}
                    if r["state"] in DETAIL and any(basis.intersection(f["evidence"]) or
                            f["rule"]=="H02" and r["unit"] in f.get("scope",()) for f in positives):
                        raise ValueError("旧版验收或付款相符结论尚未核对验收 PDF 签署凭证，请重审后签收。")
        return
    if policy.get("code_sha256") is not None and "acceptance_execution.py" not in policy["code_sha256"]:
        raise ValueError("验收 PDF 签署程序缺少归档源码摘要")
    expected = sources(graph, read_original)
    if marker!=FORMAT or graph.get("acceptance_pdf_sources")!=expected or (nodes,edges)!=source_graph(expected):
        raise ValueError("验收 PDF 签署凭证、物理页或图谱关系与原件不符")
