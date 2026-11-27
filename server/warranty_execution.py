"""Bind warranty certificate claims to the submitted signing version."""

import original_records
from pdf_execution import unit_graph, unit_records


FORMAT = "warranty-certificate-execution-v1"
SINCE = (2026, 11, 27, 13)
PDF, NATIVE = "warranty_pdf_sources", "warranty_original_sources"
FAMILY = original_records.Family("warranty", ("warranty",), "质保期满确认单", "期满确认单签认原件",
                                 ("acceptance_signer",), FORMAT)
DETAIL = {
    "typeset":"期满确认单的签认栏为排印文字，须取得实际签发依据。",
    "visual":"期满确认单含图形或影像，须核实签认痕迹及签署人。",
    "current":"电子签名覆盖本版期满确认单，仍须核对签署人身份和确认权限。",
    "earlier":"电子签名仅覆盖较早版本的期满确认单，请核对签后变更与最终签发稿。",
    "mismatch":"期满确认单的 PDF 电子签名与所签内容校验不符，请核对签署平台原件。",
    "word_text":"期满确认单为带排印签认栏的 Word 文件，请取得已签发的原件。",
    "word_visual":"期满确认单 Word 页含图形，签认痕迹与最终版本待核。",
    "word_review":"期满确认单 Word 含批注、修订或待核的审阅内容，请查最终签发稿。",
    "photo":"期满确认单为影像，请对照整页核实业务归属和签认。",
    "review":"期满确认单的原件版本、签署人及确认权限待核。",
    "scope_pending":"期满确认单的业务归属或最终版本待核。",
}


def sources(graph, read_original, read_text):
    units = set(graph["documents_by_kind"].get("warranty", ()))
    records = unit_records(graph, read_original, units, field="acceptance_signer",
                           prefix="warranty-pdf", label="期满确认单 PDF ")
    return {PDF:{"format":FORMAT, "records":records}, NATIVE:original_records.sources(graph, read_original, read_text, FAMILY)}


def source_graph(ledgers):
    a, b = unit_graph(ledgers[PDF], "warranty_pdf", "期满确认单 PDF 签署凭证")
    c, d = original_records.source_graph(ledgers[NATIVE], FAMILY)
    return a + c, b + d


def certificate(graph, contract, releases):
    from acceptance_payments import same_original

    units = {r.unit for r in releases}
    pdf = [r for r in graph.get(PDF, {}).get("records", ()) if r["unit"] in units]
    native = [r for r in graph.get(NATIVE, {}).get("records", ()) if r["unit"] in units]
    records = pdf + native
    if not records:
        return None
    linked = len(records) == len(releases) == 1 and records[0]["unit"] == releases[0].unit and same_original(contract, releases[0])
    state = records[0]["state"] if linked else "scope_pending"
    refs = [ref for r in records for ref in (r["id"], r["doc"], *(p["ref"] for p in r["pages"]), *r["fields"])]
    return {"records":[r["id"] for r in records], "state":state, "linked":linked,
            "evidence":list(dict.fromkeys([*refs, *original_records.review_refs(native, graph[NATIVE])]))}


def attach(finding, check, *, paid=None):
    cert = check.get("certificate")
    if not cert:
        return
    state = cert["state"]
    status = "risk" if state == "mismatch" else "missing"
    reasons = [DETAIL[state]]
    stated = check["stated_on"]
    if cert["linked"]:
        # Carry documentary conflicts even when a different prerequisite is still pending.
        cutoff = check.get("at_submission", {}).get("as_of")
        if cutoff and stated and stated > cutoff:
            status = "risk"
            reasons.append(f"期满确认原件列示日期 {stated} 晚于资料提交日 {cutoff}，需核实实际发生日期。")
        if stated and check["calendar_end"] and stated < check["calendar_end"]:
            status = "risk"
            reasons.append(f"确认单于 {stated} 记载期满，早于按合同复算的 {check['calendar_end']}。")
        if check["defect_open"] and check["requires_defect_clearance"]:
            status = "risk"
            reasons.append("期满确认单仍列有未解决质量问题，需核实关闭情况及质保金可否返还。")
        if paid and stated and paid < stated:
            status = "risk"
            reasons.append(f"回单付款日 {paid} 早于确认单所列期满日 {stated}，请核查提前返还依据。")
        elif paid and paid == stated:
            reasons.append("付款与单上所列期满日同日，请核实当天签批与支付时分。")
    if finding["status"] == "ok" or finding["status"] == "missing" and status == "risk":
        finding["status"] = status
    for reason in reasons:
        if reason not in finding["detail"]:
            finding["detail"] += " " + reason


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    methods = policy.get("code_sha256", {})
    marker = policy.get("warranty_execution")
    checks = [f for f in report["findings"] if f["rule"] in ("H04","H05") and f.get("warranty_check")]
    prefixes = ("warranty_pdf_", "warranty_original_", "warranty_word_")
    nodes = [n for n in graph["nodes"] if n["type"].startswith(prefixes)]
    edges = [e for e in graph["edges"] if e["type"].startswith(prefixes)]
    if marker is None:
        if (version >= SINCE or "warranty_execution.py" in methods or PDF in graph or NATIVE in graph or nodes or edges
                or any("certificate" in f["warranty_check"] or "stated_on" in f["warranty_check"] for f in checks)):
            raise ValueError("底稿缺少期满确认单原件签署程序")
        if signing and any(f["warranty_check"].get("confirmed_on") and
                           "ok" in (f["status"], f["warranty_check"]["status"]) for f in checks):
            originals = sources(graph, read_original, read_text)
            for record in originals[PDF]["records"] + originals[NATIVE]["records"]:
                if any(f["warranty_check"].get("confirmed_on") and "ok" in (f["status"], f["warranty_check"]["status"])
                       and record["unit"] in f["scope"] and set(record["fields"]).intersection(f["evidence"]) for f in checks):
                    raise ValueError("旧版质保金相符判断所据期满确认单尚未核对签发原件，请重审后签收。")
        return
    if (version < SINCE or marker != FORMAT or "code_sha256" in policy and
            not {"warranty_execution.py", "original_records.py", "pdf_execution.py", "acceptance_comments.py"} <= methods.keys()):
        raise ValueError("期满确认单原件程序或源码摘要不符")
    expected = sources(graph, read_original, read_text)
    if any(graph.get(k) != v for k,v in expected.items()) or (nodes, edges) != source_graph(expected):
        raise ValueError("期满确认单签署版本、审阅层、物理原页或证据关系不符")
    if signing:
        cited = {ref for f in checks for ref in f["warranty_check"].get("certificate", {}).get("records", ())}
        original_records.verify_filed(graph, expected[PDF], expected[NATIVE], cited, read_original, FAMILY.label)
