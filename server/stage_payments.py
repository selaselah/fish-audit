"""Reconcile the gross transfers submitted together against each printed installment."""

import hashlib
import re
from collections import defaultdict
from decimal import Decimal
from unicodedata import normalize

from acceptance_authority import TITLES, covers, parts
from calculations import AMOUNT
from delegation import complete_id, covered_rows
from delivery_batches import ordinal
from installments import iso_day
from payment_reference import masked_value


FORMAT = "submitted-stage-transfers-v1"
SINCE = "2026.11.25.12"
RULE = ("本期多份回单与约定金额", "按原合同价款与期次比例计算本期约定金额，按同一合同的完整成功流水去重，比对本次提交回单，并另核合同与履约前提。")
BANK_TITLES = {"银行付款回单","银行转账回单","电子银行回单","银行电子回单","转账回单"}
LABELS = {"total":("含税总额","含税总价","价税合计","含税合计"),"currency":("币种","结算货币"),"unit":("金额单位","计价单位"),
          "contract_id":("合同编号","合同号"),"buyer":("采购方","甲方","买方"),"seller":("供应方","乙方","卖方"),
          "payer":("付款户名","付款人名称","付款人户名"),"payee":("收款户名","收款人名称","收款人户名"),
          "transfer_ref":("交易流水号","银行流水号"),"transfer_status":("交易状态","转账状态"),
          "transfer_amount":("付款金额","转账金额","交易金额"),"paid_on":("付款日期","转账日期","交易日期"),
          "payment_designation":("款项用途","付款用途","款项性质","对应期次","付款期次"),
          "payee_account":("收款账号","收款账户","收款人账号"),"contract_account":("约定收款账号","合同收款账号")}
CONTRACT = {"equipment_model","contract","contract_id","buyer","seller","subject","signed_on","effect_on","valid_until","effect_clause","contract_state",
            "buyer_signature","seller_signature","buyer_sealed_on","seller_sealed_on","payment_term","payment_stage","total","currency","unit",
            "acceptance_criteria","quantity_agreed","delivery_batch","batch_clause","acceptance_signing_clause","warranty_period",
            "warranty_condition","payment_deadline","contract_account"}
BANK = {"bank_receipt","contract_id","payer","payee","transfer_ref","transfer_status","transfer_amount","paid_on","payment_designation",
        "currency","unit","payee_account"}
SUCCESS = {"交易成功","转账成功","成功","已完成"}
RIDER = re.compile(r"退款|退汇|返款|冲正|冲销|撤销|抵[扣销]|扣[减款]|调价|折让|折扣|据实|另行结算|另行核价|代付|代收|垫付|跨期|上期结转|预付.{0,5}抵|尾差")
CLAUSE = re.compile(r"(?:合同生效|最终验收合格|终验合格|验收合格|质保期满|第[一二三四五六七八九十\d]+批验收合格)后"
                    r"(?:支付|付)(?:合同(?:含税)?总(?:价|额)的)?(\d{1,3}(?:\.\d{1,4})?)%[。.]?")


def literal(value):
    return normalize("NFKC",value).strip()


def is_printed(field,value,quote):
    if field in ("contract","bank_receipt"):
        titles = BANK_TITLES if field=="bank_receipt" else TITLES["contract"]
        return literal(quote) in titles and literal(value)==literal(quote)
    if field not in LABELS:
        return covers(field,value,quote)
    label,body = parts(quote)
    return bool(body and label in LABELS[field] and literal(value) in (body,literal(quote)))


def sources(graph,read_text):
    units = graph.get("audit_documents",graph["documents"])
    unit_by_page = {(u["source"],u["page"]):u["id"] for u in units if "source" in u}
    by_page = defaultdict(list)
    for f in graph["facts"]:
        by_page[f["doc"],f["page"]].append(f)
    bank_pages = {(f["doc"],f["page"]) for f in graph["facts"] if f["field"] in ("bank_receipt","transfer_ref","transfer_amount","transfer_status")}
    bank_pages.update((g["doc"],g["page"]) for g in graph["gaps"] if g.get("title_hint")=="bank_receipt"
                      or g.get("field") in ("transfer_ref","transfer_amount","transfer_status"))
    kinds=graph["documents_by_kind"]
    other={u for k,group in kinds.items() if k!="bank_receipt" for u in group}
    bank_pages={key for key in bank_pages if unit_by_page.get(key,key[0]) not in other or
                any(f["field"]=="bank_receipt" for f in by_page[key])}
    ledger={"format":FORMAT,"banks":[],"pages":[],"notes":[],"unknown_units":[],"ambiguous_units":[]}
    counts=defaultdict(int)
    repeated=set()
    for d,n in sorted(bank_pages):
        unit=unit_by_page.get((d,n),d)
        counts[unit]+=1
        text=read_text(d,n)
        columns=[parts(line)[0] for line in text.splitlines()]
        if (sum(literal(line) in BANK_TITLES for line in text.splitlines())>1 or
                any(sum(k in LABELS[field] for k in columns)>1 for field in ("transfer_ref","transfer_amount"))):
            repeated.add(unit)
    prior_terms = graph.get("prior_installment_sources", {}).get("lines", [])
    if len(bank_pages)<2 and not repeated and not prior_terms:
        return ledger
    banks = {unit_by_page.get((d,n),d) for d,n in bank_pages}
    ledger["banks"] = [u["id"] for u in units if u["id"] in banks]
    ledger["ambiguous_units"]=[u for u in ledger["banks"] if counts[u]>1 or u in repeated]
    known={u for k,group in kinds.items() if k!="contract_addendum" for u in group}
    from warranty_service import classified
    ticket_units,bounded_tickets=classified(graph.get("warranty_sources",{}))
    known=(known-ticket_units)|bounded_tickets
    ledger["unknown_units"]=[u["id"] for u in units if u["id"] not in known]
    coverage=covered_rows(graph,read_text,set(kinds.get("contract",[])),CONTRACT,is_printed,"分期合同")
    covered_terms = {(r["doc"], r["page"], r["line"], r["quote"]) for r in prior_terms if r["supported"] or r.get("credit_only")}
    for page in coverage:
        page["uncovered"] = [r for r in page["uncovered"]
                             if (page["doc"], page["page"], r["line"], r["quote"]) not in covered_terms]
    coverage+=covered_rows(graph,read_text,banks,BANK,is_printed,"分笔付款回单")
    bound={(p["doc"],p["page"]):p for p in coverage}
    partial={(g["doc"],g["page"]) for g in graph["gaps"] if g["quality"] in ("partial","unreadable")}
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc,suffix=node["id"].rsplit("/p",1)
        n=int(suffix)
        unit=unit_by_page.get((doc,n),doc)
        entry={"doc":doc,"page":n,"unit":unit,"text_only":node.get("clause_text_only") is True and node.get("layer")=="text",
               "uncovered":bound.get((doc,n),{}).get("uncovered",[]),"partial":(doc,n) in partial}
        ledger["pages"].append(entry)
        facts=by_page[doc,n]
        if node.get("layer")=="text":
            raw=read_text(doc,n)
            if hashlib.sha256(raw.encode()).hexdigest()!=node["text_sha256"]:
                raise ValueError("分期支付原页与归档文字摘要不符")
            for line,quote in enumerate(raw.splitlines(),1):
                if RIDER.search(literal(quote)):
                    refs=[f["id"] for f in facts if (f.get("source_line") or {}).get("number")==line and f["quote"]==quote]
                    ledger["notes"].append({"doc":doc,"page":n,"line":line,"quote":quote,"facts":refs})
        for f in facts:
            if not (f.get("source_line") or {}).get("rects") and RIDER.search(literal(f["quote"])):
                ledger["notes"].append({"doc":doc,"page":n,"line":None,"quote":f["quote"],"facts":[f["id"]]})
    return ledger


def printed(doc,field):
    rows=doc.fields[field]
    if len(rows)!=1 or doc.incomplete(field):
        return None
    f=rows[0]
    line=f.get("source_line") or {}
    if (not line.get("rects") or literal(line["text"])!=literal(f["quote"]) or
            not is_printed(field,f["value"],line["text"])):
        return None
    return {"ref":f["id"],"value":parts(line["text"])[1]}


def amount(inputs,field):
    if not all(inputs.get(k) for k in (field,"currency","unit")):
        return None
    value=inputs[field]["value"]
    if (inputs["currency"]["value"].upper() not in {"人民币","人民币元","CNY","RMB"} or
            inputs["unit"]["value"] not in {"元","人民币元"} or not AMOUNT.fullmatch(value)):
        return None
    result=Decimal(value.replace(",",""))
    return result if result>0 else None


def same_stage(left,right):
    if left and left==right:
        return True
    first,second=(re.fullmatch(r"第([一二三四五六七八九十\d]+)期",value) for value in (left,right))
    return bool(first and second and ordinal(first[1]) is not None and ordinal(first[1])==ordinal(second[1]))


def bank_record(graph,contract,bank,checks):
    values={k:printed(bank,k) for k in ("payer","payee","contract_id","payment_designation","paid_on","transfer_status",
                                        "transfer_amount","currency","unit","transfer_ref","payee_account")}
    v={k:r["value"] if r else "" for k,r in values.items()}
    paid=amount(values,"transfer_amount")
    reasons=[]
    if any(not contract.get(a) or contract[a]["value"]!=v[b] for a,b in (("buyer","payer"),("seller","payee"),("contract_id","contract_id"))):
        reasons.append("合同号或收付主体缺少完整对应的原文")
    account=contract.get("contract_account")
    if account and (not re.fullmatch(r"[0-9]{8,32}",account["value"]) or v["payee_account"]!=account["value"]):
        reasons.append("合同指定收款账号与回单尚未逐位核实")
    date=iso_day(v["paid_on"]) if not re.search(r"\d\s+\d",v["paid_on"]) else None
    if v["transfer_status"] not in SUCCESS or not date:
        reasons.append("成功状态或实付日期待核")
    if paid is None:
        reasons.append("付款金额、人民币币种或元单位待核")
    ref=v["transfer_ref"]
    held={r["fact"] for r in graph.get("transfer_references",{}).get("facts",[])}
    complete=bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",ref) and re.search(r"\d",ref)
                  and not masked_value(ref) and (values["transfer_ref"] or {}).get("ref") not in held)
    if not complete:
        reasons.append("需取得完整交易流水号")
    matched=[c["stage"] for c in checks if same_stage(c["stage"]["name"],v["payment_designation"])]
    if len(matched)!=1:
        reasons.append("回单用途未唯一指明合同期次")
    return {"unit":bank.unit,"date":date,"reference":ref or None,"reference_complete":complete,"amount":fmt(paid),"inputs":values,"reasons":reasons,
            "stage_ref":matched[0]["clause_ref"] if len(matched)==1 else None,
            "stage_name":matched[0]["name"] if len(matched)==1 else None,"duplicate_of":None}


def fmt(number):
    return format(number,".2f") if number is not None else None


def expected_amount(stage, facts, contracts, total):
    clause = facts.get(stage.get("clause_ref"))
    source = (clause or {}).get("source_line") or {}
    label, body = parts(source.get("text", ""))
    match = CLAUSE.fullmatch(body)
    if (not match or not source.get("rects") or literal(clause["quote"]) != literal(source["text"])
            or clause["status"] not in ("anchored", "confirmed") or clause.get("unit", clause["doc"]) not in contracts
            or not same_stage(label, stage["name"]) or not stage["share"] or Decimal(match[1]) != Decimal(stage["share"])
            or total is None):
        return None, "未取得按固定合同总额和本期比例付款的完整原行"
    value = total * Decimal(match[1]) / 100
    if value != value.quantize(Decimal(".01")):
        return None, "本期金额不足整分，需明确尾差约定"
    return value, None


def findings(graph,checks):
    from performance import Material, result
    ledger=graph.get("stage_payment_sources",{})
    if not ledger.get("banks"):
        return []
    kinds=graph["documents_by_kind"]
    contracts=kinds.get("contract",[])
    contract=Material(graph,contracts[0]) if len(contracts)==1 else None
    base={k:printed(contract,k) if contract else None for k in ("buyer","seller","contract_id","total","currency","unit","contract_account")}
    total=amount(base,"total")
    phases=[f for f in checks if f["rule"]=="H04" and f.get("stage")]
    transfers=[f for f in checks if f["rule"]=="H05"]
    records=[bank_record(graph,base,Material(graph,u),phases) for u in ledger["banks"]]
    reasons=[]
    if (not contract or not base["contract_id"] or not complete_id(base["contract_id"]["value"]) or
        any(not base[k] or masked_value(base[k]["value"]) or base[k]["value"] in ("同上","待核","未知","见附件","无","略","甲方","乙方")
            for k in ("buyer","seller","contract_id"))):
        reasons.append("需确定唯一现行合同和完整合同号")
    if contract and (contract.fields["contract_account"] or contract.incomplete("contract_account")) and not base["contract_account"]:
        reasons.append("合同指定收款账号的原行尚待核对")
    if total is None:
        reasons.append("合同含税总额、人民币币种或元单位待核")
    if not any(f["rule"]=="H03" and f["status"]=="ok" for f in checks):
        reasons.append("付款安排与比例待核")
    if ledger["unknown_units"] or ledger["notes"]:
        reasons.append("有待核附注、调整事项或未归属材料")
    if any(not p["text_only"] or p["uncovered"] or p["partial"] for p in ledger["pages"]):
        reasons.append("存在需核对的原页影像或未核原行")
    if any(r["unit"] not in kinds.get("bank_receipt",[]) or not r["stage_ref"] for r in records):
        reasons.append("有回单原件或期次尚未归属")
    if ledger["ambiguous_units"]:
        reasons.append("同一资料内有多页或多组回单栏位，需厘清每笔交易的单据边界")
    seen={}
    for r in records:
        key=(r["reference"] or "").casefold()
        if not r["reference_complete"]:
            continue
        previous=seen.setdefault(key,r)
        if previous is r:
            continue
        fields=("payer","payee","payee_account","contract_id","payment_designation","transfer_ref")
        identical=not (previous["reasons"] or r["reasons"]) and all(previous[k]==r[k] for k in ("date","stage_ref","stage_name","amount")) and all(
            (previous["inputs"][k] or {}).get("value")== (r["inputs"][k] or {}).get("value") for k in fields)
        if not identical:
            reasons.append("同一流水所载金额、日期、用途或主体不一致")
        else:
            r["duplicate_of"]=previous["unit"]
    groups=[(p,[r for r in records if (r["stage_ref"],r["stage_name"])==(p["stage"]["clause_ref"],p["stage"]["name"])]) for p in phases]
    groups.append((None,[r for r in records if not r["stage_ref"]]))
    facts={f["id"]:f for f in graph["facts"]}
    by_bank={}
    for payment in transfers:
        title=next((facts.get(ref) for ref in payment["evidence"] if (facts.get(ref) or {}).get("field")=="bank_receipt"),None)
        if title:
            by_bank[title.get("unit",title["doc"])]=(title["id"],payment)
    output=[]
    for phase,group in groups:
        if not group:
            continue
        stage=phase["stage"] if phase else None
        issue=list(reasons)
        expected = None
        if stage:
            expected, reason = expected_amount(stage, facts, contracts, total)
            if reason:
                issue.append(reason)
        for r in group:
            issue.extend(r["reasons"])
        issue=list(dict.fromkeys(issue))
        paid=delta=None
        state,status="unresolved","missing"
        if expected is not None and not issue:
            paid=sum(Decimal(r["amount"]) for r in group if not r["duplicate_of"])
            delta=paid-expected
            state,status=("over","risk") if delta>0 else ("partial","missing") if delta<0 else ("balanced","ok")
            if any(r["duplicate_of"] for r in group) and status=="ok":
                status="risk"
        label=stage["name"] if stage else "期次待分配"
        detail=f"{label}，"+"。".join(issue)+"。" if issue else (
            f"{label}约定 {fmt(expected)} 元，本次所见成功回单按完整流水去重后合计 {fmt(paid)} 元。"+
            (f"超过本期约定 {fmt(delta)} 元，请核对银行对账单及调整依据。" if delta>0 else
             f"与约定相差 {fmt(-delta)} 元，请确认其余回单或结算安排。" if delta<0 else "所见合计与本期约定相符。"))
        if any(r["duplicate_of"] for r in group):
            detail+=" 同一流水重复出现，请对照两份原页确认是否属于同一笔交易。"
        related=[by_bank[r["unit"]][1] for r in group if r["unit"] in by_bank]
        timing=[{"unit":r["unit"],"receipt_ref":by_bank[r["unit"]][0] if r["unit"] in by_bank else None,
                 "status":by_bank[r["unit"]][1]["status"] if r["unit"] in by_bank else "missing"} for r in group]
        if state!="unresolved" and (phase["status"]!="ok" or any(t["status"]!="ok" for t in timing)):
            detail+=" 合同履约或实付时点另有待核事项。"
            if status=="ok":
                status="risk" if any(t["status"] in ("risk","issue") for t in timing) else "missing"
        refs=[v["ref"] for v in base.values() if v]
        relevant=records if reasons else group
        refs.extend(v["ref"] for r in relevant for v in r["inputs"].values() if v)
        refs.extend(f"{p['doc']}/p{p['page']}" for p in ledger["pages"])
        if phase:
            refs.extend(phase["evidence"])
        refs.extend(e for f in related for e in f["evidence"])
        entry=result("H06",status,detail,refs,[u["id"] for u in graph.get("audit_documents",graph["documents"])],stage)
        entry["stage_payments"]={"state":state,"base":base,"expected":fmt(expected),"seen":fmt(paid),"difference":fmt(delta),
                                 "records":group,"reasons":issue,"timing":timing,"condition":phase["status"] if phase else None}
        output.append(entry)
    return output


def edges(findings):
    return [{"from":f["stage"]["clause_ref"],"to":r["inputs"]["transfer_amount"]["ref"],"type":"stage_transfer_operand",
             "evidence":[f["stage"]["clause_ref"],item["base"]["total"]["ref"],r["inputs"]["transfer_ref"]["ref"],r["inputs"]["transfer_amount"]["ref"]]}
            for f in findings if (item:=f.get("stage_payments")) and item["seen"] is not None for r in item["records"] if not r["duplicate_of"]]


def verify(report,read_text,*,signing=False):
    graph,policy=report["graph"],report["policy"]
    if not policy.get("stage_payments"):
        if policy.get("version","")>=SINCE or "stage_payment_sources" in graph or "stage_payments.py" in policy.get("code_sha256",{}):
            raise ValueError("缺少分期多笔回单程序")
        if signing and any(f["rule"]=="H05" and f["status"]=="ok" for f in report["findings"]) and sources(graph,read_text)["banks"]:
            raise ValueError("旧版底稿有多份付款回单，请按现行程序重审相应期款后签收。")
        return
    if (policy["stage_payments"]!=FORMAT or policy.get("version","")<SINCE or graph.get("stage_payment_sources")!=sources(graph,read_text)
            or [e for e in graph["edges"] if e["type"]=="stage_transfer_operand"]!=edges(report["findings"])):
        raise ValueError("期款所据原页、附注、金额或流水关系与底稿不符")
