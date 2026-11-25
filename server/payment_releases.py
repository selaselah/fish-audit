"""Trace a written release of a specific acceptance-payment hold to its contract and receipt."""

import hashlib
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from unicodedata import normalize

from acceptance_authority import person
from acceptance_payments import same_original
from delegation import complete_id, is_page_marker, native_value
from delivery_batches import NUM, ordinal
from reinspection import LINK_KEYS


FORMAT="stage-payment-release-v1"
SINCE="2026.11.25.26"
TITLE="付款放行单"
AUTHORITY=re.compile(r"放行约定:第("+NUM+r")期暂缓自验收日起执行,须经甲方([^，,、()\s]{2,12})签字放行")
RELEASE=re.compile(r"放行决定:解除第("+NUM+r")期验收款暂缓,自签字日起恢复支付")
HINT=re.compile(r"放行|暂缓|止付|解付|冻结|解冻|暂扣|缓付|暂不付款|拒付|中止支付")
RIDER=re.compile(r"(?:撤回|撤销|取消|作废).{0,12}(?:授权|审批|付款)|(?:付款|审批|授权).{0,12}(?:撤回|撤销|作废)|(?:另须|尚须|还需).{0,12}(?:审批|会签|批准)")
LABELS={"合同编号":"identity","合同号":"identity","采购方":"identity","供应方":"identity","采购标的":"identity",
        "原验收单编号":"receipt","原验收报告编号":"receipt","放行决定":"decision","放行签字日期":"date","审批日期":"approval_date","审批签认":"signature"}


def literal(raw):
    return normalize("NFKC",raw).strip().removesuffix("。")


def mandate(raw):
    match=AUTHORITY.fullmatch(literal(raw))
    if match and person(match[2]) and ordinal(match[1]):
        return ordinal(match[1]),match[2]
    return None


def sources(graph,read_text):
    result={"format":FORMAT,"pages":[],"lines":[]}
    notes=graph.get("acceptance_reservation_sources",{}).get("payment_opinions",[])
    if not notes:
        return result
    noted={(s["doc"],s["page"],s["line"],s["quote"]) for s in notes}
    from graph import LABELS as fields, PRINTED_TITLES
    common={label for labels in fields.values() for label in labels}
    kinds=defaultdict(set)
    for kind,units in graph["documents_by_kind"].items():
        for unit in units:
            kinds[unit].add(kind)
    sections={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    observations=defaultdict(list)
    for f in graph["facts"]:
        observations[f["doc"],f["page"]].append(f)
    candidates=[]
    release_units=set(graph["documents_by_kind"].get("payment_release",[]))
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        page=int(suffix)
        unit=sections.get((doc,page),doc)
        native=node.get("layer")=="text"
        raw=read_text(doc,page) if native else ""
        if native and (not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=node.get("text_sha256")):
            raise ValueError("放行单所据原页文字摘要不符")
        lines=[(i,s) for i,s in enumerate(raw.splitlines(),1) if s.strip() and not is_page_marker(s)]
        facts=observations[doc,page]
        printed_title=bool(lines and literal(lines[0][1])==TITLE)
        if printed_title or any(literal(f["quote"])==TITLE for f in facts):
            release_units.add(unit)
        candidates.append(({"unit":unit,"doc":doc,"page":page,"native":native,"text_only":node.get("clause_text_only") is True},
                           lines,facts,printed_title))
    for place,lines,facts,printed_title in candidates:
        unit=place["unit"]
        if not (unit in release_units or "contract" in kinds[unit]):
            others=[(i,s) for i,s in lines if (HINT.search(s) or RIDER.search(s)) and (place["doc"],place["page"],i,s) not in noted]
            external=[f for f in facts if (HINT.search(f["quote"]) or RIDER.search(f["quote"])) and not f.get("source_line") and (place["doc"],place["page"],None,f["quote"]) not in noted]
            if others or external or not place["native"] or not place["text_only"]:
                result["pages"].append({**place,"role":"context","printed_title":False,"identity_clear":True})
                for i,s in others:
                    refs=[f["id"] for f in facts if f["quote"]==s and (f.get("source_line") or {}).get("number")==i]
                    result["lines"].append({**place,"role":"qualification","line":i,"quote":s,"facts":refs})
                result["lines"].extend({**place,"role":"qualification","line":None,"quote":f["quote"],"facts":[f["id"]]} for f in external)
            continue
        release=unit in release_units
        page={**place,"role":"release" if release else "contract","printed_title":printed_title,
              "identity_clear":kinds[unit]<={"payment_release"} if release else kinds[unit]=={"contract"}}
        result["pages"].append(page)
        anchored=defaultdict(list)
        for f in facts:
            loc=f.get("source_line") or {}
            if place["native"] and loc.get("rects") and loc["text"]==f["quote"]:
                anchored[loc["number"],loc["text"]].append(f["id"])
            elif HINT.search(f["quote"]) or release and f["field"] in ("approval_signer","approved_on","original_acceptance"):
                result["lines"].append({**place,"role":"qualification","line":None,"quote":f["quote"],"facts":[f["id"]]})
        for i,raw in lines:
            text=literal(raw)
            label,sep,_=text.partition(":")
            if release:
                role="title" if text==TITLE else LABELS.get(label,"qualification") if sep else "qualification"
            elif mandate(raw):
                role="authority"
            elif HINT.search(text) or RIDER.search(text) or text not in PRINTED_TITLES and (not sep or label not in common and not re.fullmatch(r"第"+NUM+"期",label)):
                role="qualification"
            else:
                continue
            result["lines"].append({**place,"role":role,"line":i,"quote":raw,"facts":anchored[i,raw]})
    return result


def relations(ledger):
    return [{"type":"payment_release_basis","from":s["unit"],"to":f"{s['doc']}/p{s['page']}","line":s["line"],
             "evidence":[f"{s['doc']}/p{s['page']}",*s["facts"]]} for s in ledger["lines"]]


def recognized(ledger):
    pages=[p for p in ledger.get("pages",[]) if p["role"]=="release"]
    units=set()
    for p in pages:
        rows=[s for s in ledger["lines"] if s["unit"]==p["unit"]]
        decisions=[s for s in rows if s["role"]=="decision"]
        if (p["printed_title"] and p["identity_clear"] and p["native"] and p["text_only"]
                and sum(other["unit"]==p["unit"] for other in pages)==1 and len(decisions)==1
                and RELEASE.fullmatch(literal(decisions[0]["quote"])) and all(s["role"]!="qualification" for s in rows)):
            units.add(p["unit"])
    return units


def scalar(doc,field,labels):
    facts=doc.fields[field]
    if len(facts)!=1 or doc.incomplete(field):
        return None,None
    f=facts[0]
    return native_value(f,labels) or None,f["id"]


def exact_day(doc,field):
    from payment_windows import located_day,split_line
    when,ref=located_day(doc,field)
    if when:
        _,value=split_line(doc.fields[field][0]["source_line"]["text"])
        if re.fullmatch(r"(?:\d{4}年\d{1,2}月\d{1,2}日|\d{4}([/.-])\d{1,2}\1\d{1,2})",value):
            return when.isoformat(),ref
    return None,None


def submission_day(timestamp):
    submitted=datetime.fromisoformat(timestamp)
    if submitted.utcoffset() is None:
        raise ValueError("放行审查的提交时间缺少时区")
    return submitted.astimezone(timezone(timedelta(hours=8))).date().isoformat()


def assess(graph,contract,record,opinion,row):
    from performance import Material
    ledger=graph.get("payment_release_sources",{})
    pages=ledger.get("pages",[])
    units=list(dict.fromkeys(p["unit"] for p in pages if p["role"]=="release"))
    clauses=[s for s in ledger.get("lines",[]) if s["role"]=="authority" and s["unit"]==contract.unit]
    if not units and not clauses:
        return None
    if len(clauses)==1 and mandate(clauses[0]["quote"])[0]!=row["index"]:
        return None
    relevant=ledger["lines"]
    evidence=[ref for s in relevant for ref in (f"{s['doc']}/p{s['page']}",*s["facts"])]
    evidence.extend(f"{p['doc']}/p{p['page']}" for p in pages)
    check={"state":"pending","units":list(dict.fromkeys(p["unit"] for p in pages if p["role"]!="contract")),"sources":relevant,"signer":None,"required":None,"signed_on":None,
           "date_ref":None,"signature_ref":None,"receipt_ref":None,"original_ref":None,"held_on":None,"as_of":graph.get("payment_release_as_of"),
           "evidence":list(dict.fromkeys(evidence))}
    notes=opinion["notes"]
    if (len(clauses)!=1 or not clauses[0]["line"] or opinion["state"]!="hold" or len(notes)!=1 or notes[0]["scope"]!="phase"
            or notes[0]["kind"]!="acceptance" or row["kind"]!="acceptance" or not record):
        return check
    idx,check["required"]=mandate(clauses[0]["quote"])
    if idx!=row["index"] or notes[0]["index"]!=idx:
        return check
    if not units:
        check["state"]="absent"
        return check
    documents=graph.get("audit_documents",graph["documents"])
    permitted=set().union(*(set(graph["documents_by_kind"].get(k,[])) for k in ("contract","acceptance","warranty","invoice","bank_receipt")))
    if (len(units)!=1 or set(units)!=recognized(ledger) or set(graph["documents_by_kind"].get("acceptance",[]))!={record.unit}
            or any(d["id"] not in permitted|set(units) for d in documents)
            or any(not p["native"] or not p["text_only"] or not p["identity_clear"] for p in pages)
            or any(s["role"]=="qualification" for s in relevant)):
        return check
    release=Material(graph,units[0])
    rows=[s for s in relevant if s["unit"]==release.unit]
    if (len(rows)!=9 or set(s["role"] for s in rows)!={"title","identity","receipt","decision","date","signature"}
            or not same_original(contract,release)):
        return check
    state={f["id"]:f["status"] for f in graph["facts"]}
    if any(state.get(ref)=="disputed" for s in relevant for ref in s["facts"]):
        return check
    decision=next(s for s in rows if s["role"]=="decision")
    matched=RELEASE.fullmatch(literal(decision["quote"]))
    if not matched or ordinal(matched[1])!=idx:
        return check
    original,check["original_ref"]=scalar(record,"acceptance_number",("验收单编号","验收报告编号"))
    cited,check["receipt_ref"]=scalar(release,"original_acceptance",("原验收单编号","原验收报告编号"))
    check["signed_on"],check["date_ref"]=exact_day(release,"release_signed_on")
    signer,check["signature_ref"]=scalar(release,"approval_signer",("审批签认",))
    check["evidence"]=list(dict.fromkeys([*check["evidence"],*record.evidence("acceptance_number"),*release.evidence(*LINK_KEYS,"release_signed_on","approval_signer","original_acceptance")]))
    dates=opinion["record_dates"]
    if len(dates)==1 and dates[0]["unit"]==record.unit and exact_day(record,"accepted_on")== (dates[0]["date"],dates[0]["ref"]):
        check["held_on"]=dates[0]["date"]
    if (not original or not cited or not complete_id(original) or not complete_id(cited)
            or re.search(r"尾号|部分|同上|不详|末[几数\d一二三四五六七八九十]+位",original+cited)
            or any(h["fact"] in (check["original_ref"],check["receipt_ref"]) for h in graph.get("quality_references",{}).get("holds",[]))):
        return check
    if original!=cited:
        check["state"]="reference_mismatch"
        return check
    signed=re.fullmatch(r"([^()\s]+)\(已签(?:字|名)\)",signer or "")
    signoff=release.fields["approval_signer"][0] if check["signature_ref"] else {}
    att=signoff.get("attestation") or {}
    if not (signed and person(signed[1]) and signoff.get("status")=="confirmed" and att.get("decision")=="confirm" and att.get("source_check")):
        return check
    check["signer"]=signed[1]
    if check["signer"]!=check["required"]:
        check["state"]="signer_mismatch"
    elif check["signed_on"] and check["held_on"] and check["signed_on"]>check["held_on"] and check["as_of"]:
        check["state"]="matched" if check["signed_on"]<=check["as_of"] else "future"
    return check


def at_payment(opinion,contract,bank):
    from warranty_terms import bank_identity
    release=opinion["release"]
    when,ref=exact_day(bank,"paid_on")
    paid=when if when and release["as_of"] and when<=release["as_of"] and bank_identity(contract,bank) else None
    timing="unknown"
    if release["state"]=="matched" and paid and paid>release["held_on"]:
        timing="same_day" if paid==release["signed_on"] else "before" if paid<release["signed_on"] else "after"
    refs=list(dict.fromkeys([*release["evidence"],*bank.evidence("paid_on","payment_designation")]))
    return {**opinion,"release":{**release,"timing":timing,"paid_on":paid,"paid_ref":ref if paid else None,"evidence":refs},
            "evidence":list(dict.fromkeys([*opinion["evidence"],*refs]))}


def apply_release(finding,release):
    status="missing"
    if release["state"]=="matched":
        timing=release.get("timing")
        if timing=="before":
            status="risk"
            detail=f"回单付款日 {release['paid_on']} 早于具名签字放行日 {release['signed_on']}，须核查提前支付依据。"
        elif timing=="same_day":
            detail="放行签字与实际付款同日，需取得当天审批、付款时分以核实顺序。"
        elif timing=="unknown":
            detail="须核实本笔付款相对暂缓起日及具名放行的先后顺序。"
        else:
            finding["detail"]+=f" 原暂缓所据验收单号与放行单一致，合同指定人{release['signer']}已签认，放行日为 {release['signed_on']}。"
            return
    else:
        detail={"absent":"合同约定由具名人员签字放行，尚缺相应放行单。",
                "signer_mismatch":f"放行单签认人为{release['signer']}，与合同指定人{release['required']}不同，请核对授权或补充审批。",
                "reference_mismatch":"放行单所引原验收单号与暂缓款所据原件不同，请核对所放行的业务。",
                "future":"放行签字日期晚于本案资料提交日，请核对实际签发时间。",
                "pending":"原件载明暂缓，放行依据的范围、所据原单、具名签认及时间尚须核对。"}[release["state"]]
    if finding["status"]=="ok":
        finding.update(status=status,detail=detail)
    else:
        if status=="risk" and finding["status"]=="missing":
            finding["status"]="risk"
        finding["detail"]+=" "+detail


def verify(report,read_text,*,submitted=None,signed=None):
    ledger=report["graph"].get("payment_release_sources")
    marker=report["policy"].get("payment_releases")
    if not marker and report["policy"].get("version","")<SINCE and ledger is None:
        return
    expected=sources(report["graph"],read_text)
    actual=[e for e in report["graph"]["edges"] if e["type"]=="payment_release_basis"]
    if marker!=FORMAT or ledger!=expected or actual!=relations(expected):
        raise ValueError("验收款放行所据原行或凭证关系与原件不符")
    if expected["pages"]:
        cutoff=report["graph"].get("payment_release_as_of")
        if (not isinstance(cutoff,str) or date.fromisoformat(cutoff).isoformat()!=cutoff or
                submitted and cutoff!=submission_day(submitted) or signed and cutoff>submission_day(signed)):
            raise ValueError("放行审查的截止日与提交记录不符")
