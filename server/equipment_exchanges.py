"""Reconcile returned and received equipment on a signed exchange receipt with both inspections."""

import re
from collections import defaultdict

from reinspection import LINK_KEYS

TITLE = "equipment_exchange"
TITLES = ("设备换货交接单", "换货交接单", "设备退换交接单")
LABELS = {
    "exchange_number": ("交接单编号", "换货交接单号", "所据换货交接单号", "所据换货交接单编号"),
    "exchange_old_model": ("退回型号", "退回设备型号", "换出设备型号"),
    "exchange_new_model": ("换入型号", "换入设备型号"),
    "exchange_old_serials": ("退回设备编号", "退回设备序列号", "换出设备编号"),
    "exchange_new_serials": ("换入设备编号", "换入设备序列号"),
    "exchange_on": ("交接日期", "换货交接日期"),
    "exchange_status": ("交接状态", "换货交接结果"),
}
PRINTED = {label: key for key, labels in {
    **LABELS, "contract_id": ("合同编号","合同号"), "buyer": ("采购方","甲方","买方"), "seller": ("供应方","乙方","卖方"),
    "subject": ("采购标的","合同标的","标的"), "buyer_signature": ("甲方签章","甲方盖章"),
    "seller_signature": ("乙方签章","乙方盖章"), "original_acceptance": ("原验收单编号","原验收报告编号"),
    "acceptance_number": ("验收单编号","验收报告编号","复验单编号","复验报告编号"),
    "delivered_serials": ("验收设备编号","实收设备编号","验收序列号"),
    "quantity_accepted": ("实际验收数量","验收数量"), "quantity_agreed": ("约定交付数量","合同交付数量"),
}.items() for label in labels}
FORM_FIELDS = {*LABELS, *LINK_KEYS, "buyer_signature", "seller_signature", "original_acceptance"}
INSPECTION_FIELDS = {"exchange_number","delivered_serials","acceptance_number","quantity_accepted"}
CONTRACT_TERMS = re.compile(r"付款|价款|金额|结算|生效|补充协议|合同变更|免责|保修|质保|保留所有权|另行约定|免验")
SERIAL_NOTE = re.compile(r"(?:编号|序列号|机身号).{0,10}(?:尾号|部分|节选|省略|遮盖|掩码)|(?:仅列|只列|仅展示).{0,16}(?:编号|尾号|序列号)|(?:交接|退换|换货)(?:附注|说明|保留意见)")
WATERMARK = "合成演练资料仅供系统测试无交易效力"


def row_kind(quote):
    label, sep, value = quote.replace("：", ":", 1).partition(":")
    if not sep and label.strip() in TITLES:
        return "title", label.strip()
    return PRINTED.get(label.strip()), value.strip()


def sources(pages):
    """Retain physical rows, including unrecognised qualifications, before drawing links."""
    forms = set()
    referenced = False
    for place, raw, facts, _ in pages:
        quotes = raw.splitlines() if raw is not None else [f["quote"] for f in facts]
        if place["role"] == TITLE or any(q.strip() in TITLES for q in quotes):
            forms.add(place["unit"])
        if place["role"] in ("acceptance","reinspection") and any(row_kind(q)[0]=="exchange_number" for q in quotes):
            referenced = True
    if not forms and not referenced:
        return None
    evidence = []
    for place,raw,facts,anchors in pages:
        role = place["role"]
        is_form = place["unit"] in forms
        if not is_form and role not in ("contract","acceptance","reinspection"):
            continue
        rows = []
        if raw is None:
            items = [(None,f["quote"],[f["id"]]) for f in facts]
        else:
            items = [(n,q,anchors.get((n,q),[])) for n,q in enumerate(raw.splitlines(),1)]
        by_id = {f["id"]:f for f in facts}
        disputed_fields = {f["field"] for f in facts if f["status"]=="disputed"}
        for n,quote,refs in items:
            kind, value = row_kind(quote)
            if not quote.strip() or "".join(quote.split()) == WATERMARK:
                continue
            if is_form:
                if kind not in FORM_FIELDS | {"title"} or CONTRACT_TERMS.search(quote):
                    kind = "qualification"
            elif SERIAL_NOTE.search(quote):
                kind = "serial_note"
            elif not (role == "contract" and kind=="quantity_agreed") and not (role!="contract" and kind in INSPECTION_FIELDS):
                continue
            rows.append({**{key:place[key] for key in ("unit","doc","page")}, "kind":kind, "line":n, "quote":quote,
                         "value":value, "facts":refs, "disputed":kind in disputed_fields or any(by_id[ref]["status"]=="disputed" for ref in refs)})
        if is_form or rows:
            evidence.append({**place, "form":is_form, "rows":rows})
    return {"forms":sorted(forms), "pages":evidence}


def unscoped(ledger):
    forms = ledger.get("forms", [])
    return {unit for unit in forms if not clear_form([p for p in ledger["pages"] if p["unit"]==unit])}


def clear_form(pages):
    if len(pages)!=1:
        return False
    page=pages[0]
    return (page["role"]==TITLE and page["native"] and page["text_only"] and not page["incomplete"]
            and sum(r["kind"]=="title" for r in page["rows"])==1 and all(r["kind"]!="qualification" for r in page["rows"]))


def reconcile(graph, contract, inspections, comparison, chain):
    from delivery_batches import quantity, serials
    from delegation import complete_id
    from performance import Material, day
    from warranty_terms import identity

    ledger = graph["equipment_model_sources"].get("exchange")
    if not ledger:
        return
    pages, forms = ledger["pages"],ledger["forms"]
    by_unit=defaultdict(list)
    for p in pages:
        by_unit[p["unit"]].extend(p["rows"])
    form=forms[0] if len(forms)==1 else None
    form_doc = Material(graph,form) if form else None
    steps=(chain or {}).get("steps",[])
    def unique_step(role):
        units=[s["unit"] for s in steps if s["role"]==role]
        return units[0] if len(units)==1 else None
    first,final=unique_step("original"),unique_step("final")
    records={doc.unit:doc for doc in inspections}
    checks=[]

    def rows(unit,*fields):
        return [r for r in by_unit[unit] if r["kind"] in fields]
    def value(unit,field):
        found=rows(unit,field)
        return found[0]["value"] if len(found)==1 and found[0]["line"] and not found[0]["disputed"] else ""
    def refs(*lines):
        return list(dict.fromkeys(ref for r in lines for ref in (f"{r['doc']}/p{r['page']}",*r["facts"])))
    def check(key, label, status, detail, links):
        checks.append({"key":key,"label":label,"status":status,"detail":detail,"evidence":list(dict.fromkeys(links))})
    def codes(unit,field):
        # Separators may vary between lists. The printed case, zeros and punctuation of each device ID are significant.
        ids=serials(value(unit,field).replace("，",","))
        if (not ids or len({serial_key(s) for s in ids})!=len(ids)
                or any(not re.search("[0-9]",s) or re.search(r"X{2,}",s,re.I) for s in ids)):
            return []
        return ids

    form_pages=[p for p in pages if p["form"]]
    scoped=len(forms)==1 and clear_form(form_pages)
    check("scope","交接原件范围","ok" if scoped else "missing",
          "有一份可逐行核对的实物交接单。" if scoped else "需确定唯一交接原件并核对影像、其他约定或未归属的页。",
          [f"{p['doc']}/p{p['page']}" for p in form_pages]+refs(*(r for p in form_pages for r in p["rows"] if r["kind"]=="qualification")))
    associated=bool(form_doc and all(value(form,k) for k in LINK_KEYS) and identity(contract,form_doc))
    check("identity","合同、双方与标的","ok" if associated else "missing",
          "交接单的合同号、双方及标的与采购合同原行一致。" if associated else "须核对交接单所列合同号、双方主体和标的。",
          [*contract.evidence(*LINK_KEYS),*refs(*rows(form,*LINK_KEYS))])
    number,final_ref=value(form,"exchange_number"),value(final,"exchange_number")
    original,old_ref=value(first,"acceptance_number"),value(form,"original_acceptance")
    linked=all(complete_id(s) and re.search("[0-9]",s) and re.fullmatch(r"[A-Za-z0-9._-]+",s) for s in (number,original)) and number==final_ref and original==old_ref
    check("references","原验收与复验所据单号","ok" if linked else "missing",
          f"交接单 {number} 引用原验收 {original}，最终复验引用该交接单。" if linked else "交接单须能对应原验收，最终复验所引交接单号也须一致。",
          refs(*rows(form,"exchange_number","original_acceptance"),*rows(first,"acceptance_number"),*rows(final,"exchange_number")))
    models={r["unit"]:r for r in comparison["records"]}
    def received(unit):
        return (models.get(unit,{}).get("received") or {}).get("value")
    old,new=value(form,"exchange_old_model"),value(form,"exchange_new_model")
    match=bool(old and new and old==received(first) and new==received(final) and models.get(final,{}).get("comparison")=="match"
               and models.get(first,{}).get("comparison") in ("different","match"))
    check("models","退回和换入型号","ok" if match else "risk",
          f"退回型号 {old} 与初验一致，换入型号 {new} 与合同、复验一致。" if match else "请逐行核对退回与换入型号、合同约定和两次实收型号。",
          [*refs(*rows(form,"exchange_old_model","exchange_new_model")),*(ref for unit in (first,final) for ref in models.get(unit,{}).get("evidence",[]))])
    expected=quantity(value(contract.unit,"quantity_agreed"))
    outgoing,incoming=codes(form,"exchange_old_serials"),codes(form,"exchange_new_serials")
    for key,label,unit,field,handed in (("returned","初验与退回设备",first,"exchange_old_serials",outgoing),
                                        ("received","换入与复验设备",final,"exchange_new_serials",incoming)):
        inspected=codes(unit,"delivered_serials")
        quantity_ok=bool(expected[0] and expected==quantity(value(unit,"quantity_accepted")) and expected[0]==len(inspected)==len(handed))
        clear=not any(r["kind"]=="serial_note" for r in by_unit[unit]) and all(
            p["native"] and p["text_only"] and not p["incomplete"] for p in pages if p["unit"]==unit)
        status="missing"
        if inspected and handed and clear:
            status="ok" if set(inspected)==set(handed) and quantity_ok else "risk"
        detail="需取得两份完整可辨的设备编号清单和数量。"
        if status=="ok":
            detail=f"两份清单所列 {len(handed)} {expected[1]}设备的编号逐一相符。"
        elif status=="risk":
            inspection_name="初验" if key=="returned" else "复验"
            differences=[]
            for name,only in ((inspection_name,sorted(set(inspected)-set(handed))),("交接单",sorted(set(handed)-set(inspected)))):
                if only:
                    differences.append(f"仅{name}列有 "+"、".join(only))
            if not quantity_ok:
                differences.append("清单覆盖数量与约定或所验数量未能对应")
            detail="。".join(differences)+"。"
        check(key,label,status,detail,refs(*rows(form,field),*rows(unit,"delivered_serials","quantity_accepted","serial_note"),*rows(contract.unit,"quantity_agreed")))
    distinct=bool(outgoing and incoming and {serial_key(s) for s in outgoing}.isdisjoint(serial_key(s) for s in incoming))
    completed=value(form,"exchange_status") in ("旧机已退回，新机已交付","旧机已退回,新机已交付","原设备已退回，新设备已交付")
    check("delivery","实际退回与交付","ok" if completed and distinct else "missing",
          "单据记载退回和交付均已完成，两组设备编号互不重复。" if completed and distinct else "需核对实际完成的退回和交付，以及新旧两组独立设备编号。",
          refs(*rows(form,"exchange_status","exchange_old_serials","exchange_new_serials")))
    swap_day=day(value(form,"exchange_on"))
    opened,closed=(records[u].date("accepted_on") if u in records else None for u in (first,final))
    ordered=bool(swap_day and opened and closed and opened<swap_day<closed)
    dates=f"初验 {opened or '日期待核'}、交接 {swap_day or '日期待核'}、复验 {closed or '日期待核'}。"
    check("date","交接与复验时点","ok" if ordered else "risk",
          dates if ordered else dates+"须取得交接在两次验收之间的依据，同日记录需核对先后时点。",
          [*refs(*rows(form,"exchange_on")),*(ref for u in (first,final) if u in records for ref in records[u].evidence("accepted_on"))])
    missing_signatures=[]
    for party,field,name in (("buyer","buyer_signature","采购方"),("seller","seller_signature","供应方")):
        confirmed=bool(form_doc and value(form,field) and form_doc.signed(field,contract.body(party)) and any(
            f["status"]=="confirmed" and f["id"] in rows(form,field)[0]["facts"] for f in form_doc.fields[field]))
        if not confirmed:
            missing_signatures.append(name)
    check("signatures","交接双方签认","missing" if missing_signatures else "ok",
          "须核对"+"、".join(missing_signatures)+"的交接签章原行及所代表主体。" if missing_signatures else "交接单双方签章原行均经核图，名称与合同主体对应。",
          refs(*rows(form,"buyer_signature","seller_signature")))
    sequence=comparison.get("sequence",{})
    linked_chain=sequence.get("record_chain_state")=="closed" and sequence.get("outcome") in ("replacement_unverified","same_model")
    check("reinspection","整改及最终复验","ok" if linked_chain else "missing",
          "原验收、整改、最终复验及合格记录已对应。" if linked_chain else "需核清原验收、整改和最终接受设备的复验结论。",
          [ref for s in steps for ref in s["evidence"]])
    outstanding=[item for item in checks if item["status"]!="ok"]
    verified=not outstanding
    detail=(f"交接单 {number} 记载 {expected[0]} {expected[1]} {old} 已退回、{expected[0]} {expected[1]} {new} 已交付，"
            "两组设备编号分别与初验和最终复验原件对应。" if verified else "退换交接待核。"+" ".join(i["detail"] for i in outstanding))
    exchange={"status":"ok" if verified else "risk","detail":detail,"checks":checks,"evidence":list(dict.fromkeys(
        [ref for x in checks for ref in x["evidence"]]+[f"{p['doc']}/p{p['page']}" for p in pages]))}
    if scoped and associated and linked:
        # These describe cited documents. Each edge carries its own serial-list comparison.
        exchange["path"]=[{"unit":u,"page":next(f"{p['doc']}/p{p['page']}" for p in pages if p["unit"]==u and any(
            r["kind"]==field for r in p["rows"]))} for u,field in ((first,"acceptance_number"),(form,"exchange_number"),(final,"exchange_number"))]
    comparison["exchange"]=exchange
    comparison["evidence"]=list(dict.fromkeys([*comparison["evidence"],*exchange["evidence"]]))
    if verified:
        sequence["outcome"]="replacement_verified"
        comparison.update(status="ok",detail=detail)
    else:
        if comparison["status"]!="issue":
            comparison["status"]="risk"
        comparison["detail"]=comparison["detail"]+" "+detail


def serial_key(value):
    # Use a loose spelling only to hold ambiguous identifiers. Positive matches use the literal codes.
    return re.sub(r"[-._]","",value).casefold()


def edges(comparison):
    exchange=comparison.get("exchange",{})
    path=exchange.get("path")
    if not path:
        return []
    checks={r["key"]:r for r in exchange["checks"]}
    return [{"type":"equipment_exchange_"+key,"from":a["page"],"to":b["page"],"status":checks[key]["status"],
             "evidence":list(dict.fromkeys([a["page"],b["page"],*checks["identity"]["evidence"],*checks["references"]["evidence"],*checks[key]["evidence"]]))}
            for key,a,b in (("returned",path[0],path[1]),("received",path[1],path[2]))]
