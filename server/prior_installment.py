"""Test an express prior-payment condition against original bank records and the date of the dependent payment."""

import hashlib
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal

import stage_payments
from payment_releases import submission_day


FORMAT = "prior-installment-bank-evidence-v1"
SINCE = "2026.11.26.05"
FIELD = "prior_installment_clause"
LABELS = {FIELD: ("验收款放款条件", "前款凭证约定", "验收款前款条件")}
PRIOR = r"(?:首期预付款|首期款|首款|首付款|预付款|前一期款|上期款|前款|第一期款?)"
SIGNAL = re.compile(PRIOR + r".{0,20}(?:付足|付清|足额|已付|到账|收讫)|(?:足额支付|付清|付足).{0,10}" + PRIOR)
CONDITION = re.compile(r"验收款(?:放款条件|支付前提|付款前提|前款条件)[:：](?:首款|首期预付款|首付款)须(?:已付足|已付清|足额支付)[，,]以(?:付款银行成功回单为据|银行成功付款回单为准)[。]?")
ACCEPTANCE = re.compile(r"^(?:最终验收合格|终验合格|验收合格)后(?:支付|付)")
FIRST = re.compile(r"^合同生效后(?:支付|付)")
SEVERITY = {"ok": 0, "missing": 1, "risk": 2, "issue": 3}


def sources(graph, read_text):
    kinds = graph["documents_by_kind"]
    roles = {unit: kind for kind in ("contract", "contract_addendum") for unit in kinds.get(kind, ())}
    sections = {(d["source"], d["page"]): d["id"] for d in graph.get("audit_documents", ()) if "source" in d}
    facts = defaultdict(list)
    for f in graph["facts"]:
        facts[f["doc"], f["page"]].append(f)
    lines, pages = [], []
    for node in graph["nodes"]:
        if node["type"] != "page":
            continue
        doc, suffix = node["id"].rsplit("/p", 1)
        page = int(suffix)
        unit = sections.get((doc, page), doc)
        if unit not in roles:
            continue
        where = {"doc": doc, "page": page, "unit": unit, "role": roles[unit]}
        native = node.get("layer") == "text"
        pages.append({**where, "text_only": native and node.get("clause_text_only") is True})
        raw = read_text(doc, page) if native else ""
        if native and (not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=node.get("text_sha256")):
            raise ValueError("前款约定所据原页与归档文字不符")
        physical = raw.splitlines()
        located = defaultdict(list)
        def observe(quote, number, observations):
            ids = [f["id"] for f in observations]
            label = re.split("[:：]",quote,maxsplit=1)[0].strip()
            dedicated = label in ("前款凭证约定", "验收款前款条件") or any(f["field"] == FIELD for f in observations)
            if not SIGNAL.search(quote) and not dedicated:
                return
            ref = f"{doc}/p{page}/l{number}" if number else ids[0]
            # '验收款' identifies the dependent installment only when the heading itself says so.
            target = "acceptance" if label.startswith("验收款") else label if re.fullmatch(r"第[一二三四五六七八九十0-9]+期", label) else None
            lines.append({**where,"id":"prior-term/"+ref,"line":number,"quote":quote,"facts":ids,"target":target,
                          "supported":bool(number and roles[unit]=="contract" and CONDITION.fullmatch(quote.strip())
                                           and not any(f["status"]=="disputed" for f in observations))})
        for f in facts[doc,page]:
            location = f.get("source_line") or {}
            n = location.get("number")
            if (native and n and 0<n<=len(physical) and location.get("rects") and location.get("text")==physical[n-1]):
                located[n].append(f)
                if stage_payments.literal(f["quote"])==stage_payments.literal(physical[n-1]):
                    continue
            if f["quote"] not in physical or f["status"]=="disputed":
                observe(f["quote"],None,[f])
        for n, quote in enumerate(physical,1):
            observe(quote,n,located[n])
    return {"format":FORMAT,"lines":lines,"pages":pages if lines else []}


def source_graph(ledger):
    nodes, edges = [], []
    for r in ledger["lines"]:
        page = f"{r['doc']}/p{r['page']}"
        nodes.append({"id":r["id"],"type":"prior_installment_term","label":r["quote"],
                      "doc":r["doc"],"page":r["page"],"line":r["line"]})
        edges.append({"from":page,"to":r["id"],"type":"prior_installment_source","evidence":[page,*r["facts"]]})
    return nodes,edges


def unique(items):
    return list(dict.fromkeys(items))


def condition(graph, findings, grouped):
    from performance import Material
    ledger = graph["prior_installment_sources"]
    terms = ledger["lines"]
    if not terms:
        return
    phases = [f for f in findings if f["rule"]=="H04" and f.get("stage")]
    targets = [f for f in phases if ACCEPTANCE.match(f["stage"]["clause"]) or "验收" in f["stage"]["clause"] or "验收款" in f["stage"]["name"]]
    certain_target = all(r["target"]=="acceptance" for r in terms) and len(targets)==1
    if not certain_target:
        named = {r["target"] for r in terms}
        scoped = [f for f in phases if ("acceptance" in named and f in targets) or
                  any(stage_payments.same_stage(f["stage"]["name"], t) for t in named if t and t != "acceptance")]
        targets = phases if None in named or not scoped else scoped
    if not targets:
        return
    first = [f for f in phases if stage_payments.same_stage(f["stage"]["name"],"第一期") and FIRST.match(f["stage"]["clause"])]
    donor = first[0]["stage"] if len(first)==1 else {}
    by_stage = {f["stage"]["clause_ref"]: f for f in grouped if f.get("stage")}
    banks = {r["unit"]:r for f in grouped for r in f["stage_payments"]["records"]}
    kinds = graph["documents_by_kind"]
    contracts = kinds.get("contract",[])
    contract = Material(graph,contracts[0]) if len(contracts)==1 else None
    base = {k:stage_payments.printed(contract,k) if contract else None for k in ("total","currency","unit")}
    facts = {f["id"]:f for f in graph["facts"]}
    expected, _ = stage_payments.expected_amount(donor, facts, contracts, stage_payments.amount(base,"total"))
    source = by_stage.get(donor.get("clause_ref"))
    entry = source["stage_payments"] if source else None
    page_refs = [f"{p['doc']}/p{p['page']}" for p in ledger["pages"]]
    totals_refs = [v["ref"] for v in base.values() if v]
    evidence = unique([*page_refs,*(ref for r in terms for ref in [r["id"],*r["facts"]]),*totals_refs,
                       *([donor["clause_ref"]] if donor else []),*(source["evidence"] if source else [])])
    payments = [f for f in findings if f["rule"]=="H05"]
    # Include the ledger's actual bank pages and designations also when none is assigned to the first installment.
    for r in banks.values():
        evidence.extend(v["ref"] for v in r["inputs"].values() if v)
    bank_pages=graph["stage_payment_sources"]["pages"]
    evidence.extend(f"{p['doc']}/p{p['page']}" for p in bank_pages)
    scope = unique([*(p["unit"] for p in ledger["pages"]),*(p["unit"] for p in bank_pages)])
    cutoff = graph.get("prior_installment_as_of")
    clean = (certain_target and len(terms)==1 and terms[0]["supported"] and contract and terms[0]["unit"]==contract.unit
             and not kinds.get("contract_addendum") and all(p["text_only"] for p in ledger["pages"])
             and donor and donor["clause_ref"]!=targets[0]["stage"]["clause_ref"] and expected is not None)
    timing = {t["unit"]:t["status"] for t in entry["timing"]} if entry else {}
    receipts = []
    if entry:
        for r in entry["records"]:
            inputs=r["inputs"]
            receipts.append({"unit":r["unit"],"amount":r["amount"],"date":r["date"],"duplicate_of":r["duplicate_of"],
                             "refs":{k:v["ref"] for k,v in inputs.items() if v},"timing":timing.get(r["unit"])})
    check = {"format":FORMAT,"terms":[r["id"] for r in terms],"scope":scope,"evidence":unique(evidence),
             "source_stage":donor.get("clause_ref"),"source_name":donor.get("name"),"share":donor.get("share"),
             "base":base,"expected":stage_payments.fmt(expected) if clean else None,"seen":None,
             "as_of":cutoff,"covered_on":None,"records":receipts,"payment_date":None,"payment_date_ref":None,
             "before":None,"on_day":None}
    state,status,detail="terms","missing","需核实前款约定所指期次、凭证类型和现行合同。"
    if clean:
        if not source:
            bank_ledger = graph["stage_payment_sources"]
            unknown = (any(not r["stage_ref"] or r["reasons"] for r in banks.values())
                       or bank_ledger["unknown_units"] or bank_ledger["notes"] or bank_ledger["ambiguous_units"]
                       or any(not p["text_only"] or p["partial"] or p["uncovered"] for p in bank_pages))
            state = "allocation" if unknown else "absent"
            detail = "有回单未明确归属期次，首款足额付款的凭证待核。" if unknown else "本案尚缺可唯一归入首期的足额成功付款回单。"
        elif any(not r["stage_ref"] for r in banks.values()):
            state,detail="allocation","有回单未明确归属期次，首款足额付款的凭证待核。"
        elif entry["state"]=="unresolved" or not cutoff or any(not r["date"] or r["date"]>=cutoff for r in receipts):
            state,detail="unverified","前款流水、归属、原件或截至提交日的支付时间待核。"
        elif entry["state"]=="over" or any(r["duplicate_of"] for r in receipts):
            state,status,detail="disputed","risk","首款出现超额或重复流水，须查明归属和调整情况。"
        elif entry["state"]=="partial":
            check["seen"]=entry["seen"]
            state,detail="partial","本次可对应的首款回单合计少于合同约定，需补核剩余款项。"
        elif entry["state"]=="balanced" and source["status"]=="ok" and all(r["timing"]=="ok" for r in receipts):
            check.update(seen=entry["seen"],covered_on=max(r["date"] for r in receipts))
            state,status,detail="met","ok","至所列日期，首期已具备合同要求的足额成功付款回单。"
        else:
            state,detail="unverified","所见首款合计仍须结合合同生效、付款依据及各笔实际支付日期核查。"
    elif all(re.search("到账|收讫", r["quote"]) for r in terms):
        state,detail="credit","合同涉及收款方实际到账，需核实相应入账凭证或收讫确认。"
    check.update(state=state,status=status,detail=detail)
    for target in targets:
        target_ref=target["stage"]["clause_ref"]
        proof={**check,"target_stage":target_ref,"evidence":unique([*check["evidence"],target_ref])}
        attach(target,proof)
        for payment in payments:
            if payment.get("stage",{}).get("clause_ref")!=target_ref:
                continue
            title=next((facts.get(ref) for ref in payment["evidence"] if (facts.get(ref) or {}).get("field")=="bank_receipt"),None)
            bank=banks.get(title.get("unit",title["doc"])) if title else None
            actual={**proof}
            if bank and bank["stage_ref"]==target_ref and not bank["reasons"] and bank["date"] and cutoff and bank["date"]<cutoff:
                paid=bank["date"]
                actual.update(payment_date=paid,payment_date_ref=bank["inputs"]["paid_on"]["ref"])
                if state in ("met","partial"):
                    before=sum((Decimal(r["amount"]) for r in receipts if r["date"]<paid),Decimal(0))
                    same=sum((Decimal(r["amount"]) for r in receipts if r["date"]==paid),Decimal(0))
                    actual.update(before=stage_payments.fmt(before),on_day=stage_payments.fmt(same))
                    if state=="met" and paid<check["covered_on"]:
                        actual.update(state="early",status="risk",detail="验收款付款日早于本案回单所示的首款足额日，需复核当日依据。")
                    elif state=="met" and paid==check["covered_on"]:
                        actual.update(state="same_day",status="missing",detail="首款足额和验收款实付是同一天，需核对两笔银行记录的时分。")
            elif state=="met":
                actual.update(state="payment_unknown",status="missing",detail="验收款回单的日期、归属或成功状态仍需核实。")
            attach(payment,actual)


def attach(finding, proof):
    finding["prior_installment"]=proof
    finding["evidence"]=unique([*finding["evidence"],*proof["evidence"]])
    finding["scope"]=unique([*finding["scope"],*proof["scope"]])
    if finding["status"]=="ok" and proof["status"]!="ok":
        finding["detail"]=proof["detail"]
    else:
        finding["detail"]+=" "+proof["detail"]
    if SEVERITY[proof["status"]]>SEVERITY[finding["status"]]:
        finding["status"]=proof["status"]


def verify(report,read_text,*,submitted=None,signed=None,signing=False):
    graph,policy=report["graph"],report["policy"]
    marker=policy.get("prior_installment")
    nodes=[n for n in graph["nodes"] if n["type"]=="prior_installment_term"]
    edges=[e for e in graph["edges"] if e["type"]=="prior_installment_source"]
    claims=[f for f in report["findings"] if "prior_installment" in f]
    if marker is None:
        if (policy.get("version","")>=SINCE or "prior_installment.py" in policy.get("code_sha256",{}) or
                "prior_installment_sources" in graph or "prior_installment_as_of" in graph or nodes or edges or claims):
            raise ValueError("缺少前款付款凭证程序标记")
        if signing:
            positive=[f for f in report["findings"] if f["rule"] in ("H04","H05","H06") and f["status"]=="ok"]
            if positive:
                terms=sources(graph,read_text)["lines"]
                if terms and any(any(r["target"] is None for r in terms) or "验收" in (f.get("stage") or {}).get("clause","")
                                 or "验收" in (f.get("stage") or {}).get("name","") for f in positive):
                    raise ValueError("旧版付款结论尚未核对首款凭证约定，请按现行程序重审后签收。")
        return
    ledger=sources(graph,read_text)
    if marker!=FORMAT or policy.get("version","")<SINCE or ledger!=graph.get("prior_installment_sources") or (nodes,edges)!=source_graph(ledger):
        raise ValueError("首款约定的物理原页、原行或依据关系与归档不符")
    cutoff=graph.get("prior_installment_as_of")
    if ledger["lines"]:
        if (not isinstance(cutoff,str) or date.fromisoformat(cutoff).isoformat()!=cutoff or
                submitted and cutoff!=submission_day(submitted) or signed and cutoff>submission_day(signed)):
            raise ValueError("前款凭证的审查截止日与案件提交记录不符")
    elif cutoff is not None or claims:
        raise ValueError("缺少前款约定的来源")
