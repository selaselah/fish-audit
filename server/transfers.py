"""Compare one printed bank receipt with one contract for a single full settlement."""

import re

import payment_execution

from calculations import in_yuan, money, normalized
from payment_notes import note_refs, pending_notes
from payment_visibility import unchecked


RULES = {
    "B01": ("合同与银行回单", "取一份可归属的采购合同和一份银行付款回单，按单合同单笔全额付款核对。"),
    "B02": ("付款归属与主体", "合同号、采购方与付款户名、供应方与收款户名逐项核对；简称或不一致需人工查证。"),
    "B03": ("约定账户与收款账户", "对照合同明确约定的收款账号与回单的完整收款账号，保留前导零；账户差异需核对授权变更。"),
    "B04": ("回单与合同全额差额", "在单笔全额、收付双方及合同号相符、回单记载成功等条件下，以人民币元比较付款与合同总额。"),
    "B05": ("回单流水、状态与日期", "核对可辨认的交易流水号、回单所记状态及付款日期与签约日期的先后。"),
}


def check_transfers(graph, docs, values, record, parsed_date, verified_grants=()):
    kinds = graph["documents_by_kind"]
    contracts, receipts = kinds.get("contract",[]), kinds.get("bank_receipt",[])
    ids = [doc["id"] for doc in docs]
    titles = [f["id"] for f in graph["facts"] if f["field"] in ("contract","bank_receipt") and f["status"] in ("anchored","confirmed")]
    grants = set(verified_grants)
    core = set(contracts+receipts)
    complete = (len(contracts) == len(receipts) == 1 and len(core)==2 and not grants.intersection(core)
                and set(ids)==core|grants and all(not names or (kind=="power_of_attorney" and set(names)==grants)
                    for kind,names in kinds.items() if kind not in ("contract","bank_receipt")))
    detail = f"核得合同 {len(contracts)} 份、银行回单 {len(receipts)} 份，本案共 {len(ids)} 份单据。"
    if grants:
        detail += f"其中 {len(grants)} 份书面委托已在合同签署程序中核对。"
    record("B01","ok" if complete else "missing",detail,titles,ids)
    if not complete:
        for rule in ("B02","B03","B04","B05"):
            record(rule,"missing","请先建立单合同与单份银行回单的对应关系。",titles,ids)
        return
    contract, bank = contracts[0], receipts[0]
    matched = True
    basis = list(titles)
    for first,second,label in (("contract_id","contract_id","合同号"),("buyer","payer","采购方与付款户名"),
                               ("seller","payee","供应方与收款户名")):
        pair = values("B02",[(contract,first),(bank,second)])
        if not pair:
            matched = False
            continue
        refs = [f["id"] for f in pair]
        equal = normalized(pair[0]["value"]) == normalized(pair[1]["value"])
        matched = matched and equal
        basis.extend(refs)
        record("B02","ok" if equal else "risk",label+"分别记载为「"+pair[0]["value"]+"」及「"+pair[1]["value"]+"」。",refs)
    accounts = values("B03",[(contract,"contract_account"),(bank,"payee_account")])
    if accounts:
        a,b = (normalized(f["value"]) for f in accounts)
        refs = basis + [f["id"] for f in accounts]
        if not matched or not all(re.fullmatch(r"[0-9]{8,32}",v) for v in (a,b)):
            record("B03","missing","账户归属或完整账号待核，遮挡或缩写的账号无法用于全号比对。",refs)
        else:
            record("B03","ok" if a == b else "risk",f"合同约定账号尾号 {a[-4:]}，回单收款账号尾号 {b[-4:]}。"+
                   ("两个完整账号一致。" if a == b else "两个完整账号不同，请核验变更授权及对方确认记录。"),refs)
    proof = payment_execution.entry(graph, bank)
    if proof:
        cited = [*basis, *payment_execution.refs(graph, bank)]
        record("B05", "risk" if proof["state"] == "conflict" else "missing", payment_execution.DETAIL[proof["state"]], cited, [bank])
        record("B04", "missing", "本笔实际扣款凭证待核，暂缓比较实付金额与合同价款。", cited, ids)
        return
    partial = [m for m in graph.get("transfer_references",{}).get("facts",[]) if m["unit"]==bank]
    trace = None
    if partial:
        refs = list(dict.fromkeys([*(m["fact"] for m in partial),*note_refs(partial)]))
        basis.extend(refs)
        detail = ("回单同页有一条待核的流水展示说明，请对照页图核实该说明和流水栏。" if pending_notes(partial) else
                  "回单流水号有遮盖或只列尾号。请取得完整流水号，核对交易状态和付款日期。")
        if unchecked(partial):
            detail = "已核对流水栏的可见字符，请检查整张回单的页脚和备注并记录流水展示范围。"
        record("B05","missing",detail,refs,[bank])
    else:
        trace = values("B05",[(bank,"transfer_ref"),(bank,"transfer_status"),(contract,"signed_on"),(bank,"paid_on")])
    settled = False
    if trace:
        ref,status,signed,paid = trace
        signed_on,paid_on = parsed_date(signed),parsed_date(paid)
        state = normalized(status["value"])
        settled = (state in {"交易成功","付款成功","支付成功","已入账","已记账"}
                   and re.fullmatch(r"[A-Za-z0-9_-]{4,80}",normalized(ref["value"])) is not None
                   and signed_on is not None and paid_on is not None and paid_on >= signed_on)
        basis.extend(f["id"] for f in trace)
        record("B05","ok" if settled else "risk",f"回单记载「{status['value']}」，流水号「{ref['value']}」，"
               f"付款日期「{paid['value']}」，合同签约日期「{signed['value']}」。"+
               ("" if settled else "请向资金经办人员核对流水、状态与实际付款日期。"),[f["id"] for f in trace])
    fields = values("B04",[(contract,"total"),(bank,"transfer_amount"),(contract,"currency"),(bank,"currency"),
                           (contract,"unit"),(bank,"unit"),(contract,"payment_term")])
    if fields:
        total, paid = (money(f) for f in fields[:2])
        refs = basis+[f["id"] for f in fields]+[c["page_id"] for c in graph.get("cautions",[])]
        amended = [f["id"] for f in graph["facts"] if f["field"] == "adjustment"]
        refs.extend(amended)
        full = normalized(fields[6]["value"]).rstrip("。") in {"一次性全额结算","一次性全额付款","一次性付清","一次结清","一次性结清","一次付清"}
        if not (matched and settled and full and not amended and not graph.get("cautions") and
                all(in_yuan(f) for f in fields[2:4]) and all(normalized(f["value"]) in {"元","人民币元"} for f in fields[4:6])
                and total is not None and paid is not None and min(total,paid) >= 0):
            record("B04","missing","单笔全额条款、付款归属、回单状态或金额口径尚未齐备，暂缓计算差额。",refs,ids)
        else:
            delta = paid-total
            record("B04","issue" if delta else "ok",f"回单 {paid:,.2f} 元，合同 {total:,.2f} 元，付款与合同差额 {delta:,.2f} 元。",refs)
