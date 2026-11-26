"""Bind an offline PDF signature integrity check to the exact contract original."""

from hashlib import sha256
from io import BytesIO
from itertools import islice

FORMAT = "pdf-execution-v1"
SINCE = "2026.11.26.14"
MAX_SIGNATURES = 24
DETACHED = {"/adbe.pkcs7.detached", "/ETSI.CAdES.detached"}

DETAIL = {
    "typeset": "PDF 签署页仅见排印内容，原件未检出嵌入式电子签名。请核对双方签署的纸本原页或对应版本的电子签署记录。",
    "visual": "原件未检出嵌入式电子签名，请核对签署页影像、双方主体及用印或授权依据。",
    "current": "电子签名校验覆盖本版 PDF。证书信任、签署人身份、代表权限及双方是否完成签署仍待核实。",
    "earlier": "电子签名覆盖较早的 PDF 版本。请核对后续修改和双方最终签署的版本。",
    "mismatch": "电子签名与其标记的已签内容校验不符，请核对签署平台原件和版本记录。",
    "review": "本次未能完整核验 PDF 的电子签名，请核对原件和签署平台记录。",
}


def signature(reader, field, value, name, size):
    from pyhanko.sign.validation.generic_cms import validate_sig_integrity
    from pyhanko.sign.validation.pdf_embedded import EmbeddedPdfSignature

    row = {"field": str(name)[:160], "state": "review"}
    try:
        obj = value.get_object()
        subfilter = str(obj.get("/SubFilter", ""))
        row["subfilter"] = subfilter[:64]
        if obj.get("/Type") == "/DocTimeStamp" or subfilter == "/ETSI.RFC3161":
            return {**row, "state": "timestamp"}
        if obj.get("/Type", "/Sig") != "/Sig" or subfilter not in DETACHED:
            return row
        embedded = EmbeddedPdfSignature(reader, field, str(name))
        if len(embedded.byte_range) != 4:
            return row
        ranges = list(embedded.byte_range)
        if any(not isinstance(value, int) for value in ranges):
            return row
        start, first, second, last = ranges
        if start != 0 or not 0 < first < second <= size or not 0 <= last <= size - second:
            return row
        info = embedded.signed_data["encap_content_info"]
        if (info["content_type"].native != "data" or info["content"].native is not None or
                embedded.md_algorithm not in {"sha256", "sha384", "sha512"}):
            return row
        coverage = embedded.evaluate_signature_coverage().name
        if coverage not in {"ENTIRE_FILE", "ENTIRE_REVISION"}:
            return row
        cert = embedded.signer_cert
        row.update(revision=embedded.signed_revision + 1, ends_at=second + last, digest=embedded.md_algorithm,
                   coverage=coverage, certificate_sha256=sha256(cert.dump()).hexdigest())
        intact, valid = validate_sig_integrity(embedded.signer_info, cert, "data", embedded.compute_digest())
        row["state"] = ("current" if coverage == "ENTIRE_FILE" else "earlier") if intact and valid else "mismatch"
        return row
    except Exception:
        # Unsupported encodings, certificates and algorithms all require review.
        return row


def inspect_original(raw):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    rows = []
    try:
        reader = PdfFileReader(BytesIO(raw), strict=True)
        if reader.encrypted:
            return "review", rows
        fields = list(islice(enumerate_sig_fields(reader, filled_status=True), MAX_SIGNATURES + 1))
        for name, value, field in fields[:MAX_SIGNATURES]:
            rows.append(signature(reader, field, value, name, len(raw)))
        states = {row["state"] for row in rows}
        if "mismatch" in states:
            return "mismatch", rows
        if len(fields) > MAX_SIGNATURES or "review" in states:
            return "review", rows
        if "current" in states:
            return "current", rows
        if "earlier" in states:
            return "earlier", rows
        return ("review" if rows else "unsigned"), rows
    except Exception:
        return "review", rows


def contracts(graph):
    units = set(graph.get("documents_by_kind", {}).get("contract", []))
    physical = {}
    for unit in graph.get("audit_documents", graph["documents"]):
        if unit["id"] in units:
            physical.setdefault(unit.get("source", unit["id"]), []).append(unit["id"])
    return [(doc, physical[doc["id"]]) for doc in graph["documents"]
            if doc["id"] in physical and doc.get("ext") == ".pdf"]


def sources(graph, read_original):
    documents = []
    for doc, units in contracts(graph):
        raw = read_original(doc) if read_original else None
        if raw is not None and sha256(raw).hexdigest() != doc["sha256"]:
            raise ValueError("PDF 签署检查的原件与入库摘要不符")
        state, signatures = inspect_original(raw) if raw is not None else ("review", [])
        documents.append({"id": "pdf-execution/" + doc["id"], "doc": doc["id"], "units": units,
                          "original_sha256": doc["sha256"], "size": len(raw) if raw is not None else None,
                          "state": state, "signatures": signatures})
    return {"format": FORMAT, "documents": documents}


def source_graph(ledger):
    nodes = [{"id": r["id"], "type": "pdf_signature_inspection", "label": "PDF 原件签署检查",
              "doc": r["doc"], "sha256": r["original_sha256"]} for r in ledger["documents"]]
    edges = [{"from": r["doc"], "to": r["id"], "type": "pdf_signature_source",
              "evidence": [r["doc"]]} for r in ledger["documents"]]
    return nodes, edges


def review(finding, graph, unit):
    ledger = graph.get("pdf_execution_sources", {})
    doc = next((r for r in ledger.get("documents", []) if unit in r["units"]), None)
    if not doc:
        return
    effect = graph["contract_effect_sources"]
    pages = [p for p in effect["pages"] if p["unit"] == unit and p["doc"] == doc["doc"]]
    rows = [r for r in effect.get("signing_rows", []) if r["unit"] == unit and r["doc"] == doc["doc"] and r["role"] == "signature"]
    state = doc["state"]
    if state == "unsigned":
        state = "typeset" if pages and all(p["native"] and p["text_only"] for p in pages) else "visual"
    page_refs = [f"{p['doc']}/p{p['page']}" for p in pages]
    refs = [doc["id"], doc["doc"], *page_refs, *(r["id"] for r in rows), *(ref for r in rows for ref in r["facts"])]
    finding["effect_review"]["pdf_execution"] = {"source": doc["id"], "unit": unit, "state": state,
                                                 "pages": page_refs, "rows": [r["id"] for r in rows]}
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *refs]))
    detail = DETAIL[state]
    if finding["status"] == "ok":
        finding["detail"] = detail
    else:
        finding["detail"] += " " + detail
    if state == "mismatch" and finding["status"] != "issue":
        finding["status"] = "risk"
    elif finding["status"] == "ok":
        finding["status"] = "missing"


def verify(report, read_original, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("pdf_execution")
    present = "pdf_execution_sources" in graph
    if not marker and not present:
        if policy.get("version", "") >= SINCE or "pdf_execution.py" in policy.get("code_sha256", {}):
            raise ValueError("本版缺少 PDF 签署检查")
        if signing and contracts(graph) and any(f["rule"] == "H01" and f["status"] == "ok" for f in report["findings"]):
            raise ValueError("旧版合同签署结论尚未核对 PDF 原件的签署凭证，请重审后签收。")
        return
    expected = sources(graph, read_original)
    nodes, edges = source_graph(expected)
    if (marker != FORMAT or graph.get("pdf_execution_sources") != expected or
            [n for n in graph["nodes"] if n["type"] == "pdf_signature_inspection"] != nodes or
            [e for e in graph["edges"] if e["type"] == "pdf_signature_source"] != edges):
        raise ValueError("PDF 签署凭证、原件摘要或图谱关系与实测不符")
