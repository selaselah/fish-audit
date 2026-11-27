"""Compare the printed approval issue time with the actual debit on the particular bank receipt."""
from collections import defaultdict
from hashlib import sha256

from delegation import is_page_marker
from payment_acceptance import FIELD, LABELS as REFERENCE_LABELS, column
from payment_quality import BANK
from signer_clock import DEBIT, OTHER, interval, printed_clock


SIGNED = {"审批签发时间","签批完成时间","审批签发时刻"}
ACTUAL = DEBIT - {"扣款时间"}
EVENTS = OTHER | {"扣款时间","申请时间","预约扣款时间","入账时间"}
DISPLAY = str.maketrans("０１２３４５６７８９：＋（）－　","0123456789:+()- ")
WORDING = {
    "debit_first":"本期回单所列实际扣款早于审批单所列签发时刻，请核查扣款当时的授权依据。",
    "approval_first":"审批单所列签发时刻早于回单所列实际扣款，签批人身份、权限及实际签发仍待核。",
    "overlap":"两单所列时刻在打印精度内重叠，请核实更精确的签批和扣款记录。",
    "other_event":"回单所列时刻属于银行受理等其他环节，请补本笔实际扣款时刻。",
    "zone":"两单时刻尚无一致的明确时区，请取得可比较的时间基准。",
    "conflict":"时刻栏重复、日期冲突或原页有其他记载，请核对完整审批和银行记录。",
    "missing":"该笔付款的审批签发或实际扣款时刻尚无完整可定位原文。",
}


def bank_pages(graph, read_text, read_layout):
    from graph import LABELS, PRINTED_TITLES

    known={label:field for field in (*BANK,"transfer_ref","transfer_amount","payee_account") for label in LABELS[field]}
    known.update({label:FIELD for label in REFERENCE_LABELS[FIELD]})
    files={d["id"]:d for d in graph["documents"]}
    nodes={n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    facts=defaultdict(list)
    for fact in graph["facts"]:
        facts[fact["doc"],fact["page"]].append(fact)
    pages=[]
    for place in graph.get("payment_window_sources",{}).get("pages",()):
        if place["document_kind"]!="bank_receipt" or not place["native"]:
            continue
        doc,page=place["doc"],place["page"]
        source,node=files[doc],nodes[f"{doc}/p{page}"]
        text=read_text(doc,page)
        if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=node["text_sha256"]:
            raise ValueError("扣款时刻所据回单与归档文字不符")
        lines=[(i,raw) for i,raw in enumerate(text.splitlines(),1) if raw.strip() and not is_page_marker(raw)]
        if not any(column(raw)[0] in ACTUAL | EVENTS for _,raw in lines):
            continue
        complete=(page==1 and place["unit"]==doc and source.get("ext")==".pdf" and source.get("pages")==1 and place["text_only"]
                  and PRINTED_TITLES.get(lines[0][1].strip())=="bank_receipt" and not any(g["doc"]==doc for g in graph.get("gaps",()))
                  and not any(f["status"]=="disputed" for f in facts[doc,page]))
        rows,seen=[],set()
        geometry=read_layout(doc,page).get("lines",{})
        for i,raw in lines[1:]:
            label,_=column(raw)
            if label in known:
                field=known[label]
                if field in seen:
                    complete=False
                seen.add(field)
                continue
            field="debit_time" if label in ACTUAL else "bank_event" if label in EVENTS else "rider"
            locs=[f["id"] for f in facts[doc,page] if (f.get("source_line") or {}).get("number")==i and f["source_line"]["text"]==raw]
            rects=geometry.get(str(i),[])
            if field=="rider" or not rects:
                complete=False
            rows.append({"id":f"payment-clock/{doc}/p{page}/l{i}","field":field,"unit":place["unit"],"doc":doc,"page":page,"line":i,
                         "quote":raw,"page_sha256":node["sha256"],"rects":rects,"facts":locs})
        pages.append({"doc":doc,"page":page,"unit":place["unit"],"complete":complete and set(BANK)<=seen,"rows":rows})
    return pages


def assess(signed, bank, pages, paid_on):
    matching=[p for p in pages if p["unit"]==bank]
    rows=[r for p in matching for r in p["rows"]]
    if not rows and not signed:
        return None
    debits=[r for r in rows if r["field"]=="debit_time"]
    debit=debits[0] if len(debits)==1 else None
    check={"rows":[r["id"] for r in rows],"signed":signed["id"] if signed else None,"debit":debit["id"] if debit else None}
    if len(matching)>1 or len(debits)>1 or any(not p["complete"] for p in matching):
        return {**check,"state":"conflict"}
    if not debit and rows and all(r["field"]=="bank_event" for r in rows):
        return {**check,"state":"other_event"}
    if not signed or not debit:
        return {**check,"state":"missing"}
    clocks=[printed_clock(column(r["quote"])[1].translate(DISPLAY)) for r in (signed,debit)]
    if any(day and day!=paid_on for day,_,_ in clocks):
        return {**check,"state":"conflict"}
    if any(not at for _,at,_ in clocks):
        return {**check,"state":"missing"}
    if any(zone!="+08:00" for _,_,zone in clocks):
        return {**check,"state":"zone"}
    signature,actual=(interval(at) for _,at,_ in clocks)
    state="debit_first" if actual[1]<=signature[0] else "approval_first" if signature[1]<=actual[0] else "overlap"
    return {**check,"state":state,"signed_at":clocks[0][1],"debited_at":clocks[1][1],"zone":"+08:00"}


def event_lines(graph, bank):
    """A fully printed clock column on this receipt cannot supply a second inspection number."""
    return {(r["doc"],r["page"],r["line"],r["quote"]):r for p in graph.get("inspection_use_sources",{}).get("bank_clocks",())
            if p["complete"] and p["unit"]==bank for r in p["rows"] if r["field"] in {"debit_time","bank_event"}
            and r["rects"] and printed_clock(column(r["quote"])[1].translate(DISPLAY))[1]}


def split_receipt_notes(graph,bank,rows):
    events=event_lines(graph,bank)
    citations,timing=[],[]
    for raw in rows:
        event=events.get((raw["doc"],raw["page"],raw["line"],raw["quote"]))
        if raw["kind"]=="note" and not raw["disputed"] and event and set(raw["facts"])<=set(event["facts"]):
            timing.append({"note":raw["id"],"event":event["id"]})
        else:
            citations.append(raw)
    return citations,timing
