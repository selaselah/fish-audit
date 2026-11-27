"""Read a contractually required board decision from its own filed version and original rows."""

import re
import unicodedata

import original_records
from delegation import complete_id, native_value
from pdf_execution import unit_graph, unit_records


FORMAT = "board-decision-execution-v1"
SINCE = (2026, 11, 27, 15)
PDF, NATIVE = "board_pdf_sources", "board_original_sources"
FAMILY = original_records.Family("board", ("contract_approval",), "董事会审批单", "董事会审批单签认原件",
                                 ("approval_signer",), FORMAT)
DETAIL = {
    "typeset":"审批单签认栏仅见排印文字，请取得签发原件或对应签署记录。",
    "visual":"审批单 PDF 含图形或扫描内容，请核对签认痕迹、批准范围和签发人。",
    "current":"PDF 电子签名覆盖本版审批单，签署人身份、议决权限及最终决议仍待查验。",
    "earlier":"PDF 电子签名覆盖较早版本，请核对签后变更及最终表决文本。",
    "mismatch":"审批单的 PDF 电子签名与所签内容校验不符，请查签署平台原件及版本。",
    "word_text":"Word 审批单签认栏为排印文字，请取得签认定稿或对应签署记录。",
    "word_visual":"Word 审批单含图形，请核对签认痕迹与最终表决文本。",
    "word_review":"Word 审批单含批注、修订或待核的审阅内容，请查最终决议及其批准范围。",
    "photo":"审批单为影像，请查原页所属合同、审批机构与签认原件。",
    "review":"审批单的签发版本、签认与决议权限待核。",
    "multiple":"本案所附审批资料尚须逐份核对所属合同和最终决议。",
}


def sources(graph, read_original, read_text):
    units = set(graph["documents_by_kind"].get("contract_approval", ()))
    records = unit_records(graph, read_original, units, field="approval_signer",
                           prefix="board-pdf", label="董事会审批单 PDF ")
    return {PDF:{"format":FORMAT, "records":records}, NATIVE:original_records.sources(graph, read_original, read_text, FAMILY)}


def source_graph(ledgers):
    pdf_nodes, pdf_edges = unit_graph(ledgers[PDF], "board_pdf", "董事会审批单 PDF 签署凭证")
    nodes, edges = original_records.source_graph(ledgers[NATIVE], FAMILY)
    return pdf_nodes + nodes, pdf_edges + edges


def original_row(material, key, *, approval=False):
    from contract_effect import approval_field
    from performance import LABELS, SOURCE_LABELS

    facts = material.fields[key]
    if len(facts) != 1 or material.incomplete(key):
        return None
    fact = facts[0]
    line = fact.get("source_line") or {}
    value = native_value(fact, LABELS.get(key) or SOURCE_LABELS.get(key, ()))
    if (not value or not isinstance(line.get("number"), int) or line["number"] < 1
            or approval and not approval_field(line["text"], fact)):
        return None
    return fact["id"], unicodedata.normalize("NFKC",value)


def decision(graph, contract, approvals, party):
    if not graph or PDF not in graph:
        return None
    units = {a.unit for a in approvals}
    pdf = [r for r in graph[PDF]["records"] if r["unit"] in units]
    native = [r for r in graph[NATIVE]["records"] if r["unit"] in units]
    records = pdf + native
    if not records:
        return None
    fields = {}
    contract_rows = {k:original_row(contract,k) for k in ("effect_clause","contract_id","buyer","seller")}
    if contract_rows["effect_clause"]:
        fields["effect_clause"] = contract_rows["effect_clause"][0]
    linked = False
    unique = len(approvals) == len(records) == 1
    if unique:
        rows = {k:original_row(approvals[0],k,approval=True) for k in
                ("contract_id","buyer","seller","approval_authority","approval_result","approved_on","approval_signer")}
        fields.update({k:row[0] for k,row in rows.items() if row})
        ids = ("contract_id","buyer","seller")
        side = "buyer" if party in ("甲方","采购方") else "seller"
        linked = bool(all(contract_rows.values()) and all(rows[k] and contract_rows[k][1] == rows[k][1] for k in ids)
                      and complete_id(rows["contract_id"][1]) and not re.search(r"\s", rows["contract_id"][1])
                      and rows["approval_authority"] and rows["approval_authority"][1] == contract_rows[side][1]+"董事会")
    refs = [ref for r in records for ref in (r["id"], r["doc"], *(p["ref"] for p in r["pages"]), *r["fields"])]
    refs.extend(row[0] for row in contract_rows.values() if row)
    return {"state":records[0]["state"] if unique else "multiple", "linked":linked, "records":[r["id"] for r in records],
            "fields":fields, "evidence":list(dict.fromkeys([*refs,*fields.values(),*original_records.review_refs(native,graph[NATIVE])]))}


def review(status, note, check):
    state = check["state"]
    if status == "ok":
        status = "missing"
        note = ("审批单所列机构与合同所约董事会相符，决定栏列有批准。" if check["linked"] and "approval_result" in check["fields"]
                else "请先核对审批单所属合同、审批机构与决定原行。")
    if state == "mismatch":
        status = "risk"
    return status, note+" "+DETAIL[state]


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    methods = policy.get("code_sha256", {})
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    findings = [f for f in report["findings"] if f["rule"] == "H01"]
    checks = [f["effect_review"]["board_decision"] for f in findings if "board_decision" in f.get("effect_review", {})]
    prefixes = ("board_pdf_", "board_original_", "board_word_")
    nodes = [n for n in graph["nodes"] if n["type"].startswith(prefixes)]
    edges = [e for e in graph["edges"] if e["type"].startswith(prefixes)]
    marker = policy.get("board_decision")
    if marker is None:
        if version >= SINCE or "board_execution.py" in methods or PDF in graph or NATIVE in graph or nodes or edges or checks:
            raise ValueError("底稿缺少董事会决议原件核验程序")
        units = set(graph["documents_by_kind"].get("contract_approval", ()))
        if signing and any(units.intersection(f["scope"]) and (f["status"] == "ok" or "董事会批准决定、日期和签认已有材料支持" in f["detail"]) for f in findings):
            raise ValueError("旧版批准判断所据董事会审批单尚未核对签发原件，请重审后签收。")
        return
    if (marker != FORMAT or version < SINCE or "code_sha256" in policy and
            not {"board_execution.py","pdf_execution.py","original_records.py","acceptance_comments.py"} <= methods.keys()):
        raise ValueError("董事会决议原件程序或源码摘要不符")
    expected = sources(graph, read_original, read_text)
    if any(graph.get(k) != v for k,v in expected.items()) or (nodes, edges) != source_graph(expected):
        raise ValueError("董事会审批单签署版本、审阅原文、物理页或图谱关系不符")
    if signing:
        cited = {ref for check in checks for ref in check["records"]}
        original_records.verify_filed(graph, expected[PDF], expected[NATIVE], cited, read_original, FAMILY.label)
