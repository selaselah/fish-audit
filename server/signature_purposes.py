"""Keep the reason on a current PDF signature tied to the document it signs."""

from hashlib import sha256
from io import BytesIO
from itertools import islice
from unicodedata import normalize


KEY = "signature_purposes"
FORMAT = "signed-pdf-purpose-v1"
SINCE = (2026, 11, 28, 26)
ROLES = {"contract":"合同", "acceptance":"验收报告", "reinspection":"复验报告"}
QUANTITY_ONLY = {
    "仅确认到货数量", "本次签署仅确认到货数量", "仅确认到货数量,不代表终验合格",
    "仅确认到货数量,实际供货单位及终验质量仍待核对",
}


def reason_text(raw, name):
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    reader = PdfFileReader(BytesIO(raw), strict=True)
    fields = list(islice(enumerate_sig_fields(reader, filled_status=True), 2))
    if len(fields)!=1 or str(fields[0][0])!=name:
        return None
    reason = fields[0][1].get_object().get("/Reason")
    if isinstance(reason, generic.TextStringObject):
        text = str(reason)
        if 0<len(text)<=512 and text.strip() and not any(ord(c)<32 and c not in "\t\r\n" for c in text):
            return text
    return None


def sources(graph, read_original):
    if not read_original:
        return []
    kinds = graph.get("documents_by_kind", {})
    contracts = {r["doc"]:r for r in graph.get("pdf_execution_sources",{}).get("documents",[])}
    inspections = {r["unit"]:r for r in graph.get("acceptance_pdf_sources",{}).get("records",[])}
    if not contracts and not inspections:
        return []
    units = graph.get("audit_documents", graph["documents"])
    rows = []
    for doc in graph["documents"]:
        unit = doc["id"]
        if doc.get("ext")!=".pdf" or [d["id"] for d in units if d.get("source",d["id"])==unit]!=[unit]:
            continue
        roles = [k for k in ROLES if unit in kinds.get(k,())]
        if len(roles)!=1:
            continue
        role = roles[0]
        proof = contracts.get(unit) if role=="contract" else inspections.get(unit)
        if not proof or proof["state"]!="current" or len(proof["signatures"])!=1:
            continue
        sig, = proof["signatures"]
        if sig["state"]!="current" or sig.get("coverage")!="ENTIRE_FILE":
            continue
        raw = read_original(doc)
        if sha256(raw).hexdigest()!=doc["sha256"] or doc["sha256"]!=proof["original_sha256"] or sig["ends_at"]!=len(raw):
            raise ValueError("签名原因与签名覆盖的原件不符")
        reason = reason_text(raw,sig["field"])
        if reason:
            label = normalize("NFKC",reason).strip().removesuffix("。")
            rows.append({"id":"signature-purpose/"+unit,"doc":unit,"role":role,"source":proof["id"],
                         "original_sha256":doc["sha256"],"field":sig["field"],"revision":sig["revision"],
                         "certificate_sha256":sig["certificate_sha256"],"reason":reason,
                         "scope":"quantity_only" if label in QUANTITY_ONLY else "as_stated"})
    return rows


def source_graph(rows):
    nodes = [{"id":r["id"],"type":"pdf_signature_purpose","label":r["reason"],"doc":r["doc"]} for r in rows]
    edges = [{"from":r["source"],"to":r["id"],"type":"declares_signature_purpose","evidence":[r["doc"],r["source"]]} for r in rows]
    return nodes,edges


def cited(finding, rows):
    rule = finding["rule"]
    if rule not in ("H01","H02") and not (rule in ("H04","H05") and finding.get("stage")):
        return []
    return [r for r in rows if r["doc"] in finding["scope"] and r["source"] in finding["evidence"] and
            (rule!="H01" or r["role"]=="contract") and (rule!="H02" or r["role"]!="contract")]


def apply(graph, findings):
    rows = graph.get(KEY,{}).get("rows",[])
    for f in findings:
        used = cited(f,rows)
        if not used:
            continue
        f[KEY] = [r["id"] for r in used]
        f["evidence"] = list(dict.fromkeys([*f["evidence"],*(ref for r in used for ref in (r["doc"],r["id"]))]))
        for r in used:
            if r["scope"]=="quantity_only":
                action = "双方同意合同条款的签署依据" if r["role"]=="contract" else "性能、质量及终验范围的签认依据"
                f["detail"] += f" {ROLES[r['role']]}电子签名所填原因仅确认到货数量，请另核{action}。"
                if f["rule"] in ("H01","H02") and f["status"] in ("ok","missing"):
                    f["status"] = "risk"
                elif f["status"]=="ok":
                    f["status"] = "missing"


def verify(report, read_original, *, signing=False):
    graph, policy = report["graph"],report["policy"]
    nodes = [n for n in graph["nodes"] if n["type"]=="pdf_signature_purpose"]
    edges = [e for e in graph["edges"] if e["type"]=="declares_signature_purpose"]
    used_here = any(KEY in f for f in report["findings"])
    if tuple(map(int,policy.get("version","0").split(".")))<SINCE:
        if KEY in graph or KEY in policy or nodes or edges or used_here:
            raise ValueError("旧版底稿出现未出具的签名原因判断")
        if signing:
            restrictive = [r for r in sources(graph,read_original) if r["scope"]=="quantity_only"]
            if any(f["rule"] in ("H01","H02") and f["status"] in ("ok","missing") and cited(f,restrictive)
                   for f in report["findings"]):
                raise ValueError("签名属性明确仅确认到货数量，本版尚未核对该签署范围，请重新审计后签收。")
        return
    rows = sources(graph,read_original)
    if (graph.get(KEY)!=({"format":FORMAT,"rows":rows} if rows else None) or policy.get(KEY)!=(FORMAT if rows else None)
            or (nodes,edges)!=source_graph(rows)):
        raise ValueError("签名原因、所属原件或图谱关系与所签 PDF 不符")
    expert = report.get("calls",{}).get("expert") or {}
    procedures = expert.get("input",{}).get("procedures",[])
    declared = [p for p in procedures if KEY in p]
    if not rows and not used_here and not declared:
        return
    if "code_sha256" in policy and "signature_purposes.py" not in policy["code_sha256"]:
        raise ValueError("签名原因缺少出具时的规则源码")
    if len(declared)!=sum(bool(cited(f,rows)) for f in report["findings"]):
        raise ValueError("专家输入含有多余或缺失的 PDF 签名原因")
    links = {(e["from"],e["to"]) for e in graph["edges"] if e["type"]=="supports_result" and e["evidence"]==[e["from"]]}
    for f in report["findings"]:
        used = cited(f,rows)
        if f.get(KEY)!=([r["id"] for r in used] or None) or any(
                ref not in f["evidence"] or (ref,"finding/"+f["id"]) not in links for r in used for ref in (r["id"],r["doc"],r["source"])):
            raise ValueError("审计程序引用的签名原因与签署文件不符")
        if used and (not expert.get("response_id") or not any(p.get("rule")==f["rule"] and p.get("status")==f["status"] and
                p.get("observation")==f["detail"] and p.get("evidence")==f["evidence"] and p.get("stage")==f.get("stage")
                and p.get(KEY)==used for p in declared)):
            raise ValueError("专家检查与本项所据的签名原因不符")
