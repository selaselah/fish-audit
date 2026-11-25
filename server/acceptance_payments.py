"""Preserve payment instructions on a final acceptance record separately from its quality opinion."""

import re
from collections import defaultdict
from unicodedata import normalize

from delegation import complete_id, is_page_marker
from delivery_batches import NUM, ordinal
from reinspection import LINK_KEYS
from warranty_terms import identity


SINCE = "2026.11.25.25"
HEADINGS = {"付款意见","支付意见","付款备注","付款说明","付款办理意见"}
ROLES = {"预付款":"effect","验收款":"acceptance","质保金":"warranty"}
ROLE = "|".join(ROLES)
ALL = r"(?:全部|所有|各期)(?:合同)?(?:付款|款项|货款|期款)"
TARGET = rf"(?:本合同(?:项下)?的?)?(?:(?P<all>{ALL})|(?:第(?P<number>{NUM})期)(?P<role>{ROLE})?|(?P<only>{ROLE}))"
ACTION = r"(?:暂缓|暂停|停止|冻结)(?:办理|支付|付款)?|同意支付|同意付款"
AFTER = re.compile(TARGET+rf"(?:均|一律)?(?P<action>{ACTION})")
BEFORE = re.compile(rf"(?P<action>{ACTION})"+TARGET)
HINT = re.compile(r"(?:暂缓|暂停|冻结|暂不|同意|不予|不同意).{0,14}(?:付款|支付|验收款|质保金|预付款)"
                  r"|(?:付款|支付|验收款|质保金|预付款|全部款项).{0,14}(?:暂缓|暂停|冻结|暂不|不予|缓付|暂扣)")


def classify(raw):
    text=normalize("NFKC",raw).strip().rstrip("。")
    label,sep,body=text.partition(":")
    named=bool(sep and label.strip() in HEADINGS)
    if not named and not HINT.search(text):
        return None
    if named and body.strip() in {"无","无付款意见","无其他付款意见"}:
        return None
    match=(AFTER.fullmatch(body.strip()) or BEFORE.fullmatch(body.strip())) if named else None
    number=ordinal(match["number"]) if match and match["number"] else None
    if not match or match["number"] and not number:
        return {"stance":"unclear","target":None,"index":None,"kind":None}
    return {"stance":"assent" if match["action"].startswith("同意") else "hold",
            "target":"all" if match["all"] else "phase","index":number,
            "kind":ROLES.get(match["role"] or match["only"])}


def page_rows(place, text, facts, known_labels):
    from graph import PRINTED_TITLES
    anchored=defaultdict(list)
    notes,qualifications=[],[]
    for f in facts:
        point=f.get("source_line") or {}
        if text is not None and point.get("rects") and point["text"]==f["quote"]:
            anchored[point["number"],point["text"]].append(f["id"])
        elif entry:=classify(f["quote"]):
            notes.append({**place,"line":None,"quote":f["quote"],"facts":[f["id"]],**entry})
    for number,raw in enumerate((text or "").splitlines(),1):
        if is_page_marker(raw):
            continue
        row={**place,"line":number,"quote":raw,"facts":anchored[number,raw]}
        if entry:=classify(raw):
            notes.append({**row,**entry})
        else:
            value=normalize("NFKC",raw).strip()
            label,sep,_=value.partition(":")
            if PRINTED_TITLES.get(value) in (None,"payment_release") and not (sep and label.strip() in known_labels):
                qualifications.append({**row,"stance":"qualification","target":None,"index":None,"kind":None})
    return notes,qualifications


def same_original(contract,record):
    if not identity(contract,record):
        return False
    values={}
    for key in LINK_KEYS:
        pair=[normalize("NFKC",doc.fields[key][0]["source_line"]["text"]).partition(":")[2].strip()
              for doc in (contract,record)]
        if not pair[0] or pair[0]!=pair[1] or re.search(r"[*×□…]|待定|不详|同上|同(?:主)?合同",pair[0]):
            return False
        values[key]=pair[0]
    return complete_id(values["contract_id"]) and values["buyer"]!=values["seller"]


def for_stages(graph,contract,receipts,rows,plan):
    from payment_windows import located_day
    ledger=graph.get("acceptance_reservation_sources",{})
    notes=ledger.get("payment_opinions",[])
    if not notes:
        return {}
    records={r.unit:r for r in receipts}
    observations={f["id"]:f for f in graph["facts"]}
    pages=ledger["pages"]
    context={}
    for unit in {n["unit"] for n in notes}:
        record=records.get(unit)
        seen=[p for p in pages if p["unit"]==unit]
        bound=bool(record and seen and all(p["native"] and p["text_only"] for p in seen)
                   and plan["status"]=="ok" and same_original(contract,record))
        when,ref=located_day(record,"accepted_on") if bound else (None,None)
        context[unit]=(bound,when.isoformat() if when else None,ref)
    matched=defaultdict(list)
    for note in notes:
        bound=context[note["unit"]][0] and note["line"] and not any(observations[f]["status"]=="disputed" for f in note["facts"])
        indices=[]
        if bound and note["target"]=="phase":
            kinds={note["kind"],"batch"} if note["kind"]=="acceptance" else {note["kind"]}
            indices=[i for i,row in enumerate(rows) if (not note["index"] or note["index"]==row["index"])
                     and (not note["kind"] or row["kind"] in kinds)]
            if len(indices)==1:
                fact=observations.get(rows[indices[0]]["ref"])
                if not fact or not (fact.get("source_line") or {}).get("rects") or fact["status"] not in ("anchored","confirmed"):
                    indices=[]
                elif note["index"]:
                    label=normalize("NFKC",fact["source_line"]["text"]).strip().partition(":")[0].strip()
                    printed=re.fullmatch(r"第("+NUM+r")期",label)
                    if not printed or ordinal(printed[1])!=note["index"]:
                        indices=[]
        scope="phase" if len(indices)==1 else "all" if bound and note["target"]=="all" else "unresolved"
        for i in indices if scope=="phase" else range(len(rows)):
            matched[i].append({**note,"scope":scope})
    decisions={}
    for i,entries in matched.items():
        units=list(dict.fromkeys(n["unit"] for n in entries))
        stances={n["stance"] for n in entries}
        scopes={n["scope"] for n in entries}
        if "unresolved" in scopes or stances-{"hold","assent"}:
            state="unresolved"
        elif stances=={"hold","assent"}:
            state="conflict" if len(units)==1 else "unresolved"
        else:
            state=next(iter(stances))
        dates=[{"unit":u,"date":context[u][1],"ref":context[u][2]} for u in units if context[u][1]]
        refs=contract.evidence(*LINK_KEYS)
        refs.extend(f"{p['doc']}/p{p['page']}" for p in pages if p["unit"] in units)
        refs.extend(ref for n in entries for ref in n["facts"])
        refs.extend(ref for u in units if u in records for ref in records[u].evidence(*LINK_KEYS,"accepted_on","acceptance_signer"))
        refs.append(rows[i]["ref"])
        decisions[rows[i]["ref"]]={"state":state,"notes":entries,"record_dates":dates,"units":units,
                                  "evidence":list(dict.fromkeys(refs))}
    return decisions


def attach(finding,opinion):
    if not opinion:
        return
    state=opinion["state"]
    finding["payment_opinion"]=opinion
    finding["scope"]=list(dict.fromkeys([*finding["scope"],*opinion["units"]]))
    finding["evidence"]=list(dict.fromkeys([*finding["evidence"],*opinion["evidence"]]))
    if release:=opinion.get("release"):
        from payment_releases import apply_release
        apply_release(finding,release)
        return
    detail={"hold":"验收原件的付款意见载明暂缓支付，须核对签发权限、适用时间及后续放行凭据。",
            "conflict":"同一验收文书对本期同时载有暂缓与同意支付，须核对最终审批依据。",
            "assent":"验收文书另列同意支付意见，付款仍应逐项核对合同前提。",
            "unresolved":"付款意见的归属、范围或附注待核，请查完整原页及审批记录。"}[state]
    if finding["rule"]=="H05" and state!="assent":
        detail+=" 请核实本笔实际付款当时的审批记录。"
    status="risk" if state=="conflict" and finding["rule"]=="H04" else "missing"
    if state!="assent" and (finding["status"]=="ok" or finding["status"]=="missing" and status=="risk"):
        if finding["status"]=="ok":
            finding["detail"]=detail
        else:
            finding["detail"]+=" "+detail
        finding["status"]=status
    else:
        finding["detail"]+=" "+detail


def legacy_signoff(report,ledger):
    positives=[f for f in report["findings"] if f["rule"] in ("H04","H05") and f["status"]=="ok" and f.get("stage")]
    if not positives or not ledger.get("payment_opinions"):
        return
    from performance import compute
    findings=compute({**report["graph"],"acceptance_reservation_sources":ledger},recheck_payment_opinions=True)
    held={f["stage"]["clause_ref"] for f in findings if f.get("payment_opinion") and f["payment_opinion"]["state"]!="assent"}
    if any(f["stage"]["clause_ref"] in held for f in positives):
        raise ValueError("旧版列为相符的期款另有验收付款意见，请重新审计后签收。")
