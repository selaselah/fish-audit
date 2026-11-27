"""Trace a prospective change of installment approvers to the filed agreement and approval."""
from datetime import date
from hashlib import sha256

import approval_clock
import approval_names
import installment_approval
from contract_changes import SEALS, TITLES
from delegation import is_page_marker
from payment_acceptance import FIELD, LEVEL, column, number
from payment_quality import BANK, readings, witness
from reinspection import LINK_KEYS
from stage_payments import SUCCESS


FORMAT = "cited-inspection-payment-use-v7"
HEADINGS = {"补充协议编号":"number","原合同编号":"base_number","采购方":"buyer","供应方":"seller","采购标的":"subject",
            "变更范围":"scope","原签批约定":"previous","变更后签批约定":"revised","变更适用时点":"timing",
            "协议生效条款":"effect","甲方签章":"buyer_seal","乙方签章":"seller_seal","甲方盖章日期":"buyer_date","乙方盖章日期":"seller_date"}
TIMING = "仅适用于本协议生效后签发的付款审批单"
WORDING = {"pending":"另有涉及付款签批的补充协议，需查清归属、签发版本及完整约定。",
           "terms":"已定位原合同及补充协议所列的两份签批名单。须核实协议签署及本期审批时适用的版本。",
           "before":"审批单日期早于协议所记最后盖章日。","after":"审批单日期晚于协议所记最后盖章日。",
           "same_day":"审批与协议最后记载的盖章日期为同一天，盖章时刻待核。"}


def pages(graph,read_text,read_layout):
    files={d["id"]:d for d in graph["documents"]}
    nodes={n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    result=[]
    for page in graph.get("payment_window_sources",{}).get("pages",()):
        if page["document_kind"]!="contract_addendum" or not page["native"]:
            continue
        doc,pg,unit=page["doc"],page["page"],page["unit"]
        node=nodes[f"{doc}/p{pg}"];text=read_text(doc,pg)
        if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=node["text_sha256"]:
            raise ValueError("签批变更所据补充协议原文与归档不符")
        lines=[(i,s) for i,s in enumerate(text.splitlines(),1) if not is_page_marker(s)]
        if not any(column(s)[0] in ("原签批约定","变更后签批约定") or column(s)[0]=="变更范围" and "签批" in s for _,s in lines):
            continue
        facts=[f for f in graph["facts"] if f["doc"]==doc and f["page"]==pg]
        complete=(doc==unit and pg==1 and files[doc].get("ext")==".pdf" and files[doc].get("pages")==1 and page["text_only"]
                  and lines[0][1].strip() in TITLES and not any(f["status"]=="disputed" for f in facts)
                  and not any(g["doc"]==doc and g.get("quality") in {"unreadable","partial","section_unresolved"} for g in graph["gaps"]))
        rects=read_layout(doc,pg).get("lines",{})
        rows=[]
        for i,s in lines:
            field="title" if s.strip() in TITLES else HEADINGS.get(column(s)[0],"rider")
            observed=[f["id"] for f in facts if (f.get("source_line") or {}).get("number")==i and f["source_line"]["text"]==s]
            rows.append({"id":f"approval-change/{doc}/p{pg}/l{i}","unit":unit,"doc":doc,"page":pg,"line":i,
                         "field":field,"quote":s,"facts":observed,"rects":rects.get(str(i),[]),"page_sha256":node["sha256"]})
        result.append({"doc":doc,"page":pg,"unit":unit,"complete":complete,"rows":rows})
    return result


def cite(check,rows):
    for r in rows:
        check["evidence"].extend((r["id"],f"{r['doc']}/p{r['page']}",*r["facts"]))


def inspect(graph,finding):
    from performance import Material,printed_day

    ledger=graph["inspection_use_sources"];changes=ledger["approver_changes"]
    base=ledger.get("approver_terms",[]);refs=finding["stage_approvers"];stage=finding["stage"]
    supplements=[r for p in changes for r in p["rows"]]
    scoped=[term for r in supplements if r["field"] in {"previous","revised"}
            and (term:=approval_names.clause("付款签批约定："+column(r["quote"])[1]))]
    contract_rows=[r for p in base for r in p["rows"] if r["id"] in refs]
    if scoped and contract_rows and not any(t[:2]==b[:2] for t in scoped for r in contract_rows if (b:=approval_names.clause(r["quote"]))):
        return None
    entry={"state":"pending","status":"missing","documents":[p["doc"] for p in changes],"rows":[r["id"] for r in supplements],
           "evidence":[stage["clause_ref"]]}
    cite(entry,[*contract_rows,*supplements])
    kinds=graph["documents_by_kind"];sheets=ledger.get("approvals",[])
    ordinary=approval_names.ORDINARY | {"contract_addendum"}
    units={u for k in ordinary for u in kinds.get(k,())} | {p["unit"] for p in sheets}
    if (len(base)!=1 or not base[0]["complete"] or len(base[0]["rows"])!=1 or len(contract_rows)!=1 or
            kinds.get("contract")!=[base[0]["unit"]] or len(changes)!=1 or not changes[0]["complete"] or
            kinds.get("contract_addendum")!=[changes[0]["unit"]] or any(v for k,v in kinds.items() if k not in ordinary and k!="other")
            or units!={d["id"] for d in graph["documents"]}):
        return entry
    change=changes[0];fields={r["field"]:r for r in supplements}
    if set(fields)!={"title",*HEADINGS.values()} or len(fields)!=len(supplements) or not all(r["rects"] for r in supplements):
        return entry
    v={k:column(r["quote"])[1] for k,r in fields.items()}
    records=[r for r in graph.get("addendum_pdf_sources",{}).get("records",()) if r["unit"]==change["unit"]]
    if len(records)!=1:
        return entry
    execution=records[0]
    entry.update(execution=execution["id"],signature_state=execution["state"])
    entry["evidence"].extend([execution["id"],execution["doc"],*(p["ref"] for p in execution["pages"]),*execution["fields"]])
    if execution["state"] not in ("typeset","current"):
        return entry
    base_row=contract_rows[0];term=approval_names.clause(base_row["quote"])
    obs=graph.get("retest_reference_sources",{}).get("rows") or graph.get("payment_quality_sources",{}).get("rows",[])
    contract=Material(graph,base_row["unit"])
    identity=readings(obs,contract,LINK_KEYS);installment=witness(obs,contract,"payment_stage",clause=stage["clause_ref"])
    previous,revised=(approval_names.clause("付款签批约定："+v[k]) for k in ("previous","revised"))
    if (not term or not previous or not revised or previous[:2]!=term[:2] or revised[:2]!=term[:2] or
            column(base_row["quote"])[1]!=v["previous"] or set(previous[2])==set(revised[2]) or
            not identity or not installment or installment[1]!=stage["clause"] or not number(v["number"]) or
            not number(v["base_number"]) or v["base_number"]==v["number"] or v["base_number"]!=identity["contract_id"][1]
            or any(v[k]!=identity[k][1] for k in ("buyer","seller","subject")) or v["buyer"]==v["seller"]):
        return entry
    if (v["scope"]!="仅变更"+stage["name"]+term[1]+"签批人，其余条款不变" or v["timing"]!=TIMING or v["effect"] not in SEALS or
            any(v[k+"_seal"] not in (v[k]+"（已盖章）",v[k]+"(已盖章)") for k in ("buyer","seller"))):
        return entry
    dates=[installment_approval.printed_date(v[k+"_date"]) for k in ("buyer","seller")]
    signed=printed_day(contract,"signed_on")
    if not all(dates) or not signed or signed.isoformat()>min(dates):
        return entry
    entry.update(state="terms",original=base_row["id"],fields={k:r["id"] for k,r in fields.items()},before=previous[2],after=revised[2],
                 buyer_on=dates[0],seller_on=dates[1],last_seal_on=max(dates),contract_fields={k:x[0] for k,x in identity.items()})
    entry["evidence"].extend([*entry["contract_fields"].values(),*contract.evidence("signed_on")])
    if finding["rule"]=="H05" and term[1]=="验收款" and not finding.get("execution_basis"):
        payment(graph,finding,entry,identity,obs,sheets,term)
    return entry


def payment(graph,finding,entry,identity,observations,sheets,term):
    from performance import Material

    kinds=graph["documents_by_kind"];ledger=graph["inspection_use_sources"]
    banks=kinds.get("bank_receipt",[]);finals=kinds.get("reinspection",[]);initials=kinds.get("acceptance",[])
    if len(sheets)!=1 or len(banks)!=1 or banks[0] not in finding["scope"] or len(finals)!=1 or len(initials)!=1:
        return
    data=installment_approval.contents(sheets[0])
    if not data:
        return
    fields,values,_,decision,issued=data
    bank=readings(observations,Material(graph,banks[0]),(*BANK,FIELD))
    final=readings(observations,Material(graph,finals[0]),(*LINK_KEYS,"acceptance_number"))
    initial=readings(observations,Material(graph,initials[0]),(*LINK_KEYS,"acceptance_number"))
    notes=ledger["rows"];stage=finding["stage"]["name"]
    if (not bank or not final or not initial or initial["acceptance_number"][1]==final["acceptance_number"][1]
            or not number(initial["acceptance_number"][1]) or any(identity[k][1]!=r[k][1] for r in (initial,final) for k in LINK_KEYS) or
            len(notes)!=1 or notes[0]["unit"]!=finals[0] or notes[0]["kind"]!="approval" or notes[0]["disputed"] or not notes[0]["rects"]
            or notes[0]["authority"]!=values["authority"] or notes[0]["index"]!=term[0] or notes[0]["role"]!=term[1]
            or any(bank[k][1]!=values[k] or values[k]!=identity[c][1] for k,c in (("contract_id","contract_id"),("payer","buyer"),("payee","seller")))
            or bank["transfer_status"][1] not in SUCCESS or bank["payment_designation"][1] not in (stage,stage+term[1])
            or values["stage"]!=stage+term[1] or not number(values["inspection"]) or values["inspection"]!=bank[FIELD][1]
            or values["inspection"]!=final["acceptance_number"][1] or "signed_at" not in fields):
        return
    signed_day,signed_at,zone=approval_clock.printed_clock(values["signed_at"].translate(approval_clock.DISPLAY))
    if not signed_at or zone!="+08:00" or signed_day and signed_day!=issued:
        return
    clocks=ledger.get("bank_clocks",[])
    if len(clocks)!=1 or clocks[0]["unit"]!=banks[0] or not clocks[0]["complete"]:
        return
    listed=approval_names.listed(values.get("signed_by","")) or []
    delta=(date.fromisoformat(issued)-date.fromisoformat(entry["last_seal_on"])).days
    state="before" if delta<0 else "after" if delta>0 else "same_day"
    expected=entry["before"] if delta<0 else entry["after"] if delta>0 else []
    mismatch=bool(listed and expected and set(listed).isdisjoint(expected))
    missing=[n for n in expected if n not in listed] if listed and set(listed)<set(expected) else []
    paid=bank["paid_on"][1]
    clock=approval_clock.assess(fields["signed_at"],banks[0],clocks,paid) if issued==paid else None
    early=paid<issued or (clock or {}).get("state")=="debit_first"
    entry.update(state=state,status="risk" if mismatch or decision=="refused" or early else "missing",printed_difference=mismatch,missing_names=missing,
                 issued_on=issued,days_from_seals=delta,listed=listed,approval=fields["title"]["unit"],paid_on=paid,
                 approval_fields={k:r["id"] for k,r in fields.items()},bank_fields={k:v[0] for k,v in bank.items()},
                 receipt_fields={k:v[0] for k,v in final.items()},initial_fields={k:v[0] for k,v in initial.items()},
                 request=notes[0]["id"],refused=decision=="refused",early_debit=early)
    cite(entry,[*sheets[0]["rows"],*notes,*clocks[0]["rows"]])
    entry["evidence"].extend([*entry["bank_fields"].values(),*entry["receipt_fields"].values(),*entry["initial_fields"].values()])


def apply(graph,findings):
    ledger=graph.get("inspection_use_sources",{})
    if not ledger.get("approver_changes"):
        return
    for f in findings:
        if f["rule"] not in ("H04","H05") or not f.get("stage_approvers"):
            continue
        record=inspect(graph,f)
        if not record:
            continue
        record["evidence"]=list(dict.fromkeys(record["evidence"]))
        f["approval_change"]=record
        f["evidence"]=list(dict.fromkeys([*f["evidence"],*record["evidence"]]))
        f["scope"]=list(dict.fromkeys([*f["scope"],*record["documents"],*([record["approval"]] if "approval" in record else [])]))
        if LEVEL[f["status"]]<LEVEL[record["status"]]:f["status"]=record["status"]
        detail=WORDING[record["state"]]
        if record.get("printed_difference"):detail+=" 审批单具名栏与按纸面日期对应的名单不同，请核对当时的完整授权。"
        if record.get("missing_names"):detail+=" 按纸面日期对应的共同签批约定，尚缺"+"、".join(record["missing_names"])+"的签批依据。"
        if record.get("refused"):detail+=" 审批单列明不同意支付。"
        if record.get("early_debit"):detail+=" 原件记载的扣款在审批签发之前。"
        if "issued_on" in record:detail+=" 协议实际生效、双方签署及签批权限仍待人工核验。"
        f["detail"]+=" "+detail


def edges(findings):
    return [{"type":"dates_approval_change","from":c["fields"]["revised"],"to":c["approval_fields"]["date"],"evidence":c["evidence"]}
            for f in findings if (c:=f.get("approval_change")) and "issued_on" in c]
