"""Compare candidate signed observations with each evidenced invoice identifier in the current workpaper."""

from collections import defaultdict

from invoice_identity import InvoiceIdentities, printed
from invoice_masks import withheld_invoices
from invoice_proof import field_source, invoice_number_edges


FORMAT = "signed-invoice-identity-v1"


def archived_id(case_id,revision,fact):
    return f"prior/{case_id}/r{revision}/{fact}"


def archived_identity(identity,number,facts,page,text,signoff):
    observations = []
    case_id,rev = signoff["case_id"],signoff["rev"]
    for ref in identity["code_refs"]:
        code = facts[ref]
        if (code["doc"],code["page"],code.get("unit"),code["source_sha256"],code["page_sha256"]) != (
                number["doc"],number["page"],number.get("unit"),number["source_sha256"],number["page_sha256"]):
            raise ValueError("历史代码与票号的单据、原件或页图不一致")
        basis,line = "unverified",None
        if code["status"] in {"anchored","confirmed"}:
            if not printed(code["value"]) or printed(code["value"]) not in printed(code["quote"]):
                raise ValueError("历史发票代码缺少原文支持")
            source = field_source(code,page,text,signoff["time"])
            basis,line = source["basis"],source["line"]
            line_text = printed(code["quote"]).replace("：",":").rstrip("。;；")
            if (code["status"]=="anchored" and (basis!="native_line" or
                    line_text not in {"发票代码"+printed(code["value"]),"发票代码:"+printed(code["value"])})):
                raise ValueError("已定位的历史代码缺少原页代码标签或文字行")
        observations.append({"id":archived_id(case_id,rev,ref),"fact":ref,"doc":code["doc"],"page":code["page"],
                             "field":"invoice_code","value":code["value"],"quote":code["quote"],"status":code["status"],
                             "line":line,"basis":basis,"source_sha256":code["source_sha256"],"page_sha256":code["page_sha256"]})
    if identity["kind"]=="code_number" and any(c["basis"] not in {"native_line","field_check"} for c in observations):
        identity = {**identity,"kind":"short_unresolved","code":None}
    return {"identity":identity,"code_evidence":observations}


def lookup_numbers(graph):
    facts = {f["id"]:f for f in graph["facts"]}
    reader = InvoiceIdentities(graph)
    groups = defaultdict(set)
    for edge in invoice_number_edges(graph):
        for ref in edge["evidence"]:
            identity = reader.describe(facts[ref])
            key = edge["to"],identity["number"],identity["kind"],identity["code"] or ""
            groups[key].update([ref,*identity["code_refs"]])
    return [{"key":key,"value":number,"kind":kind,"code":code or None,"facts":sorted(refs)}
            for (key,number,kind,code),refs in sorted(groups.items())]


def compare(number,row):
    prior = row["identity"]
    if number["value"]!=prior["number"]:
        raise ValueError("签收候选中的号码与本案初筛条件不符")
    if "short_unresolved" in (number["kind"],prior["kind"]):
        return "uncertain"
    if number["code"]!=prior["code"]:
        return "different"
    return "uncertain" if row["document_kind"]=="unclassified" else "same"


def screen(numbers,rows):
    by_key = defaultdict(list)
    for number in numbers:
        by_key[number["key"]].append(number)
    result=[]
    for row in rows:
        states = {compare(number,row) for number in by_key[row["number_key"]]}
        if not states:
            raise ValueError("前案票号不在本次签收检索范围内")
        status = next(s for s in ("same","uncertain","different") if s in states)
        result.append({**row,"id":archived_id(row["case_id"],row["rev"],row["fact"]),"comparison":status})
    return sorted(result,key=lambda r:(r["case_id"],r["rev"],r["fact"]))


def actionables(rows):
    return [r for r in rows if r["comparison"]!="different"]


def code_relations(rows):
    nodes,edges = {},[]
    for row in rows:
        for code in row["code_evidence"]:
            ref = code["id"]
            node = {**code,"type":"archived_code","label":"发票代码"}
            if ref in nodes and nodes[ref]!=node:
                raise ValueError("同一历史代码引用了不同的原文")
            nodes[ref] = node
            edges.append({"from":ref,"to":row["id"],"type":"supports_invoice_code","evidence":[ref,row["id"]]})
    return list(nodes.values()),edges


def check_history(graph,record):
    historical=defaultdict(list)
    for row in graph["prior_invoices"]:
        historical[row["number_key"]].append(row)
    partial=withheld_invoices(graph)
    if partial:
        refs=[m["fact"] for m in partial]
        record("I02","missing","有票号含遮盖位或只列尾号，无法用这些引文对已签收底稿作完整标识查重。",
               refs,invoice_lookup={"withheld":refs,"candidates":[]})
    for number in lookup_numbers(graph):
        label = (number["code"]+" / " if number["code"] else "")+number["value"]
        candidates = historical[number["key"]]
        states = defaultdict(int)
        refs = number["facts"].copy()
        comparisons = []
        for row in candidates:
            comparison = compare(number,row)
            states[comparison]+=1
            comparisons.append({"id":row["id"],"comparison":comparison})
            refs.extend([row["id"],*(c["id"] for c in row["code_evidence"])])
        if candidates:
            detail = f"票据 {label} 在本企业已签收底稿中有 {len(candidates)} 处同号引文。"
            if states["same"]:
                detail += f"完整标识相同 {states['same']} 处，请核对前案签收、副本、补件及实际报销记录。"
            if states["uncertain"]:
                detail += f"有 {states['uncertain']} 处因代码或单据归属待核而无法判定。"
            if states["different"]:
                detail += f"双方同页代码不同，已排除 {states['different']} 处。"
        else:
            detail = f"票据 {label} 在本企业当时已签收底稿中未检出同号引文。"
        if number["kind"]=="short_unresolved":
            detail += "本案八位号码的同页代码仍待核准。"
        status = "risk" if states["same"] else "missing" if states["uncertain"] or number["kind"]=="short_unresolved" else "ok"
        record("I02",status,detail,refs,invoice_lookup={"number":number,"candidates":comparisons})
