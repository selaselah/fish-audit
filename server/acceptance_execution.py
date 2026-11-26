"""Distinguish a printed acceptance name from evidence of execution in the submitted PDF."""

from pdf_execution import apply_unit_records, unit_graph, unit_records

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


def sources(graph, read_original):
    kinds = graph.get("documents_by_kind", {})
    receipts = set(kinds.get("acceptance", ())) | set(kinds.get("reinspection", ()))
    return {"format": FORMAT, "records": unit_records(graph, read_original, receipts, field="acceptance_signer",
            prefix="acceptance-pdf", label="验收 PDF ")}


def source_graph(ledger):
    return unit_graph(ledger, "acceptance_pdf", "验收 PDF 签署凭证")


def relevant(graph, units):
    return [r for r in graph.get("acceptance_pdf_sources", {}).get("records", ()) if r["unit"] in units]


def apply(item, records):
    return apply_unit_records(item, records, "acceptance_execution", DETAIL)


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
