"""Read phase-specific payment deadlines from originals and compare them to a successful transfer."""

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from calculations import normalized
from cn_workdays import SOURCE as CALENDAR_NOTICE, SOURCE_KEY, after_workdays
from delegation import complete_id
from delivery_batches import one, ordinal, raw_body
from performance_versions import PAYMENT_WINDOW_FORMAT, PAYMENT_WINDOW_FORMATS
from warranty_terms import DATE, NO_EXTENSION, bank_identity, identity


FORMAT="phase-payment-window-v1"
FIELD="payment_deadline"
ROLES={"首付款":"effect","预付款":"effect","验收款":"acceptance","质保金":"warranty","尾款":"尾款","进度款":"进度款"}
NUMBER=r"(?:[1-9][0-9]{0,2}|[一二两三四五六七八九十]{1,3})"
ORDINAL=r"第("+NUMBER+r")期"
PHASE=re.compile(ORDINAL+"|"+"|".join(ROLES))
ENDING=("最迟付款日","最迟支付日","付款截止日","支付截止日","付款期限","支付期限","付款时限","支付时限")
LABELS={FIELD:tuple(p+t for p in ("验收款","预付款","首付款","") for t in ENDING)}
LABELED=re.compile(r"(?:"+PHASE.pattern+r")?(?:"+"|".join(ENDING)+r")")
EVENT=r"(?:本?合同生效|最终验收合格|终验合格|全部验收合格|验收合格)"
RELATIVE=re.compile(r"(?:自)?("+EVENT+r")(?:之日起|之日后|后)("+NUMBER+r")(个工作日|工作日|个自然日|自然日|天|日)内(?:应)?(?:支付|付款|付清)(?:合同(?:总价|价款|总额)的?)?([0-9]{1,3}(?:\.[0-9]{1,4})?%)?")
FIXED=re.compile(r"(?:应于|最迟于)?("+DATE+r")(?:前|之前)?(?:付款|支付)?")
NATIONAL={"按国家调休日历","按国务院调休安排","按国务院办公厅公布的节假日及调休安排"}
HINT=re.compile(r"(?:付款|支付|结算|预付款|验收款|尾款|质保金|款项|到账).{0,18}(?:截止|最迟|最晚|到期|期限|时限|宽限|工作日|自然日|不得早于|不得晚于|不晚于|延期|展期)|"
                r"(?:最迟|最晚|不得早于|不得晚于|不晚于|应于|限于|延至|延期|展期|顺延|暂缓|推迟|延期至).{0,32}(?:付款|支付|付清|结算|到账)|"
                r"(?:工作日|自然日|天|日|周|月|年)(?:以内|之内|内|前|后|起).{0,9}(?:支付|付款|结算|付清|到账)|"
                r"(?:验收|生效|签署|开票|收票).{0,18}[0-9一二三四五六七八九十]+(?:个)?(?:天|日|月|工作日|自然日).{0,12}(?:支付|付款|结算|付清|到账)|"
                r"(?:以|按).{0,14}(?:到账|入账|银行营业日|企业工作日).{0,10}(?:为准|计算)")
BANK="bank_receipt"
BANK_HOLD=re.compile(r"冲正|退汇|撤销|转账失败|退款|退票|取消交易|待入账")


def split_line(raw):
    label,separator,body=unicodedata.normalize("NFKC",raw).strip().partition(":")
    return label.strip(),body.strip() if separator else ""


def label_matches(label):
    return bool(LABELED.fullmatch(label))


def spec(raw):
    """Accept a complete clause only. Embedded digits, extra conditions and other clocks stay unresolved."""
    from performance import STAGE_PREFIX, day
    label,body=split_line(raw)
    inline=bool(STAGE_PREFIX.fullmatch(label+":"))
    if not body or not (inline or label_matches(label)):
        return None
    text=body.rstrip("。")
    phase=PHASE.match(text)
    if phase and label in ENDING:
        text=text[phase.end():].lstrip(":")
    if "(" in text or ")" in text:
        parenthetical=re.fullmatch(r"([^(),]+)\(([^(),]+)\)",text)
        if not parenthetical:
            return None
        pieces=list(parenthetical.groups())
    else:
        pieces=text.split(",")
    suffix=pieces[1] if len(pieces)==2 else ""
    if len(pieces)>2 or len(pieces)==2 and suffix not in NO_EXTENSION|NATIONAL:
        return None
    match=RELATIVE.fullmatch(pieces[0])
    if match:
        event,amount,unit,share=match.groups()
        if inline!=bool(share):
            return None
        count=int(amount) if amount.isascii() else ordinal(amount)
        if not count or not 0<count<=999:
            return None
        work="工作日" in unit
        if work and suffix in NO_EXTENSION or not work and suffix in NATIONAL:
            return None
        return {"trigger":"effect" if "生效" in event else "acceptance","trigger_text":event,
                "count":count,"basis":"working" if work else "calendar","fixed":None,
                "national":suffix in NATIONAL,"unadjusted":suffix in NO_EXTENSION,"share":share[:-1] if share else None}
    if not inline and re.search(r"截止日|最迟(?:付款|支付)日",label) and suffix not in NATIONAL:
        match=FIXED.fullmatch(pieces[0])
        # A bare dated field is inclusive. Wording such as "之前" needs the original convention.
        fixed=day(match[1]) if match and pieces[0]==match[1] else None
        if fixed:
            return {"trigger":None,"trigger_text":None,"count":None,"basis":"fixed","fixed":fixed.isoformat(),
                    "national":False,"unadjusted":suffix in NO_EXTENSION,"share":None}
    return None


def selectors(raw):
    # Keep meaningful boundaries in the original. "第1 2期" cannot become period twelve.
    label,body=split_line(raw)
    result=[]
    for match in PHASE.finditer(label+" "+body):
        if match[1]:
            value=int(match[1]) if match[1].isascii() else ordinal(match[1])
            key="phase:"+str(value) if value else "unknown"
        else:
            key=ROLES[match[0]]
        if key not in result:
            result.append(key)
    return result


def scoped_row(raw):
    label,_=split_line(raw)
    return label_matches(label) and len(selectors(raw))==1 and spec(raw) is not None


def mentions(raw):
    label,_=split_line(raw)
    return label_matches(label) or bool(HINT.search(normalized(raw)))


def sources(graph,read_text):
    sections={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    kinds={unit:kind for kind,units in graph["documents_by_kind"].items() for unit in units}
    by_page=defaultdict(list)
    for f in graph["facts"]:
        by_page[f["doc"],f["page"]].append(f)
    pages,lines=[],[]
    for n in graph["nodes"]:
        if n["type"]!="page":
            continue
        doc,suffix=n["id"].rsplit("/p",1)
        page=int(suffix)
        unit=sections.get((doc,page),doc)
        kind=kinds.get(unit,"other")
        place={"doc":doc,"page":page,"unit":unit,"document_kind":kind}
        native=n.get("layer")=="text"
        facts=by_page[doc,page]
        def relevant(raw):
            return mentions(raw) or kind==BANK and bool(BANK_HOLD.search(normalized(raw)))
        anchored=defaultdict(list)
        for f in facts:
            loc=f.get("source_line") or {}
            if native and loc.get("rects"):
                anchored[loc["number"],loc["text"]].append(f)
            elif f["field"]==FIELD or relevant(f["quote"]):
                lines.append({**place,"line":None,"quote":f["quote"],"facts":[f["id"]],"targets":selectors(f["quote"])})
        if native:
            text=read_text(doc,page)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=n.get("text_sha256"):
                raise ValueError("付款时限所据的原页文字摘要不符")
            for i,raw in enumerate(text.splitlines(),1):
                found=anchored[i,raw]
                if relevant(raw) or any(f["field"]==FIELD for f in found):
                    lines.append({**place,"line":i,"quote":raw,"facts":[f["id"] for f in found],"targets":selectors(raw)})
        pages.append({**place,"native":native,"text_only":n.get("clause_text_only") is True})
    return {"format":FORMAT,"pages":pages,"lines":lines}


def row_targets(line,rows):
    hits=set()
    for target in line["targets"]:
        for i,r in enumerate(rows):
            if target in (r["kind"],r["label"],"phase:"+str(r["index"])):
                hits.add(i)
    return hits


def located_day(doc,field):
    from performance import DATE_LABELS, day, printed_day
    facts=doc.fields[field]
    if len(facts)!=1 or doc.incomplete(field):
        return None,None
    fact=facts[0]
    source=fact.get("source_line") or {}
    label,value=split_line(source.get("text",""))
    when=day(value)
    if not when or not source.get("rects") or label not in DATE_LABELS[field] or split_line(fact["quote"])!=(label,value) or printed_day(doc,field)!=when:
        return None,None
    return when,fact["id"]


def stage_window(graph,contract,rows,index,receipts,signed,accepted,accepted_on,check,*,separate_opinions=()):
    ledger=graph.get("payment_window_sources",{})
    row=rows[index]
    lines=[s for s in ledger.get("lines",[]) if s["document_kind"]!=BANK and index in (row_targets(s,rows) or range(len(rows)))
           and (s["doc"],s["page"],s["line"],s["quote"]) not in separate_opinions]
    relevant={contract.unit}
    if row["kind"] in ("acceptance","batch","warranty"):
        relevant.update(d.unit for d in receipts)
    relevant.update(s["unit"] for s in lines)
    mixed=[p for p in ledger.get("pages",[]) if p["unit"] in relevant and (not p["native"] or not p["text_only"])]
    if not lines and not mixed:
        return None
    refs=[row["ref"]]
    refs.extend(f"{s['doc']}/p{s['page']}" for s in [*lines,*mixed])
    refs.extend(ref for s in lines for ref in s["facts"])
    entry={"state":"unresolved","detail":"","term_ref":None,"trigger_ref":None,"trigger_on":None,"calendar_end":None,
           "terms":None,"days":[],"calendar_source":None,"lines":lines,"mixed_pages":mixed,
           "scope":list(dict.fromkeys([*check["scope"],*(s["unit"] for s in lines),*(p["unit"] for p in mixed)])),
           "evidence":list(dict.fromkeys(refs))}
    def pending(detail):
        entry["detail"]=detail
        return entry
    if mixed:
        return pending("付款相关原页含影像或批注，须核对是否另列付款时限或起算条件。")
    if len(lines)!=1 or lines[0]["unit"]!=contract.unit:
        return pending("需核对付款时限的适用期次、合同版本和其他文件的记载。")
    line=lines[0]
    unambiguous=row_targets(line,rows)=={index} if line["targets"] else len(rows)==1
    if not unambiguous or len(line["targets"])>1:
        return pending("付款时限所指期次待核，需核对明确的期号或期名。")
    raw=line["quote"]
    parsed=spec(raw)
    candidates=[f for f in contract.fields[FIELD]+contract.fields["payment_stage"]
                if f["id"] in line["facts"] and raw_body(f) and (f["field"]==FIELD or f["id"]==row["ref"])]
    if len(candidates)!=1 or not line["line"] or not parsed:
        return pending("需定位完整的付款期限原文，核对起点、天数、日历及其他付款条件。")
    proof=candidates[0]
    if (proof["field"]=="payment_stage")!=bool(parsed["share"]):
        return pending("付款期次与单列时限的原文字段归属待核。")
    entry.update(terms=parsed,term_ref=proof["id"])
    if row["kind"] not in ("acceptance","effect") or parsed["trigger"] and parsed["trigger"]!=row["kind"]:
        return pending("付款期限的起算事件尚不能与该期履约条件对应。")
    stage_fact=next((f for f in contract.fields["payment_term"]+contract.fields["payment_stage"] if f["id"]==row["ref"]),None)
    from performance import stage_terms
    if (not stage_fact or not raw_body(stage_fact) or row["label"] and split_line(stage_fact["source_line"]["text"])[0]!=row["label"]
            or proof["id"]!=row["ref"] and stage_terms(raw_body(stage_fact).rstrip("。"))[1]!=row["kind"]):
        return pending("需逐字核对本期付款条款、比例及其与时限的对应关系。")
    identifier=one(contract,"contract_id")
    if signed["status"]!="ok" or check["status"]!="ok" or not identifier or not complete_id(raw_body(identifier)):
        return pending("须先核实合同生效、本期履约条件和完整合同编号。")
    if row["kind"]=="effect":
        start,start_ref=located_day(contract,"effect_on")
    else:
        matches=[(dt,ref) for doc in receipts for dt,ref in [located_day(doc,"accepted_on")] if dt and dt==accepted_on]
        if accepted["status"]!="ok" or not receipts or not all(identity(contract,d) for d in receipts) or len(matches)!=1:
            return pending("须取得同一合同、双方和标的的合格终验或复验日期。")
        start,start_ref=matches[0]
    if not start:
        return pending("付款期限的起算日期仍缺少可定位的原件。")
    entry.update(trigger_on=start.isoformat(),trigger_ref=start_ref)
    entry["evidence"]=list(dict.fromkeys([*entry["evidence"],start_ref]))
    if parsed["basis"]=="fixed":
        end=date.fromisoformat(parsed["fixed"])
    elif parsed["basis"]=="calendar":
        try:
            end=start+timedelta(days=parsed["count"])
        except OverflowError:
            return pending("付款时限超出可核日期范围。")
    elif parsed["national"]:
        entry["calendar_source"]=SOURCE_KEY
        entry["evidence"].append("source/"+SOURCE_KEY)
        end,entry["days"]=after_workdays(start,parsed["count"])
        if not end:
            return pending("期间超出已核实的全国调休日历年份，需补充日历依据。")
    else:
        return pending("须确定合同所指工作日历及调休安排，才能复算最后付款日。")
    entry["calendar_end"]=end.isoformat()
    if end<start:
        entry["state"]="conflict"
        return pending("合同列明的最后付款日早于本期履约起点，两项约定和履行记录需核实。")
    entry["state"]="fixed" if parsed["national"] or parsed["unadjusted"] else "nominal"
    entry["detail"]=f"本期履约起点为 {start}，按原条款计算的付款末日为 {end}。"
    if entry["state"]=="nominal":
        entry["detail"]+=" 实际末日还须结合休假日顺延及合同约定。"
    return entry


def attach_stage(check,entry):
    if not entry:
        return
    check["payment_window"]=entry
    check["evidence"]=list(dict.fromkeys(check["evidence"]+entry["evidence"]))
    check["scope"]=entry["scope"]
    if check["status"]=="ok" and entry["state"] in ("unresolved","conflict"):
        check["status"]="risk" if entry["state"]=="conflict" else "missing"
    check["detail"]+=" "+entry["detail"]


def compare_transfer(payment,check,graph,contract,bank,row):
    from performance import matches_stage
    ledger=graph.get("payment_window_sources",{})
    lines=[s for s in ledger.get("lines",[]) if s["unit"]==bank.unit]
    if "payment_window" not in check:
        if lines:
            refs=[*(f"{s['doc']}/p{s['page']}" for s in lines),*(ref for s in lines for ref in s["facts"])]
            payment["payment_window"]={"state":"unresolved","detail":"回单另载期限或交易状态，请核实合同与实际付款原件。",
                "term_ref":None,"trigger_ref":None,"trigger_on":None,"calendar_end":None,"terms":None,"days":[],
                "calendar_source":None,"lines":lines,"mixed_pages":[],"scope":payment["scope"],"evidence":refs,
                "outcome":"unresolved","paid_on":None,"paid_ref":None,"days_late":None}
            payment["evidence"]=list(dict.fromkeys([*payment["evidence"],*refs]))
            payment.update(status="missing",detail=payment["payment_window"]["detail"])
        return
    entry={**check["payment_window"],"outcome":"unresolved","paid_on":None,"paid_ref":None,"days_late":None}
    payment["payment_window"]=entry
    paid,ref=located_day(bank,"paid_on")
    designation=one(bank,"payment_designation")
    if not paid or not designation or not matches_stage(raw_body(designation),row) or not bank_identity(contract,bank):
        payment.update(status="missing",detail="需核对原始回单的合同编号、户名、款项用途、成功状态及付款日期。")
        return
    entry.update(paid_on=paid.isoformat(),paid_ref=ref)
    mixed=[p for p in ledger["pages"] if p["unit"]==bank.unit and (not p["native"] or not p["text_only"])]
    entry["lines"]=[*entry["lines"],*lines]
    entry["mixed_pages"]=[*entry["mixed_pages"],*mixed]
    entry["scope"]=list(dict.fromkeys([*entry["scope"],bank.unit]))
    refs=[ref,*(f"{s['doc']}/p{s['page']}" for s in [*lines,*mixed]),*(r for s in lines for r in s["facts"])]
    entry["evidence"]=list(dict.fromkeys([*entry["evidence"],*refs]))
    payment["evidence"]=list(dict.fromkeys([*payment["evidence"],*refs]))
    if mixed or lines:
        payment.update(status="missing",detail="回单含影像、时点说明或交易状态附注，须核实实际支付及适用的时间口径。")
        return
    if entry["state"] not in ("fixed","nominal"):
        payment["detail"]+=" "+entry["detail"]
        return
    start=date.fromisoformat(entry["trigger_on"])
    end=date.fromisoformat(entry["calendar_end"])
    if paid<start:
        entry["outcome"]="early"
        payment.update(status="risk",detail=f"回单记载 {paid} 付款，早于本期履约起点 {start}，需核对提前付款依据。")
    elif paid==start or paid==end:
        entry["outcome"]="same_day"
        label="履约起点" if paid==start else "付款末日"
        payment.update(status="missing",detail=f"回单付款日与{label}同为 {paid}，需核实截止时刻、业务时间及实际支付时分。")
    elif paid>end and entry["state"]=="fixed":
        entry.update(outcome="late",days_late=(paid-end).days)
        payment.update(status="risk",detail=f"回单记载 {paid} 付款，晚于约定末日 {end} 共 {(paid-end).days} 个自然日，请核实延期约定或实际履行依据。")
    elif paid>end:
        entry["outcome"]="extension_unknown"
        payment.update(status="missing",detail=f"回单付款日 {paid} 晚于日历末日 {end}，实际期限须核对顺延约定及适用的休假日。")
    elif payment["status"]=="ok":
        entry["outcome"]="within"
        payment["detail"]=f"本笔回单于 {paid} 支付，在履约起点 {start} 之后、约定的日历末日 {end} 之前。"


def edges(findings):
    result=[]
    for f in findings:
        w=f.get("payment_window") or {}
        if f["rule"]=="H05" and w.get("outcome") in ("within","early","late","same_day","extension_unknown"):
            result.append({"type":"payment_window_comparison","from":w["term_ref"],"to":w["paid_ref"],
                           "outcome":w["outcome"],"evidence":f["evidence"]})
    return result


def verify(report,read_text,*,signing=False):
    policy,graph=report["policy"],report["graph"]
    marker=policy.get("payment_windows")
    if not marker:
        if "payment_windows.py" in policy.get("code_sha256",{}) or "payment_window_sources" in graph or policy.get("performance_checks") in PAYMENT_WINDOW_FORMATS:
            raise ValueError("付款时限核对程序标记缺失")
        if not signing:
            return
        old=[f for f in report["findings"] if f["rule"] in ("H04","H05") and f["status"]=="ok" and f.get("stage")]
        if old:
            from performance import compute
            ledger=sources(graph,read_text)
            current=compute({**graph,"payment_window_sources":ledger},PAYMENT_WINDOW_FORMAT)
            for former in old:
                for new in current:
                    if (new.get("payment_window") and new["rule"]==former["rule"] and new.get("stage")==former["stage"]
                            and set(former["scope"])<=set(new["scope"]) and new["status"]!="ok"):
                        raise ValueError("旧版付款时限或回单时点仍需核对，请按现行程序重新审计后签收。")
        return
    if marker!=FORMAT or policy.get("performance_checks") not in PAYMENT_WINDOW_FORMATS or graph.get("payment_window_sources")!=sources(graph,read_text):
        raise ValueError("付款期限、原页文字或影像覆盖与归档不符")
    if [e for e in graph["edges"] if e["type"]=="payment_window_comparison"]!=edges(report["findings"]):
        raise ValueError("合同付款期限与实际回单的比较关系不符")
    scheduled=[f for f in report["findings"] if (f.get("payment_window") or {}).get("calendar_source")==SOURCE_KEY]
    if scheduled:
        source="source/"+SOURCE_KEY
        node={"id":source,"type":"method_reference","label":CALENDAR_NOTICE["title"],**CALENDAR_NOTICE}
        if policy.get("sources",{}).get(SOURCE_KEY)!=CALENDAR_NOTICE or node not in graph["nodes"] or any(
                source not in f["evidence"] or {"from":source,"to":"finding/"+f["id"],"type":"supports_result","evidence":[source]} not in graph["edges"]
                for f in scheduled):
            raise ValueError("工作日计算未关联当版采用的年度调休依据")
    wanted=sorted((f.get("unit",f["doc"]),f["id"],(f["id"],)) for f in graph["facts"] if f["field"]==FIELD and f["status"] in ("anchored","confirmed"))
    actual=sorted((e["from"],e["to"],tuple(e["evidence"])) for e in graph["edges"] if e["type"]==FIELD)
    if wanted!=actual:
        raise ValueError("付款期限未关联其所属原件")
