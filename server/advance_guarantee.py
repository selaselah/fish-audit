"""Documentary evidence for an express first-installment advance-guarantee receipt condition."""

import hashlib
import re
from collections import Counter, defaultdict
from datetime import date
from math import isfinite

from contract_folios import complete_number, line_numbers, verify_page_geometry
from delegation import is_page_marker
from payment_execution import BANK_TITLES
from payment_reference import masked_value
from stage_payments import LABELS as BANK_LABELS, RIDER as BANK_QUALIFIER


FORMAT = "advance-payment-guarantee-v1"
SINCE = "2026.11.27.05"
KEY = "advance_guarantee_sources"
RECTS = "advance_guarantee_rects"
TITLES = {"预付款保函": "guarantee", "预付款保函签收单": "receipt"}
FIRST = r"(?:第[一1]期|首期)"
BUYER = r"(?:采购方|买方|甲方)"
RECEIVE = BUYER + r"(?:须)?收到(?:以" + BUYER + r"为受益人的)?本合同项下(?:的)?预付款保函"
RIDER = re.compile(r"(?:预付款|首付款|" + FIRST + r"(?:预付款)?)(?:支付前提|付款前提|支付条件|付款条件)[:：]\s*" +
                   RECEIVE + r"后(?:方可|才可)支付" + FIRST + r"预付款[。]?")
INLINE = re.compile(r"(?P<stage>" + FIRST + r"|预付款|首付款)[:：]\s*(?:(?:本)?合同生效(?:后)?(?:且|并))?" + RECEIVE +
                    r"后(?:方可|才可)?支付(?:合同(?:总价|价款|总额)(?:的)?)?(?P<share>[0-9]{1,3}(?:\.[0-9]{1,4})?)[%％]。?")
INLINE_RIDER = re.compile(r"(?P<stage>" + FIRST + r")[:：]\s*(?:本)?合同生效后支付(?P<share>[0-9]{1,3}(?:\.[0-9]{1,4})?)[%％][，,；;]\s*" +
                          RECEIVE + r"后(?:方可|才可)支付" + FIRST + r"预付款。?")
FIRST_NAME = re.compile(FIRST + r"(?:预付款|款|付款)?|预付款|首付款")
EFFECT_STAGE = re.compile(r"(?:本)?合同生效后(?:支付|付)(?:合同(?:总价|价款|总额)(?:的)?)?[0-9]{1,3}(?:\.[0-9]{1,4})?[%％]。?")
CLAUSE_HINT = re.compile(r"保函|预付款担保")
ADVANCE_HINT = re.compile(r"预付|首付|首期|首款|第[一1]期")
LABELS = {
    "contract_id": ("合同编号", "合同号", "采购合同编号"), "buyer": ("采购方", "买方", "甲方", "采购单位", "购买方"),
    "seller": ("供应方", "卖方", "乙方", "供应商", "销售方"), "guarantee_id": ("保函编号",),
    "beneficiary": ("受益人",), "issued_on": ("开立日期",), "received_guarantee_id": ("签收保函编号",),
    "recipient": ("签收单位",), "received_on": ("签收日期",), "payer": ("付款户名","付款人名称","付款人户名"),
    "payee": ("收款户名","收款人名称","收款人户名"), "payment_designation": (*BANK_LABELS["payment_designation"],"用途"),
    "paid_on": ("付款日期","转账日期","交易日期","支付日期"), "transfer_status": ("交易状态","转账状态"),
    "transfer_ref": BANK_LABELS["transfer_ref"],
    "issuer": ("开立机构",), "payment_note": ("银行附言","附言"),
}
COLUMNS = {label: field for field, labels in LABELS.items() for label in labels}
FIELDS = {"contract": ("contract_id","buyer","seller"), "guarantee": ("contract_id","guarantee_id","beneficiary","issued_on"),
          "receipt": ("contract_id","received_guarantee_id","recipient","received_on"),
          "payment": ("contract_id","payer","payee","payment_designation","paid_on","transfer_status")}
SEVERITY = {"ok":0,"missing":1,"risk":2,"issue":3}
BANK_METADATA = {label for field in ("currency","unit","transfer_amount","payee_account") for label in BANK_LABELS[field]}


def value(row):
    return body(row["quote"])


def body(quote):
    return re.split(r"[:：]",quote,maxsplit=1)[-1].strip()


def inline_stage(quote):
    return INLINE.fullmatch(quote.strip()) or INLINE_RIDER.fullmatch(quote.strip())


def first_stage(finding):
    name=(finding.get("stage") or {}).get("name","")
    return name=="条款 1" or bool(FIRST_NAME.fullmatch(name))


def legible_name(raw):
    return bool(re.fullmatch(r"[A-Za-z0-9\u3400-\u9fff（）()· .&-]{1,120}",raw)
                and not re.search(r"尾号|待[核定填]|不详|未填写|未提供|另见|示例|附注|方可|另[须需]|须经",raw)
                and raw not in ("无","采购方","买方","甲方","供应方","乙方"))


def rectangles(rects):
    return isinstance(rects,list) and bool(rects) and all(isinstance(r,list) and len(r)==4 and
        all(type(v) in (int,float) and isfinite(v) and 0<=v<=1 for v in r) and r[0]<r[2] and r[1]<r[3] for r in rects)


def literal_day(raw):
    parts = re.fullmatch(r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日",raw)
    if not parts:
        parts = re.fullmatch(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})",raw)
    if parts:
        try:
            return date(*map(int,parts.groups())).isoformat()
        except ValueError:
            pass
    return None


def sources(graph, read_text, read_layout=None):
    """Read the original text separately from the model transcription; resolve rows within their own unit."""
    kinds = graph.get("documents_by_kind", {})
    contracts = set(kinds.get("contract", ()))
    amendments = set(kinds.get("contract_addendum", ()))
    ledger = {"format":FORMAT, "rows":[], "pages":[]}
    if not contracts:
        return ledger
    banks = set(kinds.get("bank_receipt", ()))
    docs = {d["id"]:d for d in graph["documents"]}
    sections = {(d["source"], d["page"]):d["id"] for d in graph.get("audit_documents", ()) if "source" in d}
    observations, pages = defaultdict(list), []
    for f in graph["facts"]:
        observations[f["doc"],f["page"]].append(f)
    for n in graph["nodes"]:
        if n["type"]=="page":
            doc, suffix = n["id"].rsplit("/p",1)
            num = int(suffix)
            pages.append((doc,num,sections.get((doc,num),doc),n))
    page_counts = Counter(p[0] for p in pages)

    def scan(page, contract=False):
        doc,num,unit,node = page
        native = node.get("layer")=="text"
        physical = []
        if native:
            text = read_text(doc,num)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256"):
                raise ValueError("预付款保函所据原页文字与出具摘要不符")
            physical = text.splitlines()
        facts = observations[doc,num]
        printed_titles = [TITLES[q.strip()] for q in physical if q.strip() in TITLES]
        if contract:
            role = "contract"
        elif printed_titles:
            role = printed_titles[0]
        elif unit in banks:
            role = "payment"
        else:
            hints = [TITLES[f["quote"].strip()] for f in facts if f["quote"].strip() in TITLES]
            name = docs[doc].get("name","")
            if not hints and "预付款保函" in name:
                hints = ["receipt" if "签收" in name else "guarantee"]
            if not hints:
                return
            role = hints[0]
        address = {"doc":doc,"unit":unit,"page":num,"original_sha256":docs[doc]["sha256"],"page_sha256":node["sha256"]}
        clean = native and node.get("clause_text_only") is True
        severe = any(g["doc"]==doc and g["page"]==num and g.get("quality") not in ("uncovered","uncovered_title")
                     for g in graph.get("gaps", ()))
        clean = clean and not severe
        headings = [q.strip() for q in physical if not is_page_marker(q)]
        if role in ("receipt","guarantee"):
            clean = clean and page_counts[doc]==1 and len(printed_titles)==1 and headings[0] in TITLES
        if role=="payment":
            columns=Counter(COLUMNS.get(re.split(r"[:：]",q,maxsplit=1)[0]) for q in headings)
            clean = (clean and page_counts[doc]==1 and bool(headings) and headings[0] in BANK_TITLES
                     and sum(q in BANK_TITLES for q in headings)==1 and not any(BANK_QUALIFIER.search(q) for q in headings)
                     and all(n==1 for field,n in columns.items() if field) and
                     sum(re.split(r"[:：]",q,maxsplit=1)[0] in BANK_LABELS["transfer_amount"] for q in headings)<=1)
        layout = read_layout(doc,num).get("lines",{}) if native and read_layout else {}
        located = defaultdict(list)
        for f in facts:
            loc=f.get("source_line") or {}
            if loc.get("text") and loc.get("number"):
                located[loc["number"]].append(f)
        rows = []
        def add(field, quote, number, matched, row_role, supported):
            exact = [f for f in matched if f["quote"]==quote and f.get("unit",f["doc"])==unit and
                     f.get("page_sha256")==node["sha256"] and f.get("source_sha256")==address["original_sha256"] and
                     (number is None or (f.get("source_line") or {}).get("text")==quote and f["source_line"]["number"]==number)]
            ids = [f["id"] for f in exact]
            locs = [f["source_line"]["rects"] for f in exact if (f.get("source_line") or {}).get("rects")]
            rects = layout.get(str(number), []) if read_layout else (locs[0] if locs else [])
            eligible = clean and number is not None and rectangles(rects) and all(rects==r for r in locs) and supported
            if any(f.get("status")=="disputed" or f.get("visual_check") in ("conflict","unreadable") for f in matched):
                eligible=False
            # Even unlocated/unsupported signals have a stable identity, but never a manufactured line or rectangle.
            suffix = "l"+str(number) if eligible else "hold"+str(len(rows)+1)
            ref = f"advance-guarantee/{doc}/p{num}/{suffix}"
            rows.append({**address,"id":ref,"role":row_role,"field":field,"line":number if eligible else None,
                         "quote":quote,"facts":ids,"rects":rects if eligible else []})
        for i,q in enumerate(physical,1):
            if is_page_marker(q):
                continue
            literal = q.strip()
            label = re.split(r"[:：]",literal,maxsplit=1)[0].strip()
            field = COLUMNS.get(label)
            if contract and CLAUSE_HINT.search(q):
                add("clause",q,i,located[i],"clause",True)
            elif contract and FIRST_NAME.fullmatch(label):
                add("payment_stage",q,i,located[i],role,True)
            elif literal in TITLES and role in ("receipt","guarantee") or role=="payment" and literal in BANK_TITLES:
                # An unrelated semantic label (e.g. a model calling the heading a purchase item)
                # supplies no title evidence. The original's exact heading has its own geometry.
                title_facts=[f for f in located[i] if f["field"] in ("other","bank_receipt") or f["status"]=="disputed"]
                add("title",q,i,title_facts,role,True)
            elif field in FIELDS[role] or role=="payment" and field=="transfer_ref":
                add(field,q,i,located[i],role,True)
            elif role=="guarantee" and field=="issuer" and legible_name(body(q)):
                add(field,q,i,located[i],role,True)
            elif role=="payment" and field=="payment_note" and re.fullmatch(
                    r"(?:本合同(?:项下)?(?:的)?)?(?:第[一1]期|首期)(?:付款|预付款)", body(q)):
                add(field,q,i,located[i],role,True)
            elif role in ("receipt","guarantee"):
                clean = False
            elif role=="payment" and label not in BANK_METADATA:
                clean = False
        if contract:
            for f in facts:
                if CLAUSE_HINT.search(f["quote"]) and f["quote"] not in physical:
                    add("clause",f["quote"],None,[f],"clause",False)
        elif role in ("guarantee","receipt") and not printed_titles:
            hint = next((f for f in facts if f["quote"].strip() in TITLES),None)
            add("title",hint["quote"] if hint else docs[doc]["name"],None,[hint] if hint else [],role,False)
        if role in ("receipt","guarantee","payment"):
            clean = clean and any(r["field"]=="title" and r["line"] for r in rows)
            if not clean:
                for i,r in enumerate(rows,1):
                    r.update(id=f"advance-guarantee/{doc}/p{num}/hold{i}",line=None,rects=[])
        ledger["pages"].append({**address,"role":role,"native":native,"text_only":node.get("clause_text_only") is True,"clean":clean})
        ledger["rows"].extend(rows)

    for p in pages:
        if p[2] in contracts|amendments:
            scan(p,contract=True)
    if not any(r["role"]=="clause" and ADVANCE_HINT.search(r["quote"]) for r in ledger["rows"]):
        return {"format":FORMAT,"pages":[],"rows":[]}
    for p in pages:
        if p[2] not in contracts|amendments:
            scan(p)
    return ledger


def source_graph(ledger):
    nodes, edges = [], []
    for row in ledger["rows"]:
        pg = f"{row['doc']}/p{row['page']}"
        nodes.append({k:row[k] for k in ("id","role","field","doc","unit","page","line","original_sha256","page_sha256")} |
                     {"type":"advance_guarantee_line","label":row["quote"]})
        edges.append({"type":"advance_guarantee_source","from":pg,"to":row["id"],"evidence":[pg,*row["facts"]]})
    return nodes, edges


def terms(graph, unit=None):
    return [r for r in graph.get(KEY,{}).get("rows",()) if r["role"]=="clause" and (unit is None or r["unit"]==unit)]


def scoped(graph, unit):
    rows = terms(graph)
    if len(rows)!=1 or rows[0]["unit"]!=unit or unit not in graph["documents_by_kind"].get("contract",()) or not rows[0]["line"]:
        return None
    row=rows[0]
    if any(not p["clean"] for p in graph[KEY]["pages"] if p["unit"]==unit):
        return None
    inline = inline_stage(row["quote"])
    if not inline and not RIDER.fullmatch(row["quote"].strip()):
        return None
    targets=[r for r in graph[KEY]["rows"] if r["unit"]==unit and (r["field"]=="payment_stage" or inline and r is row)]
    if len(targets)!=1 or not targets[0]["line"] or not (inline or EFFECT_STAGE.fullmatch(value(targets[0]))):
        return None
    t=targets[0]
    anchored=[f for f in graph["facts"] if f["id"] in t["facts"] and f["field"]=="payment_stage" and
              f["status"] in ("anchored","confirmed") and f["quote"]==t["quote"] and f["value"] in (t["quote"],value(t)) and
              f.get("unit",f["doc"])==unit and f.get("page_sha256")==t["page_sha256"] and f.get("source_sha256")==t["original_sha256"] and
              any(e["type"]=="payment_stage" and e["from"]==unit and e["evidence"]==[f["id"]] for e in graph["edges"])]
    return row if len(anchored)==1 else None


def bounded_units(graph):
    return {p["unit"] for p in graph.get(KEY,{}).get("pages",()) if p["role"] in ("guarantee","receipt") and p["clean"]}


def independent_transfer(ledger, unit):
    """An additional receipt can be separated by a different installment or a unique, complete bank reference."""
    payments = defaultdict(list)
    for r in ledger["rows"]:
        if r["role"]=="payment":
            payments[r["unit"]].append(r)

    def unique(rows, field):
        matching = [r for r in rows if r["field"]==field]
        return value(matching[0]) if len(matching)==1 and matching[0]["line"] else ""

    ref = unique(payments[unit],"transfer_ref")
    for peer in {p["unit"] for p in ledger["pages"] if p["role"]=="payment" and p["unit"]!=unit}:
        other = unique(payments[peer],"transfer_ref")
        if ref and ref.casefold()==other.casefold():
            return False
        designation = unique(payments[peer],"payment_designation")
        if re.fullmatch(r"第(?:[二三四五六七八九十]+|[2-9]|[1-9][0-9]+)期(?:款|付款)?|尾款|质保金", designation):
            continue
        if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",n) and re.search(r"[0-9]",n) and not masked_value(n)
                   for n in (ref,other)):
            return False
    return True


def assessment(graph, phase, payment=None):
    ledger=graph[KEY]
    contracts=graph["documents_by_kind"].get("contract",[])
    if len(contracts)!=1:
        return None
    owner=contracts[0]
    rules=terms(graph)
    if not rules or not first_stage(phase):
        return None
    all_rows=ledger["rows"]
    sources=[*rules]
    def selected(role,unit=None):
        rows=[r for r in all_rows if r["role"]==role and (unit is None or r["unit"]==unit)]
        sources.extend(rows)
        result={}
        for field in FIELDS[role]:
            choices=[r for r in rows if r["field"]==field]
            if len(choices)==1 and choices[0]["line"]:
                result[field]=value(choices[0])
        return result
    c=selected("contract",owner)
    g=selected("guarantee")
    r=selected("receipt")
    issued=received=paid=None
    first=scoped(graph,owner)
    def finish(state, detail, status="missing"):
        items=list({s["id"]:s for s in sources}.values())
        evidence=list(dict.fromkeys(ref for s in items for ref in (s["id"],s["doc"],f"{s['doc']}/p{s['page']}",*s["facts"])))
        return {"state":state,"status":status,"detail":detail,"issued_on":issued,"received_on":received,"paid_on":paid,
                "sources":items,"evidence":evidence,"units":list(dict.fromkeys(s["unit"] for s in items))}
    if payment:
        banks=set(payment["scope"]) & set(graph["documents_by_kind"].get("bank_receipt",()))
        if len(banks)==1:
            unit=banks.pop()
            bank=selected("payment",unit)
            if (first and set(bank)==set(FIELDS["payment"]) and FIRST_NAME.fullmatch(bank["payment_designation"]) and
                    c.get("buyer")!=c.get("seller") and
                    (bank["contract_id"],bank["payer"],bank["payee"])==(c.get("contract_id"),c.get("buyer"),c.get("seller")) and
                    bank["transfer_status"] in ("交易成功","转账成功","成功","已完成") and not payment.get("execution_basis") and
                    independent_transfer(ledger,unit)):
                paid=literal_day(bank["paid_on"])
    if not first:
        return finish("review","预付款保函的适用期次、完整约定或原页版式待核。")
    pages={role:[p for p in ledger["pages"] if p["role"]==role] for role in ("guarantee","receipt")}
    if any(len(v)>1 or any(not p["clean"] for p in v) for v in pages.values()):
        return finish("review","保函或签收材料有多份、附注、影像或归属疑点，请核对完整原件。")
    if not pages["guarantee"] or set(g)!=set(FIELDS["guarantee"]) or not complete_number(g.get("guarantee_id","")):
        return finish("missing","待取得可定位的预付款保函，核对合同号、保函编号、受益人及开立日期。")
    if (set(c)!=set(FIELDS["contract"]) or c["buyer"]==c["seller"] or not all(legible_name(x) for x in (c["buyer"],c["seller"],g["beneficiary"])) or
            not all(complete_number(x) for x in (c["contract_id"],g["contract_id"]))):
        return finish("review","原合同或保函的完整合同编号、主体待核。")
    if c["contract_id"]!=g["contract_id"]:
        return finish("mismatch","保函所列合同编号与本合同不同，不能归入本期。","risk")
    issued=literal_day(g["issued_on"])
    if not issued:
        return finish("review","保函开立日期原行待核。")
    if g["beneficiary"]!=c["buyer"]:
        explicit="为受益人" in first["quote"]
        return finish("mismatch","保函所列受益人与合同约定的采购方不同。" if explicit else
                      "保函所列受益人与采购方名称不同，请核实该份保函的归属和约定受益人。","risk" if explicit else "missing")
    if not pages["receipt"] or set(r)!=set(FIELDS["receipt"]):
        return finish("missing","已有保函记载，尚缺可与本合同、本保函对应的采购方签收原件。")
    if not legible_name(r["recipient"]) or not all(complete_number(x) for x in (r["contract_id"],r["received_guarantee_id"])):
        return finish("review","签收原件的合同号或所收保函编号不完整。")
    if (r["contract_id"],r["received_guarantee_id"],r["recipient"])!=(c["contract_id"],g["guarantee_id"],c["buyer"]):
        return finish("mismatch","签收单所列合同、保函编号或签收单位与本合同及保函原件不相符。","risk")
    received=literal_day(r["received_on"])
    if not received or received<issued:
        received=None
        return finish("review","签收日期缺乏完整原行或早于开立日期，请核对。")
    if not payment:
        return finish("recorded","采购方签收单记载了本保函及签收日期。保函真实性、效力及付款授权待人工核验。")
    if not paid:
        return finish("review","待核对明列本期的成功扣款原件及付款日。")
    if paid<received:
        return finish("before_receipt",f"回单付款日 {paid} 早于签收单记载的 {received}，请复核提前付款依据。","risk")
    if paid==received:
        return finish("same_day",f"付款与签收同为 {paid}，需取得时分记录核对先后。")
    return finish("after_receipt",f"回单付款日 {paid} 晚于签收登记日 {received}。保函真实性、效力及付款授权待人工核验。")


def assessed_findings(graph, findings):
    def stage_key(f):
        stage=f.get("stage") or {}
        return stage.get("clause_ref"),stage.get("name")
    phases={stage_key(f):f for f in findings if f["rule"]=="H04" and f.get("stage")}
    for f in findings:
        if f["rule"] not in ("H04","H05") or not (phase:=phases.get(stage_key(f))):
            continue
        proof=assessment(graph,phase,f if f["rule"]=="H05" else None)
        if proof:
            yield f,proof


def apply(graph,findings):
    if not terms(graph):
        return
    for f,proof in assessed_findings(graph,findings):
        f["advance_guarantee"]=proof
        f["evidence"]=list(dict.fromkeys([*f["evidence"],*proof["evidence"]]))
        f["scope"]=list(dict.fromkeys([*f["scope"],*proof["units"]]))
        if SEVERITY[proof["status"]]>SEVERITY[f["status"]]:
            f.update(status=proof["status"],detail=proof["detail"])
        else:
            f["detail"]+=" "+proof["detail"]


def verify(report,read_text,*,signing=False,read_layout=None):
    graph,policy=report["graph"],report["policy"]
    marker=policy.get("advance_guarantee")
    claims=[f for f in report["findings"] if "advance_guarantee" in f]
    nodes=[n for n in graph.get("nodes",()) if n["type"]=="advance_guarantee_line"]
    edges=[e for e in graph.get("edges",()) if e["type"]=="advance_guarantee_source"]
    calls=report.get("calls",{}).get("pages",[])
    methods=policy.get("code_sha256",{})
    if marker is None:
        if (policy.get("version","")>=SINCE or "advance_guarantee.py" in methods or KEY in graph or nodes or edges or claims
                or any(RECTS in c for c in calls)):
            raise ValueError("底稿缺少预付款保函程序标记")
        if signing and any(f["status"]=="ok" and f["rule"] in ("H04","H05") and first_stage(f) for f in report["findings"]):
            if sources(graph,read_text,read_layout)["rows"]:
                raise ValueError("旧版已通过的首期付款尚未核对预付款保函及签收原件，请重审后签收。")
        return
    if marker!=FORMAT or policy.get("version","")<SINCE or "code_sha256" in policy and "advance_guarantee.py" not in methods:
        raise ValueError("预付款保函程序与出具版本不符")
    by_page={(c["doc"],c["page"]):c for c in calls}
    layout=read_layout
    if layout is None and "calls" in report:
        def layout(doc,page):
            return {"lines":by_page.get((doc,page),{}).get(RECTS,{})}
    actual=sources(graph,read_text,layout)
    if actual!=graph.get(KEY) or (nodes,edges)!=source_graph(actual):
        raise ValueError("预付款保函原件、原行或来源关系与归档不符")
    expected = {f["id"]:p for f,p in assessed_findings(graph,report["findings"])} if actual["rows"] else {}
    if ({f["id"] for f in claims}!=expected.keys() or any(f["advance_guarantee"]!=expected[f["id"]] or
            SEVERITY[f["status"]]<SEVERITY[expected[f["id"]]["status"]] for f in claims)):
        raise ValueError("预付款保函或付款先后结论与本期原行不符")
    if "calls" in report:
        if any(by_page.get((p["doc"],p["page"]),{}).get("page_sha256")!=p["page_sha256"] for p in actual["pages"]):
            raise ValueError("预付款保函所据原页摘要与分页记录不符")
        rects=defaultdict(dict)
        for r in actual["rows"]:
            if r["line"]:
                rects[r["doc"],r["page"]][str(r["line"])]=r["rects"]
        verify_page_geometry(calls,line_numbers(actual["rows"]),rects,RECTS,"预付款保函",read_layout)
        supports={(e["from"],e["to"]) for e in graph["edges"] if e["type"]=="supports_result" and e["evidence"]==[e["from"]]}
        for f in claims:
            p=f["advance_guarantee"]
            if (not set(p["units"])<=set(f["scope"]) or not set(p["evidence"])<=set(f["evidence"]) or
                    any((ref,"finding/"+f["id"]) not in supports for ref in p["evidence"])):
                raise ValueError("预付款保函依据未绑定本期结论")
