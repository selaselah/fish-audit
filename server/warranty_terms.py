"""Reconcile the contracted warranty period and release conditions with signed evidence."""

import calendar
import hashlib
import re
from collections import defaultdict
from datetime import date, timedelta

from acceptance_authority import covers, parts, signed_name
from calculations import normalized
from contract_changes import labelled_sources
from delegation import complete_id, covered_rows
from delivery_batches import one, ordinal, raw_body
from performance_versions import WARRANTY_FORMAT, WARRANTY_FORMATS
from reinspection import LINK_KEYS, linked


FORMAT = "contract-warranty-release-v1"
LABELS = {
    "warranty_period": ("质保期限","质保期","保修期限","保修期","质保截止日"),
    "warranty_condition": ("质保金返还条件","质保金释放条件","质保金支付条件","质保金返还前提"),
    "warranty_defects": ("质保遗留事项","质保缺陷状态","质保未结事项","质保期内遗留问题"),
}
RELEASE_TITLES = {"质保期满确认单","质保期满确认书"}
MENTION = re.compile(r"质保|保修|质量保证期|质量保证金|缺陷责任期|保留款|尾款|扣留|扣减|扣款")
NUMBER = r"(?:[1-9][0-9]{0,3}|[一二两三四五六七八九十]{1,3})"
PERIOD = re.compile(r"(?:自|从)(?:最终验收|整体验收|终验)合格(?:之日|当日|日)?(?:起|之日起)(?:算)?(?:为|计)?("+NUMBER+r")(个自然日|自然日|天|日|个月|年)")
DATE = r"[0-9]{4}(?:年|[./-])[0-9]{1,2}(?:月|[./-])[0-9]{1,2}日?"
CONFIRM = re.compile(r"("+DATE+r")(?:双方确认)?质保期(?:已届满|届满|已满)")
NO_EXTENSION = {"届满日不顺延","遇节假日不顺延","遇法定休假日不顺延"}
NO_DEFECT = {"无","无遗留事项","无未关闭缺陷","无未结质量问题","无未解决质量问题"}
DEFECT_CONDITION = {"质保期满且无未关闭缺陷","质保期满且无未结质量问题","质保期满且无遗留质量问题"}
INLINE = re.compile("("+"|".join(sorted(DEFECT_CONDITION))+r")后(?:支付|返还)(?:合同(?:总价|价款|总额)的?)?([0-9]{1,3}(?:\.[0-9]{1,4})?)%")
OPEN_DEFECT = re.compile(r"(?:有未关闭缺陷|存在未关闭缺陷|仍有未结质量问题|.{1,36}(?:故障|缺陷|质量问题)(?:尚未|仍未|未)(?:修复|关闭|解决))")
RELEASE_FIELDS = {"warranty",*LINK_KEYS,"warranty_release","warranty_defects","acceptance_signer"}


def parse_period(label,body):
    from performance import day
    clauses=body.rstrip("。").split(",")
    unadjusted=len(clauses)==2 and clauses[1] in NO_EXTENSION
    if len(clauses)>1 and not unadjusted:
        return None
    text=clauses[0]
    if label=="质保截止日":
        fixed=day(text) if re.fullmatch(DATE,text) else None
        return {"unit":"固定日期","count":None,"fixed":fixed.isoformat(),"unadjusted":unadjusted} if fixed else None
    matched=PERIOD.fullmatch(text)
    if not matched:
        return None
    count=int(matched[1]) if matched[1].isascii() else ordinal(matched[1])
    if not count:
        return None
    unit={"年":"年","个月":"月"}.get(matched[2],"日")
    return {"unit":unit,"count":count,"fixed":None,"unadjusted":unadjusted}


def calendar_end(accepted,period):
    if period["fixed"]:
        return date.fromisoformat(period["fixed"])
    try:
        if period["unit"]=="日":
            return accepted+timedelta(days=period["count"])
        months=period["count"]*(12 if period["unit"]=="年" else 1)
        year,month=divmod(accepted.year*12+accepted.month-1+months,12)
        return date(year,month+1,min(accepted.day,calendar.monthrange(year,month+1)[1]))
    except (ValueError,OverflowError):
        return None


def release_field(field,value,quote):
    if field=="warranty":
        return normalized(value)==normalized(quote) and normalized(quote) in RELEASE_TITLES
    return covers(field,value,quote)


def inline_condition(raw):
    from performance import STAGE_PREFIX
    label,body=parts(raw)
    return INLINE.fullmatch(body.rstrip("。")) if STAGE_PREFIX.fullmatch(label+":") else None


def dedicated(raw):
    label,body=parts(raw)
    return (label in LABELS["warranty_period"] and parse_period(label,body) is not None or
            label in LABELS["warranty_condition"] and body.rstrip("。") in DEFECT_CONDITION)


def contract_kind(raw):
    from performance import STAGE_PREFIX, stage_terms
    label,body=parts(raw)
    for field in ("warranty_period","warranty_condition"):
        if label in LABELS[field]:
            return field
    if inline_condition(raw):
        return "inline_condition"
    if not MENTION.search(normalized(raw)):
        return None
    line=normalized(raw).rstrip("。")
    if STAGE_PREFIX.match(line) or label in {"付款期次","付款条款","结算条款","付款方式","结算方式","付款条件","支付条件","结算条件"}:
        if body and all(stage_terms(term)[1] for term in re.split(r"[;,。]",normalized(body).rstrip("。"))):
            return None
    return "unresolved"


def sources(graph,read_text):
    contracts=set(graph["documents_by_kind"].get("contract",[]))
    releases=set(graph["documents_by_kind"].get("warranty",[]))
    receipts=set(graph["documents_by_kind"].get("acceptance",[]))|set(graph["documents_by_kind"].get("reinspection",[]))
    sections={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    observations=defaultdict(list)
    for fact in graph["facts"]:
        observations[fact["doc"],fact["page"]].append(fact)
    covered=covered_rows(graph,read_text,releases,RELEASE_FIELDS,release_field,"质保期满确认材料")
    uncovered={(p["doc"],p["page"]):{l["line"] for l in p["uncovered"]} for p in covered}
    pages,lines=[],[]
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        number=int(suffix)
        unit=sections.get((doc,number),doc)
        if unit not in contracts|releases|receipts:
            continue
        place={"unit":unit,"doc":doc,"page":number}
        native=node.get("layer")=="text"
        pages.append({**place,"native":native,"text_only":node.get("clause_text_only") is True})
        matches=defaultdict(list)
        for fact in observations[doc,number]:
            source=fact.get("source_line")
            if native and source and source.get("rects"):
                matches[source["number"],source["text"]].append(fact["id"])
            elif unit in releases or contract_kind(fact["quote"]):
                lines.append({**place,"line":None,"kind":"observation","quote":fact["quote"],"facts":[fact["id"]]})
        if not native:
            continue
        text=read_text(doc,number)
        if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256"):
            raise ValueError("质保依据的原页文字摘要不符")
        for index,raw in enumerate(text.splitlines(),1):
            if unit in contracts:
                kind=contract_kind(raw)
            elif unit in releases:
                label,_=parts(raw)
                if label in LABELS["warranty_defects"]:
                    kind="warranty_defects"
                elif label in ("质保期满确认","质保期满记录"):
                    kind="warranty_release"
                else:
                    kind="unresolved" if index in uncovered.get((doc,number),set()) else None
            else:
                kind="unresolved" if MENTION.search(normalized(raw)) else None
            if kind:
                lines.append({**place,"line":index,"kind":kind,"quote":raw,"facts":matches[index,raw]})
    return {"format":FORMAT,"pages":pages,"lines":lines}


def identity(contract,record):
    id_fact=one(contract,"contract_id")
    if not linked(contract,record) or not id_fact or not complete_id(raw_body(id_fact)):
        return False
    if not all(labelled_sources(doc,LINK_KEYS) for doc in (contract,record)):
        return False
    for key in LINK_KEYS:
        left,right=one(contract,key),one(record,key)
        if not left or not right or raw_body(left)!=raw_body(right):
            return False
    return True


def bank_identity(contract,bank):
    labels={"payer":("付款户名","付款人名称","付款人户名"),"payee":("收款户名","收款人名称","收款人户名"),
            "transfer_status":("交易状态","转账状态")}
    def printed(field):
        if field not in labels:
            fact=one(bank,field)
            return raw_body(fact) if fact else ""
        facts=bank.fields[field]
        if len(facts)!=1 or bank.incomplete(field):
            return ""
        fact=facts[0]
        source=fact.get("source_line") or {}
        label,body=parts(source.get("text",""))
        if (not source.get("rects") or label not in labels[field] or parts(fact["quote"])!=(label,body) or
                normalized(fact["value"]) not in (normalized(body),normalized(fact["quote"]))):
            return ""
        return body
    return (bool(printed("payment_designation")) and printed("transfer_status") in {"交易成功","转账成功","成功","已完成"}
            and all((fact:=one(contract,left)) and raw_body(fact)==printed(right) for left,right in
                    (("contract_id","contract_id"),("buyer","payer"),("seller","payee"))))


def assess(graph,contract,releases,receipts,accepted,accepted_on,stage_refs):
    from performance import day, printed_day, stage_terms
    ledger=graph.get("warranty_sources",{})
    units={contract.unit,*(d.unit for d in releases),*(d.unit for d in receipts)}
    pages=[p for p in ledger.get("pages",[]) if p["unit"] in units]
    lines=[s for s in ledger.get("lines",[]) if s["unit"] in units]
    refs=contract.evidence(*LINK_KEYS,"warranty_period","warranty_condition")+accepted["evidence"]
    refs.extend(f"{p['doc']}/p{p['page']}" for p in pages)
    refs.extend(ref for s in lines for ref in s["facts"])
    for release in releases:
        refs.extend(release.evidence(*sorted(RELEASE_FIELDS)))
    problems=[]
    def finding(status,detail):
        problems.append({"status":status,"detail":detail})
    mixed=[p for p in pages if not p["native"] or not p["text_only"]]
    unknown=[s for s in lines if s["kind"] in ("unresolved","observation")]
    if not pages or mixed:
        finding("missing","质保依据含影像或版式待核，需通读相关合同、验收或确认单原页。")
    if unknown:
        finding("missing","另有尚未核清的质保约定、记录或附注。")
    clauses=[f for f in contract.fields["payment_term"]+contract.fields["payment_stage"] if f["id"] in stage_refs]
    def backed(fact):
        body=raw_body(fact)
        return bool(body and (inline_condition(fact["source_line"]["text"]) or
                    any(stage_terms(part)[1]=="warranty" for part in re.split(r"[;,。]",body.rstrip("。")))))
    if len(stage_refs)!=1 or len(clauses)!=1 or not backed(clauses[0]):
        finding("missing","需定位完整的质保金期次条款并核对其适用范围。")
    matching=bool(accepted["status"]=="ok" and accepted_on and receipts and all(identity(contract,d) for d in receipts) and
                  any(printed_day(d,"accepted_on")==accepted_on for d in receipts))
    start=accepted_on if matching else None
    if not start:
        finding("missing","需取得同一合同、双方及标的的合格终验或复验日期。")
    periods=[s for s in lines if s["kind"]=="warranty_period"]
    term_fact=one(contract,"warranty_period")
    term=None
    if term_fact and len(periods)==1 and term_fact["id"] in periods[0]["facts"]:
        term=parse_period(*parts(periods[0]["quote"]))
    if periods and not term:
        finding("missing","质保起点、期限、单位或顺延条款仍待逐行核实。")
    contractual_units={contract.unit,*(d.unit for d in receipts)}
    clear_contract=all(p["unit"] not in contractual_units for p in mixed+unknown)
    end=calendar_end(start,term) if clear_contract and term and start else None
    if clear_contract and term and start and (not end or end<start):
        finding("risk","合同质保期限无法与所列终验日期顺序对应，需核对日期或合同版本。")
        end=None
    conditions=[s for s in lines if s["kind"] in ("warranty_condition","inline_condition")]
    condition=None
    if len(conditions)==1:
        row=conditions[0]
        if row["kind"]=="warranty_condition":
            fact=one(contract,"warranty_condition")
            if fact and fact["id"] in row["facts"] and raw_body(fact).rstrip("。") in DEFECT_CONDITION:
                condition=fact
        elif len(stage_refs)==1:
            condition=next((f for f in contract.fields["payment_stage"] if f["id"]==stage_refs[0]
                            and f["id"] in row["facts"] and raw_body(f) and inline_condition(row["quote"])),None)
    needs_clear=condition is not None
    if conditions and not needs_clear:
        finding("missing","需核对合同所列质保金释放前提及履行证据。")
    release=releases[0] if len(releases)==1 else None
    pairs=[]
    if release:
        for key in LINK_KEYS:
            left,right=one(contract,key),one(release,key)
            if left and right and raw_body(left)!=raw_body(right):
                pairs.append({"field":key,"contract_ref":left["id"],"release_ref":right["id"]})
    confirmation,defect,confirmed=None,None,None
    defect_open=False
    if not release or not identity(contract,release):
        finding("missing","需核对唯一的期满确认单及其完整合同编号、采购方、供应方和标的。")
        if pairs:
            labels={"contract_id":"合同编号","buyer":"采购方","seller":"供应方","subject":"标的"}
            finding("missing","确认单所列"+ "、".join(labels[p["field"]] for p in pairs)+"与合同原文不符。")
    else:
        confirmation=one(release,"warranty_release")
        signer=one(release,"acceptance_signer")
        cert=CONFIRM.fullmatch(raw_body(confirmation)) if confirmation else None
        signature=(signer or {}).get("attestation") or {}
        if (cert and signer and signer["status"]=="confirmed" and signature.get("decision")=="confirm" and
                signature.get("source_check") and signed_name(signer["source_line"]["text"])):
            confirmed=day(cert[1])
        confirmations=[s for s in lines if s["kind"]=="warranty_release"]
        if not confirmed or len(confirmations)!=1 or confirmation["id"] not in confirmations[0]["facts"]:
            confirmed=None
            finding("missing","期满确认日期或确认单签字栏仍缺少可定位的原件和核图记录。")
        defects=[s for s in lines if s["kind"]=="warranty_defects"]
        defect=one(release,"warranty_defects")
        qualified=bool(defect and len(defects)==1 and defect["id"] in defects[0]["facts"])
        if qualified and OPEN_DEFECT.fullmatch(raw_body(defect).rstrip("。")):
            defect_open=True
            finding("risk","期满确认单仍列有未解决质量问题，需核实关闭情况及质保金可否返还。")
        elif (defects or needs_clear) and (not qualified or raw_body(defect).rstrip("。") not in NO_DEFECT):
            finding("missing","需核对质保遗留事项及合同约定的缺陷关闭依据。")
    if start and confirmed and confirmed<=start:
        finding("risk" if term and not term["fixed"] and confirmed<start else "missing",
                "期满确认日早于终验或与终验同日，需复核约定起点及实际履行时点。")
    if confirmed and end:
        if confirmed<end:
            finding("risk",f"确认单于 {confirmed} 记载期满，早于按合同复算的 {end}。")
        elif confirmed==end:
            finding("missing","确认与质保期间的最后一日同日，需核实截止时刻及签认先后。")
    if term and not term["unadjusted"]:
        finding("missing","合同未明确休假日顺延口径，请核对实际届满日。")
    status=next((s for s in ("risk","missing") if any(p["status"]==s for p in problems)),"ok")
    detail=" ".join(p["detail"] for p in problems)
    if status=="ok":
        detail=(f"按原条款复算，质保期间最后一日为 {end}，" if end else "按经核图的期满记录，")+f"确认日为 {confirmed}。"
        if needs_clear:
            detail+=" 确认单载明无未关闭缺陷。"
    return {"status":status,"detail":detail,"accepted_on":start.isoformat() if start else None,
            "calendar_end":end.isoformat() if end else None,"confirmed_on":confirmed.isoformat() if confirmed else None,
            "period":term,"requires_defect_clearance":needs_clear,"defect_open":defect_open,"term_ref":term_fact["id"] if term_fact else None,
            "condition_ref":condition["id"] if condition else None,"confirmation_ref":confirmation["id"] if confirmation else None,
            "defect_ref":defect["id"] if defect else None,"identity_conflicts":pairs,"problems":problems,
            "evidence":list(dict.fromkeys(refs)),"scope":list(dict.fromkeys([contract.unit,*accepted["scope"],*(d.unit for d in releases)]))}


def edges(findings):
    return [{"type":"warranty_release_basis","from":f["stage"]["clause_ref"],"to":w["confirmation_ref"],"evidence":f["evidence"]}
            for f in findings if f["rule"]=="H04" and f["status"]=="ok" and (w:=f.get("warranty_check")) and w["status"]=="ok"]


def verify(report,read_text,*,signing=False):
    policy,graph=report["policy"],report["graph"]
    if not policy.get("warranty_checks"):
        if "warranty_terms.py" in policy.get("code_sha256",{}) or "warranty_sources" in graph or policy.get("performance_checks") in WARRANTY_FORMATS:
            raise ValueError("质保核对程序标记缺失")
        if signing:
            positives=[f for f in report["findings"] if f["rule"] in ("H04","H05") and f["status"]=="ok"
                       and MENTION.search(f.get("stage",{}).get("clause",""))]
            if positives:
                from performance import compute
                ledger=sources(graph,read_text)
                current=compute({**graph,"warranty_sources":ledger},WARRANTY_FORMAT)
                for old in positives:
                    if not any(f.get("warranty_check",{}).get("status")==f["status"]=="ok" and f["rule"]==old["rule"]
                               and f["stage"]==old["stage"] and set(old["scope"])<=set(f["scope"]) for f in current):
                        raise ValueError("旧版质保金的约定、确认主体或整页依据尚待现行程序复核，请重新审计后签收。")
        return
    if policy["warranty_checks"]!=FORMAT or policy.get("performance_checks") not in WARRANTY_FORMATS or graph.get("warranty_sources")!=sources(graph,read_text):
        raise ValueError("质保条款、确认记录或原页版式与归档不符")
    if [e for e in graph["edges"] if e["type"]=="warranty_release_basis"]!=edges(report["findings"]):
        raise ValueError("质保金期次所据的期满确认关系与归档不符")
    expected=sorted((f.get("unit",f["doc"]),f["id"],f["field"],(f["id"],)) for f in graph["facts"]
                    if f["field"] in LABELS and f["status"] in ("anchored","confirmed"))
    actual=sorted((e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"] if e["type"] in LABELS)
    if actual!=expected:
        raise ValueError("质保约定或缺陷记录与其原件证据关系不符")
