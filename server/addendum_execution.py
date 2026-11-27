"""Bind proposed changes to the PDF actually submitted for the supplementary agreement."""

from pdf_execution import unit_graph, unit_records

FORMAT = "pdf-addendum-execution-v1"
SINCE = (2026, 11, 27, 8)
KEY = "addendum_pdf_sources"
DETAIL = {
    "typeset": "补充协议 PDF 仅见排印内容，未检出嵌入式电子签名。请取得双方签署的协议原件或对应签署记录。",
    "visual": "补充协议 PDF 含影像、图形或批注。请对照双方签章原件并核实签署版本。",
    "current": "电子签名覆盖本版补充协议。双方签署人的身份、权限和对变更条款的同意仍需核验。",
    "earlier": "电子签名仅覆盖较早版本的补充协议。请核对最终协议及签署后的修改。",
    "mismatch": "补充协议的电子签名与所签内容校验不符。请取得签署平台原件并核对签署版本。",
    "review": "补充协议 PDF 的签署凭证仍需核对。请查验协议原件及双方签署记录。",
}


def sources(graph, read_original):
    units = set(graph["documents_by_kind"].get("contract_addendum", ()))
    return {"format": FORMAT, "records": unit_records(graph, read_original, units,
            field=("buyer_signature", "seller_signature"), prefix="addendum-pdf", label="补充协议 PDF ")}


def source_graph(ledger):
    return unit_graph(ledger, "addendum_pdf", "补充协议 PDF 签署凭证")


def bind(entry, graph, units):
    records = [r for r in graph.get(KEY, {}).get("records", ()) if r["unit"] in units]
    if records:
        entry["execution"] = [r["id"] for r in records]
        refs = [ref for r in records for ref in (r["id"], r["doc"], *(p["ref"] for p in r["pages"]), *r["fields"])]
        entry["evidence"] = list(dict.fromkeys([*entry["evidence"], *refs]))
    return " ".join(dict.fromkeys(DETAIL[r["state"]] for r in records))


def flag_mismatches(graph, findings):
    damaged = {r["id"]: r["unit"] for r in graph.get(KEY, {}).get("records", ()) if r["state"] == "mismatch"}
    if not damaged:
        return
    for finding in findings:
        change = finding.get("quality_change") or finding.get("payment_change") or {}
        if not any(ref in damaged and damaged[ref] in finding["scope"] for ref in change.get("execution", ())):
            continue
        if finding["status"] != "issue":
            finding["status"] = "risk"
        if DETAIL["mismatch"] not in finding["detail"]:
            finding["detail"] += " " + DETAIL["mismatch"]


def verify(report, read_original, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("addendum_pdf")
    nodes = [n for n in graph["nodes"] if n["type"] == "addendum_pdf_inspection"]
    edges = [e for e in graph["edges"] if e["type"] == "addendum_pdf_source"]
    changes = [f[key] for f in report["findings"] for key in ("quality_change", "payment_change") if f.get(key)]
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    if not marker:
        if (version >= SINCE or "addendum_execution.py" in policy.get("code_sha256", {}) or KEY in graph or
                nodes or edges or any("execution" in c for c in changes)):
            raise ValueError("本版缺少补充协议 PDF 签署凭证程序")
        if signing:
            applied = {unit for c in changes if c.get("effective_on") or c.get("state") in ("original", "applied", "by_batch")
                       or c.get("applies") in ("amended", "original") for unit in c.get("units", ())}
            if applied and any(r["unit"] in applied for r in sources(graph, read_original)["records"]):
                raise ValueError("旧版选用的变更条款或生效日期尚未核对补充协议 PDF 签署凭证，请重审后签收。")
        return
    expected = sources(graph, read_original)
    if (version < SINCE or marker != FORMAT or "code_sha256" in policy and "addendum_execution.py" not in policy["code_sha256"] or
            graph.get(KEY) != expected or (nodes, edges) != source_graph(expected)):
        raise ValueError("补充协议 PDF 的签署凭证、原件摘要或图谱关系不符")
