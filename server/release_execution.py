"""Identify what physically supports the signature on an acceptance-payment release."""

import original_records
from pdf_execution import unit_graph, unit_records


FORMAT = "payment-release-execution-v1"
SINCE = (2026, 11, 27, 11)
PDF = "release_pdf_sources"
NATIVE = "release_original_sources"
FAMILY = original_records.Family("release", ("payment_release",), "付款放行单", "付款放行单签认原件",
                                 ("approval_signer",), FORMAT)


def sources(graph, read_original, read_text):
    assigned = set(graph["documents_by_kind"].get("payment_release", ()))
    assigned.update(p["unit"] for p in graph.get("payment_release_sources", {}).get("pages", ()) if p["role"] == "release")
    scoped = {**graph, "documents_by_kind": {**graph["documents_by_kind"], "payment_release": sorted(assigned)}}
    pdf = unit_records(scoped, read_original, assigned, field="approval_signer", prefix="release-pdf", label="付款放行单 PDF ")
    return {PDF: {"format": FORMAT, "records": pdf}, NATIVE: original_records.sources(scoped, read_original, read_text, FAMILY)}


def source_graph(ledgers):
    pdf_nodes, pdf_edges = unit_graph(ledgers[PDF], "release_pdf", "付款放行单 PDF 签署凭证")
    nodes, edges = original_records.source_graph(ledgers[NATIVE], FAMILY)
    return pdf_nodes + nodes, pdf_edges + edges


def proposed(graph, contract, opinion, row, record):
    """Surface a candidate for the named phase even when its filing prevents schedule clearance."""
    from acceptance_payments import same_original
    from payment_releases import mandate

    if (PDF not in graph or opinion["state"] != "unresolved" or row["kind"] != "acceptance"
            or len(opinion["notes"]) != 1 or record is None or not same_original(contract, record)):
        return False
    note, = opinion["notes"]
    if (not note["line"] or note["stance"] != "hold" or note["target"] != "phase"
            or note["kind"] != "acceptance" or note["index"] != row["index"]):
        return False
    ledger = graph["payment_release_sources"]
    clauses = [r for r in ledger["lines"] if r["unit"] == contract.unit and r["role"] == "authority" and r["line"]]
    units = {p["unit"] for p in ledger["pages"] if p["role"] == "release"}
    return len(units) == 1 and len(clauses) == 1 and mandate(clauses[0]["quote"])[0] == row["index"]


def apply(check, graph):
    if PDF not in graph and NATIVE not in graph:
        return
    units = {p["unit"] for p in graph["payment_release_sources"]["pages"] if p["role"] == "release"} & set(check["units"])
    pdf = [r for r in graph[PDF]["records"] if r["unit"] in units]
    native = [r for r in graph[NATIVE]["records"] if r["unit"] in units]
    records = pdf + native
    check["signature_records"] = [r["id"] for r in records]
    check["signature_mismatch"] = any(r["state"] == "mismatch" for r in pdf)
    checked = [ref for r in records for ref in (r["id"], r["doc"], *(p["ref"] for p in r["pages"]), *r["fields"])]
    check["evidence"] = list(dict.fromkeys([*check["evidence"], *checked, *original_records.review_refs(native, graph[NATIVE])]))
    if check["state"] == "matched":
        check["state"] = "signature_pending"


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    checks = [r for f in report["findings"] if f["rule"] in ("H04", "H05") and (r := f.get("payment_opinion", {}).get("release"))]
    nodes = [n for n in graph["nodes"] if n["type"].startswith(("release_pdf_", "release_original_", "release_word_"))]
    edges = [e for e in graph["edges"] if e["type"].startswith(("release_pdf_", "release_original_", "release_word_"))]
    methods = policy.get("code_sha256", {})
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    marker = policy.get("release_execution")
    if marker is None:
        if (version >= SINCE or "release_execution.py" in methods or PDF in graph or NATIVE in graph or nodes or edges
                or any("signature_records" in r or "written_timing" in r for r in checks)):
            raise ValueError("底稿缺少付款放行单签署核验程序")
        if signing and any(r["state"] == "matched" for r in checks):
            raise ValueError("旧版底稿以签认栏文字确认付款放行，请按原件签署凭证重审后签收。")
        return
    if (version < SINCE or marker != FORMAT or "code_sha256" in policy and
            not {"release_execution.py", "pdf_execution.py", "original_records.py", "acceptance_comments.py"} <= methods.keys()):
        raise ValueError("付款放行单的签署核验程序或源码摘要不符")
    expected = sources(graph, read_original, read_text)
    if (any(graph.get(key) != ledger for key, ledger in expected.items())
            or (nodes, edges) != source_graph(expected)):
        raise ValueError("付款放行单原件、签署版本、批注或凭证关系不符")
    if signing:
        cited = {ref for r in checks for ref in r.get("signature_records", ())}
        records = [r for r in expected[NATIVE]["records"] if r["id"] in cited]
        pages = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
        for r in expected[PDF]["records"]:
            if r["id"] in cited:
                records.append({**r, "pages": [{**p, "layer": pages[p["ref"]]["layer"],
                                "text_only": pages[p["ref"]].get("clause_text_only") is True} for p in r["pages"]]})
        if records:
            original_records.verify_rendered(graph, records, read_original, FAMILY.label)
