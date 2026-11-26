"""Compare the acceptance number printed on a transfer with its contractual delivery batch."""

import hashlib
import re
from collections import defaultdict

from delegation import complete_id, covered_rows
from payment_reference import masked_value
from quality_references import incomplete_number


FORMAT = "payment-acceptance-reference-v1"
SINCE = "2026.11.26.20"
FIELD = "payment_acceptance_ref"
LABELS = {FIELD: ("付款依据验收单号", "付款依据验收单编号", "所据验收单号", "所据验收单编号",
                  "对应验收单号", "关联验收单号", "结算验收单号", "验收凭证编号")}
OWN_LABELS = {"验收单编号","验收报告编号","验收单号"}
HINT = re.compile(r"验收(?:证明|报告|凭证|单)(?:的)?(?:号|编号)|(?:依据|对应|所据|关联|凭|见).{0,10}验收(?:单|报告|凭证)")
CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}")
LEVEL = {"ok":0,"missing":1,"risk":2,"issue":3}
GRAPH_KEY = "payment_acceptance_sources"


def column(quote):
    pieces = re.split("[:：]",quote,maxsplit=1)
    return pieces[0].strip(), pieces[1].strip() if len(pieces)>1 else ""


def number(text):
    return bool(CODE.fullmatch(text) and re.search("[0-9]",text) and not incomplete_number(text))


def row_kind(role,quote,field=None):
    label,_ = column(quote)
    if role == "bank_receipt":
        if label in LABELS[FIELD]:
            return "citation"
        if field == FIELD or HINT.search(quote):
            return "note"
    elif label in OWN_LABELS:
        return "number"
    elif field == "acceptance_number":
        return "note"


def sources(graph,read_text):
    from stage_payments import BANK, BANK_TITLES, is_printed
    kinds = graph["documents_by_kind"]
    banks = set(kinds.get("bank_receipt",()))
    empty = {"format":FORMAT,"pages":[],"rows":[]}
    if not banks:
        return empty
    receipts = set(kinds.get("acceptance",())) | set(kinds.get("reinspection",()))
    participants = banks | receipts
    ambiguous = {u for u in participants if sum(u in group for group in kinds.values())>1}
    partial = {(g["doc"],g["page"]) for g in graph["gaps"] if g.get("quality") in ("partial","unreadable")}
    units = {(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    observed = defaultdict(list)
    for fact in graph["facts"]:
        observed[fact["doc"],fact["page"]].append(fact)
    pages,rows = [],[]
    for page in graph["nodes"]:
        if page["type"] != "page":
            continue
        doc,suffix = page["id"].rsplit("/p",1)
        n = int(suffix)
        unit = units.get((doc,n),doc)
        if unit not in participants:
            continue
        role = "bank_receipt" if unit in banks else "acceptance"
        place = {"doc":doc,"page":n,"unit":unit,"role":role}
        native = page.get("layer")=="text"
        pages.append({**place,"native":native,"text_only":page.get("clause_text_only") is True,
                      "ambiguous":unit in ambiguous or (doc,n) in partial})
        lines = []
        if native:
            text = read_text(doc,n)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=page.get("text_sha256"):
                raise ValueError("付款所据验收单的原页文字摘要不符")
            lines = text.splitlines()
            if role=="bank_receipt" and sum(line.strip() in BANK_TITLES for line in lines)!=1:
                pages[-1]["ambiguous"] = True
        located = defaultdict(list)
        for fact in observed[doc,n]:
            source = fact.get("source_line") or {}
            index = source.get("number")
            exact = (isinstance(index,int) and 0<index<=len(lines) and source.get("rects") and
                     source.get("text")==lines[index-1] and column(fact["quote"])==column(source["text"]))
            kind = row_kind(role,fact["quote"],fact["field"])
            if exact:
                located[index].append(fact)
            if kind and (not exact or not row_kind(role,lines[index-1])):
                rows.append({**place,"id":"payment-acceptance/"+fact["id"],"line":None,"kind":kind,"quote":fact["quote"],
                             "facts":[fact["id"]],"disputed":fact["status"]=="disputed"})
        previous = False
        for index,line in enumerate(lines,1):
            kind = row_kind(role,line)
            if previous and line.strip() and not re.search("[:：]",line):
                kind = "note"
            if line.strip():
                previous = kind in ("citation","number") or (previous and kind=="note")
            if kind:
                facts = located[index]
                rows.append({**place,"id":f"payment-acceptance/{doc}/p{n}/l{index}","line":index,"kind":kind,
                             "quote":line,"facts":[f["id"] for f in facts],"disputed":any(f["status"]=="disputed" for f in facts)})
    referenced = {r["unit"] for r in rows if r["role"]=="bank_receipt"}
    if graph.get("delivery_batch_sources",{}).get("signals"):
        referenced.update(p["unit"] for p in pages if p["role"]=="bank_receipt" and not (p["native"] and p["text_only"]))
    if not referenced:
        return empty
    locations = {(r["doc"],r["page"],r["line"]) for r in rows if r["line"]}
    by_page = {(p["doc"],p["page"]):p for p in pages}
    for page in covered_rows(graph,read_text,referenced,BANK,is_printed,"回单引用"):
        doc,n = page["doc"],page["page"]
        for line in page["uncovered"]:
            i = line["line"]
            if (doc,n,i) in locations:
                continue
            place = {key:by_page[doc,n][key] for key in ("doc","page","unit","role")}
            rows.append({**place,"id":f"payment-acceptance/{doc}/p{n}/l{i}","line":i,"kind":"note",
                         "quote":line["quote"],"facts":[],"disputed":False})
    return {"format":FORMAT,"pages":[p for p in pages if p["unit"] in referenced or p["role"]=="acceptance"],
            "rows":[r for r in rows if r["unit"] in referenced or r["role"]=="acceptance"]}


def source_graph(ledger):
    nodes,edges = [],[]
    for row in ledger["rows"]:
        page = f"{row['doc']}/p{row['page']}"
        nodes.append({"id":row["id"],"type":"payment_acceptance_line","label":row["quote"],
                      "doc":row["doc"],"page":row["page"],"line":row["line"]})
        edges.append({"type":"payment_acceptance_source","from":page,"to":row["id"],"evidence":[page,*row["facts"]]})
    return nodes,edges


def apply(graph,findings):
    ledger = graph.get(GRAPH_KEY,{})
    pages = ledger.get("pages",[])
    if not pages:
        return
    from delivery_batches import one
    from stage_payments import printed
    from performance import Material
    from reinspection import LINK_KEYS

    bank_units = {p["unit"] for p in pages if p["role"]=="bank_receipt"}
    contracts = graph["documents_by_kind"].get("contract",[])
    contract = Material(graph,contracts[0]) if len(contracts)==1 else None
    batch = next((f.get("batch_acceptance") for f in findings if f["rule"]=="H02"),None) or {}
    def bound(material,field):
        if not material:
            return None
        if field in ("payer","payee"):
            return material.fields[field][0] if printed(material,field) else None
        return one(material,field)
    def literal(material,field):
        fact = bound(material,field)
        return column(fact["source_line"]["text"])[1] if fact else None
    def originals(unit):
        return [r for r in ledger["rows"] if r["unit"]==unit]
    def clear(unit):
        owned = [p for p in pages if p["unit"]==unit]
        return bool(len(owned)==1 and all(p["native"] and p["text_only"] and not p["ambiguous"] for p in owned))
    contract_id = literal(contract,"contract_id")
    contract_refs = contract.evidence(*LINK_KEYS) if contract else []
    contract_identity = [literal(contract,k) for k in LINK_KEYS]
    known_contract = complete_id(contract_id) and all(
        v and not masked_value(v) and v not in {"同上","待核","未知","无","见附件","略","甲方","乙方","采购方","供应方"}
        for v in contract_identity)
    register = []
    for record in batch.get("records",[]):
        unit = record["unit"]
        doc = Material(graph,unit)
        rows = originals(unit)
        ref = rows[0] if len(rows)==1 and rows[0]["kind"]=="number" else None
        code = column(ref["quote"])[1] if ref else ""
        same = known_contract and all(literal(contract,k) and literal(contract,k)==literal(doc,k) for k in LINK_KEYS)
        identifiable = bool(same and clear(unit) and ref and ref["line"] and not ref["disputed"] and number(code)
                            and literal(doc,"acceptance_number")==code and record.get("scope_ref") and not record["scope_unclear"])
        register.append({"unit":unit,"batch":record["index"],"number_row":ref["id"] if ref else None,"number":code or None,
                         "scope_ref":record["scope_ref"],"identity_refs":doc.evidence(*LINK_KEYS),"identified":identifiable})
    for payment in findings:
        if payment["rule"]!="H05":
            continue
        units = bank_units.intersection(payment["scope"])
        if len(units)!=1:
            continue
        unit = next(iter(units))
        bank = Material(graph,unit)
        selected = originals(unit)
        stage = payment.get("stage",{})
        index = stage.get("batch_index")
        allocations = [b for b in batch.get("batches",[]) if b["index"]==index]
        own = [r for r in register if r["batch"]==index] if index else []
        raw = column(selected[0]["quote"])[1] if len(selected)==1 and selected[0]["kind"]=="citation" else ""
        matches = [r for r in register if raw and raw==r["number"]]
        identity = known_contract and all(literal(contract,k) and literal(contract,k)==literal(bank,v) for k,v in
                       (("contract_id","contract_id"),("buyer","payer"),("seller","payee")))
        designation = bound(bank,"payment_designation")
        allocation = allocations[0].get("clause_ref") if len(allocations)==1 else None
        evidence = [*payment["evidence"], *contract_refs, *bank.evidence("contract_id","payer","payee","payment_designation")]
        evidence.extend(ref for ref in (batch.get("rule_ref"),stage.get("clause_ref"),allocation) if ref)
        # The inventory also supports an absent or ambiguous number, without asserting a business link to those receipts.
        reviewed = [p for p in pages if p["role"]=="acceptance" or p["unit"]==unit]
        for p in reviewed:
            evidence.append(f"{p['doc']}/p{p['page']}")
        for r in ledger["rows"]:
            if r["role"]=="acceptance" or r["unit"]==unit:
                evidence.extend([r["id"],*r["facts"]])
        for r in register:
            evidence.extend(r["identity_refs"])
            if r["scope_ref"]:
                evidence.append(r["scope_ref"])
        acceptance_units = {p["unit"] for p in reviewed if p["role"]=="acceptance"}
        if not clear(unit) or not selected or any(not r["line"] or r["disputed"] for r in selected):
            state,status,detail="source","missing","付款所引验收资料含影像、异议或待定位原文，需核对原回单。"
        elif not number(raw):
            state,status,detail="reference","missing","回单的验收引用不唯一或单号不完整，需核对引用栏完整原文。"
        elif (not identity or not batch.get("independent") or not batch.get("contract_clear") or len(allocations)!=1
              or literal(bank,"payment_designation")!=stage.get("name") or not stage.get("clause_ref")):
            state,status,detail="scope","missing","需先对应回单用途、合同双方及该期约定的验收批次。"
        elif (len(own)!=1 or not own[0]["identified"] or any(not r["identified"] for r in register) or
              acceptance_units!={r["unit"] for r in register} or len(matches)>1):
            state,status,detail="records","missing","本期验收单、其他候选原件或编号归属尚未唯一对应。"
        elif not matches:
            state,status,detail="unlocated","missing","提交的验收原件中未找到回单所引完整单号，需取得相应凭证。"
        elif matches[0]["unit"]==own[0]["unit"]:
            state,status,detail="matched","ok",f"回单引用的验收单号与合同第 {index} 批验收原件相符。"
        elif matches[0]["batch"]:
            state,status,detail="other_batch","risk",f"本期对应第 {index} 批，回单所引单号属于第 {matches[0]['batch']} 批，需核实实际付款依据。"
        else:
            state,status,detail="records","missing","回单所引验收原件的范围与本期批次尚待核对。"
        payment["payment_acceptance"] = {"format":FORMAT,"bank":unit,"state":state,"status":status,"detail":detail,
            "batch":index,"clause_ref":stage.get("clause_ref"),"allocation_ref":allocation,
            "designation_ref":(designation or {}).get("id"),
            "citations":[r["id"] for r in selected],"number":raw or None,"register":register,
            "expected":[r["unit"] for r in own],"cited":[r["unit"] for r in matches],"evidence":list(dict.fromkeys(evidence))}
        if status!="ok" and payment["status"]=="ok":
            payment["detail"]=detail
        else:
            payment["detail"]+=" "+detail
        if LEVEL[status]>LEVEL[payment["status"]]:
            payment["status"]=status
        payment["scope"]=list(dict.fromkeys([*payment["scope"],*(p["unit"] for p in reviewed)]))
        payment["evidence"]=payment["payment_acceptance"]["evidence"]


def verify(report,read_text,*,signing=False):
    graph,policy = report["graph"],report["policy"]
    marker = policy.get("payment_acceptance")
    nodes = [n for n in graph["nodes"] if n["type"]=="payment_acceptance_line"]
    edges = [e for e in graph["edges"] if e["type"]=="payment_acceptance_source"]
    if marker is None:
        if (policy.get("version","")>=SINCE or "payment_acceptance.py" in policy.get("code_sha256",{}) or
                GRAPH_KEY in graph or nodes or edges or any("payment_acceptance" in f for f in report["findings"])):
            raise ValueError("回单验收单号核对的程序版本或原行缺失")
        if signing and any(f["rule"]=="H05" for f in report["findings"]):
            findings = [dict(f) for f in report["findings"]]
            apply({**graph,GRAPH_KEY:sources(graph,read_text)},findings)
            for original,current in zip(report["findings"],findings):
                check = current.get("payment_acceptance",{})
                if check.get("state")=="other_batch" or check and original["status"]=="ok" and check["status"]!="ok":
                    raise ValueError("旧版回单所引验收单与本期批次尚未核清，请按现行程序重新审计后签收。")
        return
    ledger = sources(graph,read_text)
    if marker!=FORMAT or ledger!=graph.get(GRAPH_KEY) or (nodes,edges)!=source_graph(ledger):
        raise ValueError("付款回单及对应验收单的原件、所列单号或原行关系与归档不符")
