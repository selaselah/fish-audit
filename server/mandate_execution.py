"""Bind a written delegation's execution evidence to its own PDF, principal and signing decision."""

from pdf_execution import apply_unit_records, unit_graph, unit_records


FORMAT = "pdf-mandate-execution-v1"
SINCE = (2026, 11, 27, 2)
DETAIL = {
    "typeset": "委托书 PDF 仅见排印内容，未检出嵌入式电子签名。请核对被代理人签名或盖章的原件或对应签署记录。",
    "visual": "委托书 PDF 含影像、图形或批注。请对照被代理人的签章栏及用印记录，核实该委托书的签发。",
    "current": "电子签名覆盖本版委托书 PDF。请核对证书信任、签署人身份及其代表被代理人签发委托书的权限。",
    "earlier": "电子签名覆盖较早版本的委托书 PDF。请核对签发时的授权范围与最终版本的变更。",
    "mismatch": "委托书 PDF 的电子签名与所签内容校验不符，请核对签署平台原件及版本记录。",
    "review": "委托书 PDF 的签署凭证尚未完整核验，请核对原件及被代理人的签发记录。",
}


def sources(graph, read_original):
    grants = set(graph.get("documents_by_kind", {}).get("power_of_attorney", ()))
    return {"format": FORMAT, "records": unit_records(graph, read_original, grants, field="grant_signature",
            prefix="mandate-pdf", label="委托书 PDF ")}


def source_graph(ledger):
    return unit_graph(ledger, "mandate_pdf", "授权委托书 PDF 签章凭证")


def review(entries, records):
    for entry in entries:
        relevant = [row for row in records if row["unit"] in entry["units"]]
        apply_unit_records(entry, relevant, "mandate_execution", DETAIL)


def verify(report, read_original, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    nodes = [n for n in graph["nodes"] if n["type"] == "mandate_pdf_inspection"]
    edges = [e for e in graph["edges"] if e["type"] == "mandate_pdf_source"]
    entries = [e for f in report["findings"] if f["rule"] == "H01" for e in f.get("delegations", ())]
    marker = policy.get("mandate_pdf")
    if not marker:
        version = tuple(map(int, (policy.get("version") or "0").split(".")))
        if (version >= SINCE or "mandate_execution.py" in policy.get("code_sha256", {}) or
                "mandate_pdf_sources" in graph or nodes or edges or any("mandate_execution" in e for e in entries)):
            raise ValueError("缺少本版委托书 PDF 签章凭证程序")
        if signing:
            approved = {unit for e in entries if e["status"] == "ok" for unit in e["units"]}
            positives = [f for f in report["findings"] if f["rule"] in ("H01", "H04", "H05") and f["status"] == "ok"]
            if approved or positives:
                for row in sources(graph, read_original)["records"]:
                    if row["unit"] in approved or any(row["unit"] in f.get("scope", ()) and
                            set(row["fields"]).intersection(f["evidence"]) for f in positives):
                        raise ValueError("旧版相符结论所据委托书 PDF 尚未核对被代理人的签章凭证，请重审后签收。")
        return
    if policy.get("code_sha256") is not None and "mandate_execution.py" not in policy["code_sha256"]:
        raise ValueError("委托书 PDF 签章程序缺少归档源码摘要")
    expected = sources(graph, read_original)
    if marker != FORMAT or graph.get("mandate_pdf_sources") != expected or (nodes, edges) != source_graph(expected):
        raise ValueError("委托书 PDF 签章凭证、物理页或图谱关系与原件不符")
