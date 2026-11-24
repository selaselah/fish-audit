"""Derive a gross installment total exclusively from signed, comparable receipt observations."""

import hashlib
import json
import re
from datetime import date
from decimal import Decimal

from calculations import in_yuan, money, normalized
from payment_notes import pending_notes


LIMIT = 32
RULE = ("同合同分期付款累计", "按合同号与收付双方检索本企业已通过的付款底稿，对同一合同原件的人民币元成功回单按完整流水去重，与合同总额比较。")
HINT = re.compile(r"分期|分[两二三四五六七八九十\d]+期|每期|分批付款")
SIMPLE_TERM = re.compile(r"(?:分期|分[两二三四五六七八九十\d]+期)(?:付款|支付|结算)(?:[,，、]?每期\d+(?:\.\d+)?%)?[。.]?")
TERM_LABEL = re.compile(r"^(?:结算条款|付款条款|付款方式|结算方式|支付条件|付款条件|结算条件):")
ADJUSTMENT = re.compile(r"退款|退回款|冲正|退汇|撤销|红冲|冲销|抵扣|扣减|补充协议|变更|质保|保留款|暂估|上限|框架|以实际|据实|折让")
IDENTITY = {"buyer", "seller", "contract_id", "payer", "payee"}
RELEVANT = IDENTITY | {"contract","bank_receipt","contract_account","payee_account","payment_term","transfer_status",
                       "transfer_ref","paid_on","signed_on","total","transfer_amount","currency","unit","adjustment"}


def iso_day(value):
    match = re.fullmatch(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?",normalized(value))
    try:
        return date(*map(int,match.groups())).isoformat() if match else None
    except ValueError:
        return None


def installment_record(graph, findings, payer, reference):
    """Retain a search key even for a prior signed case whose amount cannot be counted."""
    facts = graph["facts"]
    requested = any(f["field"]=="payment_term" and HINT.search(normalized(f["quote"])) for f in facts)
    requested = requested or any(HINT.search(normalized(row.get("quote",""))) for row in graph.get("cautions",[]))
    result = {"requested":bool(requested),"key":None,"entry":None,"refs":[f["id"] for f in facts if f["field"] in RELEVANT]}
    kinds = graph["documents_by_kind"]
    contracts, banks = kinds.get("contract",[]),kinds.get("bank_receipt",[])
    if len(contracts)!=1 or len(banks)!=1:
        return result
    contract, bank = contracts[0],banks[0]
    checked = {}
    for fact in facts:
        if fact["status"] in {"anchored","confirmed"}:
            key = (fact.get("unit",fact["doc"]),fact["field"])
            checked.setdefault(key,{})[normalized(fact["value"])] = fact

    def one(doc,field):
        values = checked.get((doc,field),{})
        return next(iter(values.values())) if len(values)==1 else None

    statuses = {}
    for finding in findings:
        statuses.setdefault(finding["rule"],set()).add(finding["status"])
    if statuses.get("B01")!={"ok"} or statuses.get("B02")!={"ok"}:
        return result
    identity = [one(contract,field) for field in ("contract_id","buyer","seller")]
    if not all(identity) or any(f["status"] not in {"anchored","confirmed"} for f in facts if f["field"] in IDENTITY):
        return result
    keys = [normalized(f["value"]) for f in identity]
    if any(v in {"未知","无","不详","略","待核","见附件"} or re.search(r"[*＊…•●×]|[xX]{3,}",v) for v in keys):
        return result
    result["key"] = hashlib.sha256(json.dumps(keys,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
    if not requested or not payer or not reference or any(statuses.get(k)!={"ok"} for k in ("E01","B03","B05")):
        return result
    term = one(contract,"payment_term")
    if not term:
        return result
    printed = TERM_LABEL.sub("",normalized(term["quote"])).rstrip("。.")
    value = TERM_LABEL.sub("",normalized(term["value"])).rstrip("。.")
    if value != printed or not SIMPLE_TERM.fullmatch(printed):
        return result
    if (any(f["field"]=="adjustment" or ADJUSTMENT.search(f["quote"]) for f in facts) or
            any(ADJUSTMENT.search(c["quote"]) or normalized(c["quote"]) != normalized(term["quote"]) for c in graph.get("cautions",[]))):
        return result
    total,paid,account,paid_on = one(contract,"total"),one(bank,"transfer_amount"),one(bank,"payee_account"),one(bank,"paid_on")
    if not all((total,paid,account,paid_on)):
        return result
    for doc in (contract,bank):
        currency,unit = one(doc,"currency"),one(doc,"unit")
        if not currency or not unit or not in_yuan(currency) or normalized(unit["value"]) not in {"元","人民币元"}:
            return result
    ceiling,amount = money(total),money(paid)
    day = iso_day(paid_on["value"])
    if not day or amount is None or ceiling is None or min(amount,ceiling)<=0:
        return result
    result["entry"] = {"contract_sha256":total["source_sha256"],"contract_total":format(ceiling,".2f"),
                       "account":normalized(account["value"]),"paid_on":day,"reference":reference,"amount":format(amount,".2f"),
                       "amount_fact":paid["id"],"contract_fact":total["id"]}
    return result


def calculate(current, history):
    if current.get("reference_note_pending"):
        return {"state":"missing","reason":"本案流水展示说明尚待核图，请先核实完整流水号再复算分期付款。"}
    if current.get("partial_reference"):
        return {"state":"missing","reason":"本案回单流水号有遮盖或只列尾号，请取得完整流水后复算分期付款。"}
    if not current["entry"]:
        return {"state":"missing","reason":"请核对合同分期条款、原件、固定总额、收款账户、成功流水及人民币元金额。"}
    if history["count"] != len(history["matches"]):
        return {"state":"incomplete","reason":f"共有 {history['count']} 份历史底稿，超过本程序逐份核验上限 {LIMIT} 份。"}
    first = current["entry"]
    payments = {}
    rows = [(first,"")]
    for match in history["matches"]:
        item = match["entry"]
        if pending_notes(match.get("incomplete_references",[])):
            return {"state":"missing","reason":f"历史底稿「{match['title']}」的流水展示说明尚待核图，请核实后再复算。"}
        if match.get("incomplete_references"):
            return {"state":"missing","reason":f"历史底稿「{match['title']}」的回单流水号有遮盖或只列尾号，请核对完整流水后复算。"}
        if not item or any(item[k]!=first[k] for k in ("contract_sha256","contract_total","account")):
            return {"state":"conflict","reason":f"历史底稿「{match['title']}」的合同原件、金额口径或回单依据与本次无法比对。"}
        rows.append((item,f"prior/{match['case_id']}/r{match['rev']}/"))
    for entry,prefix in rows:
        ref = entry["reference"]
        amount,day = entry["amount"],entry["paid_on"]
        prior = payments.get(ref)
        if prior and (prior["amount"],prior["paid_on"]) != (amount,day):
            return {"state":"conflict","reason":f"相同流水「{ref}」的付款金额或日期不一致，请查对原回单。"}
        if prior:
            prior["copies"].append(prefix+entry["amount_fact"])
        else:
            payments[ref] = {"reference":ref,"paid_on":day,"amount":amount,"amount_fact":prefix+entry["amount_fact"],"copies":[]}
    paid = sum(Decimal(p["amount"]) for p in payments.values())
    return {"state":"calculated","payments":sorted(payments.values(),key=lambda p:(p["paid_on"],p["reference"])),
            "contract_fact":first["contract_fact"],"contract_total":first["contract_total"],"paid_total":format(paid,".2f"),
            "difference":format(paid-Decimal(first["contract_total"]),".2f")}


def finding(current, history, as_of):
    calculation = calculate(current,history)
    refs = list(current["refs"])
    for match in history["matches"]:
        refs.extend(f["id"] for f in match["evidence"])
    if calculation["state"] != "calculated":
        return "missing",calculation["reason"],refs
    delta = Decimal(calculation["difference"])
    result = (f"已见 {len(calculation['payments'])} 笔不同流水，回单累计 {calculation['paid_total']} 元，"
              f"合同总额 {calculation['contract_total']} 元。")
    if delta>0:
        result += f"回单累计超出合同总额 {delta:.2f} 元，请核查银行对账单、退款和合同变更。"
    else:
        result += "所见回单累计未超合同总额，各期应付条件仍须核实。"
    return "risk" if delta>0 else "ok",result+" 核查时点 "+as_of,refs
