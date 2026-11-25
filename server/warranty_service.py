"""Compare individual warranty work orders with the contract and its dated release evidence."""

import hashlib
import re
from collections import Counter, defaultdict
from unicodedata import normalize

from acceptance_authority import SIGNED, parts, person
from contract_changes import SOURCE_LABELS
from delegation import complete_id, is_page_marker
from delivery_batches import one, raw_body
from reinspection import LINK_KEYS


TITLE="warranty_ticket"
TITLES=("质保维修工单","质保报修工单")
LABELS={"warranty_ticket_id":("质保工单编号","维修工单编号","报修工单编号"),
        "warranty_reported_on":("报修日期",),"warranty_fault":("报修事项","报修故障"),
        "warranty_ticket_state":("工单状态","维修工单状态"),"warranty_closed_on":("关闭日期","工单关闭日期"),
        "warranty_closed_by":("采购方关闭签认","买方关闭签认")}
ROW_FIELDS={label:field for field,labels in {**{k:SOURCE_LABELS[k] for k in LINK_KEYS},**LABELS}.items() for label in labels}
OPEN={"待维修","未关闭","维修中","待复修","处理中"}
CLOSED={"已关闭","已修复并关闭"}
RIDER=re.compile(r"付款|支付|预付|验收|签约|合同变更|生效|免除|追加|另行|另附|协议|另页|扣款|放行|授权|撤销|作废|重开|重新打开|首期|第.{1,3}期|价款|变更|签章|暂缓|以.*为准")
DATE=re.compile(r"(?:[0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}([-/.])[0-9]{1,2}\1[0-9]{1,2})")


def literal(text):
    return normalize("NFKC",text).strip()


def image_ticket_refs(facts):
    signals=[]
    fields=set()
    for fact in facts:
        field=fact["field"]
        if field not in LABELS or fact["status"] not in ("visual","confirmed"):
            continue
        label,body=parts(fact["quote"])
        if label not in LABELS[field] or not body or literal(fact["value"]) not in (body,literal(fact["quote"])):
            continue
        signals.append(fact["id"])
        fields.add(field)
    identifying={"warranty_ticket_id","warranty_ticket_state"}
    reporting={"warranty_reported_on","warranty_fault"}
    if identifying<=fields or "warranty_ticket_id" in fields and fields & reporting or {"warranty_ticket_state",*reporting}<=fields:
        return signals
    return []


def pages_and_lines(graph,read_text,*,inspect_images=False):
    kinds=defaultdict(set)
    for kind,units in graph["documents_by_kind"].items():
        for unit in units:
            kinds[unit].add(kind)
    sections={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    candidates=set(graph["documents_by_kind"].get(TITLE,[]))
    by_page=defaultdict(list)
    for f in graph["facts"]:
        by_page[f["doc"],f["page"]].append(f)
        if f["field"]==TITLE or literal(f["quote"]) in TITLES:
            candidates.add(f.get("unit",f["doc"]))
    originals=[]
    image_refs={}
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        page=int(suffix)
        unit=sections.get((doc,page),doc)
        native=node.get("layer")=="text"
        text=read_text(doc,page) if native else ""
        raw=[(n,s) for n,s in enumerate((text or "").splitlines(),1) if not is_page_marker(s)]
        if inspect_images and not native:
            refs=image_ticket_refs(by_page[doc,page])
            if refs:
                image_refs[doc,page]=refs
                candidates.add(unit)
        if any(literal(s) in TITLES for _,s in raw):
            candidates.add(unit)
        originals.append((unit,doc,page,node,text,raw))
    pages,lines=[],[]
    for unit,doc,page,node,text,raw in originals:
        if unit not in candidates:
            continue
        native=node.get("layer")=="text"
        if native and (not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256")):
            raise ValueError("质保维修工单的文字层与原页摘要不符")
        place={"unit":unit,"doc":doc,"page":page}
        located=defaultdict(list)
        for f in by_page[doc,page]:
            pos=f.get("source_line") or {}
            if native and pos.get("rects"):
                located[pos["number"],pos["text"]].append(f["id"])
            elif f["field"] in (TITLE,*LABELS):
                lines.append({**place,"line":None,"kind":"ticket_line","field":f["field"],"quote":f["quote"],"facts":[f["id"]]})
        fields=[]
        bounded=bool(raw and literal(raw[0][1]) in TITLES and kinds[unit]<={TITLE} and native and node.get("clause_text_only") is True)
        for n,raw_line in raw:
            label,body=parts(raw_line)
            field=TITLE if literal(raw_line) in TITLES else ROW_FIELDS.get(label,"qualification")
            fields.append(field)
            lines.append({**place,"line":n,"kind":"ticket_line","field":field,"quote":raw_line,"facts":located[n,raw_line]})
            if (field=="qualification" or RIDER.search(body) or field=="warranty_fault" and (not body or re.search(r"[;:]",body))
                    or field=="warranty_ticket_state" and body not in OPEN|CLOSED):
                bounded=False
        counts=Counter(fields)
        bounded=bounded and all(counts[k]==1 for k in (TITLE,*LINK_KEYS,"warranty_ticket_id","warranty_reported_on","warranty_fault","warranty_ticket_state"))
        source={**place,"native":native,"text_only":node.get("clause_text_only") is True,"ticket":True,"bounded":bounded}
        if (doc,page) in image_refs:
            source["image_ticket_refs"]=image_refs[doc,page]
        pages.append(source)
    return pages,lines


def classified(ledger):
    pages=[p for p in ledger.get("pages",[]) if p.get("ticket")]
    counts=Counter(p["unit"] for p in pages)
    return {p["unit"] for p in pages},{p["unit"] for p in pages if p["bounded"] and counts[p["unit"]]==1}


def printed_date(body):
    from performance import day
    parsed=day(body) if DATE.fullmatch(body) else None
    return parsed.isoformat() if parsed else None


def assess(graph,contract,start,end,confirmed,cutoff,needs_clear):
    from performance import Material
    from warranty_terms import identity
    ledger=graph["warranty_sources"]
    units,bounded=classified(ledger)
    records=[]
    for unit in sorted(units):
        doc=Material(graph,unit)
        pages=[p for p in ledger["pages"] if p.get("ticket") and p["unit"]==unit]
        rows=[r for r in ledger["lines"] if r["kind"]=="ticket_line" and r["unit"]==unit]
        refs,values={},{}
        for field in (*LINK_KEYS,*LABELS):
            chosen=one(doc,field)
            matching=[r for r in rows if r["field"]==field]
            if chosen and len(matching)==1 and matching[0]["line"] and chosen["id"] in matching[0]["facts"]:
                refs[field]=chosen["id"]
                values[field]=raw_body(chosen)
        number=values.get("warranty_ticket_id","")
        signer=one(doc,"warranty_closed_by")
        attestation=(signer or {}).get("attestation") or {}
        match=SIGNED.fullmatch(values.get("warranty_closed_by",""))
        witness=match[1].strip() if match and person(match[1].strip()) and signer and signer["status"]=="confirmed" and attestation.get("decision")=="confirm" and attestation.get("source_check") else None
        proof=contract.evidence(*LINK_KEYS)+[f"{p['doc']}/p{p['page']}" for p in pages]+[ref for row in rows for ref in row["facts"]]
        conflicts=[]
        for field in LINK_KEYS:
            left=one(contract,field)
            if left and field in refs and raw_body(left)!=values[field]:
                conflicts.append({"field":field,"contract_ref":left["id"],"ticket_ref":refs[field]})
        record={"unit":unit,"number":number if complete_id(number) else None,"fault":values.get("warranty_fault"),
                "reported_on":printed_date(values.get("warranty_reported_on","")),"closed_on":printed_date(values.get("warranty_closed_on","")),
                "printed_state":values.get("warranty_ticket_state"),"closed_by":witness,
                "linked":all(k in refs for k in LINK_KEYS) and identity(contract,doc),"identity_conflicts":conflicts,
                "refs":refs,"evidence":list(dict.fromkeys(proof))}
        records.append(record)
    counts=Counter(r["number"] for r in records if r["number"])
    for r in records:
        opening,closing=r["reported_on"],r["closed_on"]
        state=r["printed_state"]
        if r["unit"] not in bounded:
            decision="scope","missing","工单的整页、附注或文种归属待核。"
        elif not r["linked"]:
            decision="identity","missing","工单与合同的编号、采购方、供应方或标的尚未逐项对应。"
        elif not r["number"] or counts[r["number"]]!=1:
            decision="number","missing","工单编号缺失、不完整或重复，需核实记录归属及版本。"
        elif r["fault"] in (None,"","无","无报修","待填写","不适用","待核","见附件","—") or not opening or not state:
            decision="pending","missing","需核实工单的报修事项、报修日期及明确状态。"
        elif cutoff and (opening>cutoff or closing and closing>cutoff):
            decision="future","risk","工单所列报修或关闭日期晚于资料提交日，需核实实际发生时间。"
        elif not (needs_clear and cutoff and start and end and confirmed and start<opening<end<=cutoff and confirmed<=cutoff):
            decision="period","missing","需核对工单的报修时点、合同承保期间、清结约定及期满确认。"
        elif state in OPEN and not any(k in r["refs"] for k in ("warranty_closed_on","warranty_closed_by")):
            decision="open","risk","工单列为"+state+"，需查验期满确认前的关闭记录。"
        elif state not in CLOSED or not closing or not r["closed_by"] or closing<=opening:
            decision="pending","missing","工单状态、关闭日期或采购方具名关闭签认尚未核实。"
        elif closing>confirmed:
            decision="late","risk",f"工单所列关闭日 {closing} 晚于期满确认日 {confirmed}，需重新核对期满时的缺陷状态。"
        elif closing==confirmed:
            decision="same_day","missing","工单关闭与期满确认同日，需核实当日先后。"
        else:
            decision="closed","ok","工单载有期满确认前的关闭日期及经核图的采购方具名签认。"
        r["state"],r["status"],r["detail"]=decision
    return records


def payment_checks(tickets,bank,paid):
    from performance import date_check
    checks=[]
    for r in tickets:
        detail=r["detail"]
        status=r["status"]
        closed=r["closed_on"]
        if r["state"] in ("closed","late","same_day") and closed>=paid:
            if closed>paid:
                status,detail="risk",f"回单所列付款日 {paid} 早于工单关闭日 {closed}，需核实付款时的清结依据。"
            else:
                same_day="回单付款与工单关闭同日，需核对支付时分及采购方签认时间。"
                status,detail=("risk",detail+" "+same_day) if status=="risk" else ("missing",same_day)
        if status!="ok":
            checks.append(date_check("payment",status,(r["number"] or "质保工单")+" · "+detail,bank.evidence("paid_on")+r["evidence"]))
    return checks
