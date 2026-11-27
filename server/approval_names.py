"""Compare the payment approvers named in a particular contract clause and approval sheet."""
from hashlib import sha256
import re

from delegation import is_page_marker
from delivery_batches import NUM, ordinal
from payment_acceptance import column
from payment_quality import printed, readings

HEADINGS = {"付款签批约定", "付款审批人约定"}
SIGNERS = {"签批人姓名", "审批人姓名", "实际签批人"}
NAME = r"[\u3400-\u9fff]{2,8}"
CLAUSE = re.compile(r"第("+NUM+r")期(验收款|预付款|质保金)须由("+NAME+r"?)(?:签批|[与、]("+NAME+r"?)共同签批)[。]?")
# A separate delegation or qualification may change who can act for this installment.
QUALIFIER = re.compile(r"签批|审批人|会签|代签|代批|另行|另有|除外|豁免|授权|委托|变更|撤销|作废|补充|替代")
ORDINARY = {"contract","bank_receipt","acceptance","reinspection","remediation","warranty"}
WORDING = {
    "listed":"合同点名与审批单签批栏所列姓名相符。本人是否签批、权限及授权变更仍待核。",
    "different":"合同对本期点名的人员与审批单签批栏所列人员不同，请查替代授权及实际签批依据。",
    "partial":"合同要求两人共同签批，审批单仅列其中一人，另一人的签批依据待补。",
    "missing":"合同对本期明确点名签批人，所附审批单尚无可逐字对应的具名栏。",
    "other_stage":"合同具名条款指向另一笔期款，当前付款仍须单独核实权限。",
    "scope":"合同具名条款的范围、版本或签批名单待核，请对照完整原件及授权变更。",
}


def name(value):
    from acceptance_authority import person
    return bool(re.fullmatch(NAME,value) and person(value) and not re.search(r"或|以及|共同|及其|授权|任选|两人|任一|另见|同上|详见|任何|其他|全体|双方|其本人|签批人|审批人|当事人|经授权|等$",value))


def payment_only(quote):
    label,value=column(quote)
    m=CLAUSE.fullmatch(value) if label in HEADINGS else None
    return bool(m and not re.search(r"验收|复验|终验|签认|签字",m[3]+(m[4] or "")))


def clause(quote):
    label,value=column(quote)
    m=CLAUSE.fullmatch(value) if label in HEADINGS else None
    if not m or not ordinal(m[1]):
        return None
    names=[m[3],m[4]] if m[4] else [m[3]]
    if len(set(names))!=len(names) or not all(name(n) for n in names):
        return None
    return ordinal(m[1]),m[2],names


def listed(value):
    names=value.split("、")
    return names if len(names) in (1,2) and len(set(names))==len(names) and all(name(n) for n in names) else None


def pages(graph, read_text, read_layout):
    from graph import LABELS, PRINTED_TITLES
    from performance import STAGE_PREFIX

    known={label for labels in LABELS.values() for label in labels}
    docs={d["id"]:d for d in graph["documents"]}
    nodes={n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    result=[]
    for p in graph.get("payment_window_sources",{}).get("pages",()):
        if p["document_kind"]!="contract" or not p["native"]:
            continue
        doc,pg=p["doc"],p["page"]
        source=docs[doc];node=nodes[f"{doc}/p{pg}"]
        text=read_text(doc,pg)
        if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=node["text_sha256"]:
            raise ValueError("合同签批约定所据原页与归档文字不符")
        lines=[(i,raw) for i,raw in enumerate(text.splitlines(),1) if raw.strip() and not is_page_marker(raw)]
        if not any(column(raw)[0] in HEADINGS for _,raw in lines):
            continue
        facts=[f for f in graph["facts"] if f["doc"]==doc and f["page"]==pg]
        complete=(p["unit"]==doc and pg==1 and source.get("ext")==".pdf" and source.get("pages")==1 and p["text_only"]
                  and PRINTED_TITLES.get(lines[0][1].strip())=="contract" and not any(f["status"]=="disputed" for f in facts)
                  and not any(g["doc"]==doc and g.get("quality") in {"partial","unreadable","section_unresolved"} for g in graph.get("gaps",())))
        layout=read_layout(doc,pg).get("lines",{})
        rows=[]
        for i,raw in lines:
            label,_=column(raw)
            if label in HEADINGS:
                field="named_clause"
            elif QUALIFIER.search(raw) or (raw.strip() not in PRINTED_TITLES and label not in known and not STAGE_PREFIX.match(printed(raw))):
                field="qualification"
            else:
                continue
            observed=[f["id"] for f in facts if (f.get("source_line") or {}).get("number")==i and f["source_line"]["text"]==raw]
            rows.append({"id":f"contract-approver/{doc}/p{pg}/l{i}","doc":doc,"page":pg,"unit":p["unit"],"line":i,
                         "field":field,"quote":raw,"facts":observed,"rects":layout.get(str(i),[]),"page_sha256":node["sha256"]})
        result.append({"doc":doc,"page":pg,"unit":p["unit"],"complete":complete,"rows":rows})
    return result


def stage_terms(graph,unit):
    entries=[]
    for p in graph.get("inspection_use_sources",{}).get("approver_terms",()):
        if p["unit"]==unit and p["complete"]:
            for r in p["rows"]:
                if r["field"]=="named_clause" and r["rects"] and (term:=clause(r["quote"])):
                    entries.append((r,term[0],{"验收款":"acceptance","质保金":"warranty","预付款":"effect"}[term[1]]))
    return entries


def apply_conditions(graph,findings):
    from performance import stage_terms as parse_stage

    units=graph["documents_by_kind"].get("contract",())
    if len(units)!=1:
        return
    terms=stage_terms(graph,units[0])
    if not terms:
        return
    for f in findings:
        stage=f.get("stage")
        if f["rule"] not in {"H04","H05"} or not stage:
            continue
        m=re.fullmatch("第("+NUM+")期",stage["name"])
        kind=parse_stage(stage["clause"])[1]
        rows=[r for r,index,category in terms if m and ordinal(m[1])==index and category==kind]
        if rows:
            f["stage_approvers"]=[r["id"] for r in rows]
            f["evidence"]=list(dict.fromkeys([*f["evidence"],stage["clause_ref"],*(ref for r in rows for ref in (r["id"],f"{r['doc']}/p{r['page']}",*r["facts"]))]))
            if not f.get("inspection_use",{}).get("approval",{}).get("names"):
                if f["status"]=="ok":
                    f["status"]="missing"
                f["detail"]+=" 合同另列本期具名签批约定，需核对审批原件、实际签批人及其权限。"


def compare(graph, finding, approval, fields, values):
    from performance import Material

    pages=graph["inspection_use_sources"].get("approver_terms",())
    if not pages or approval["state"] not in {"earlier","later","same_day","refused"}:
        return None
    rows=[r for p in pages for r in p["rows"]]
    for p in pages:
        approval["evidence"].append(f"{p['doc']}/p{p['page']}")
    for row in rows:
        approval["evidence"].extend([row["id"],*row["facts"]])
    signer=fields.get("signed_by")
    record={"rows":[r["id"] for r in rows],"signed_by":signer["id"] if signer else None,"state":"scope"}
    kinds=graph["documents_by_kind"]
    if len(pages)!=1 or len(rows)!=1 or not pages[0]["complete"] or not rows[0]["rects"] or rows[0]["field"]!="named_clause":
        return record
    row=rows[0];term=clause(row["quote"])
    units={u for role in ORDINARY for u in kinds.get(role,())} | set(approval["documents"])
    if (not term or kinds.get("contract")!=[row["unit"]] or units!={d["id"] for d in graph["documents"]}
            or any(v for k,v in kinds.items() if k not in ORDINARY and k!="other")):
        return record
    proof=graph.get("retest_reference_sources",{}).get("rows") or graph.get("payment_quality_sources",{}).get("rows",())
    material=Material(graph,row["unit"])
    ids=readings(proof,material,("contract_id","buyer","seller"))
    if not ids or any(column(material.fields[k][0]["source_line"]["text"])[1]!=values[v] for k,v in (("contract_id","contract_id"),("buyer","payer"),("seller","payee"))):
        return record
    record["contract_fields"]={k:v[0] for k,v in ids.items()}
    approval["evidence"].extend(record["contract_fields"].values())
    index,role,required=term
    stage=re.fullmatch("第("+NUM+")期",finding["stage"]["name"])
    if not stage or index!=ordinal(stage[1]) or role!="验收款":
        return {**record,"state":"other_stage"}
    signed=listed(values["signed_by"]) if signer else []
    record.update(required=required,listed=signed)
    if not signed:
        return {**record,"state":"missing"}
    if set(signed)==set(required):
        return {**record,"state":"listed"}
    if set(signed)<set(required):
        return {**record,"state":"partial"}
    if not set(signed).intersection(required):
        return {**record,"state":"different"}
    return record


def edge(approval, use, stage):
    names=approval.get("names",{})
    if names.get("state") not in {"listed","different","partial"}:
        return None
    term,=names["rows"]
    signer=names["signed_by"]
    return {"type":"compares_approval_names","from":term,"to":signer,
            "evidence":[use["citation"],approval["request"],stage["clause_ref"],*(names["contract_fields"][k] for k in ("contract_id","buyer","seller")),term,signer]}
