"""Locate reservations about final inspection independently of the extracted result box."""

import hashlib
import re
import unicodedata
from collections import defaultdict

import acceptance_payments
import inspection_register
import supplier_pages
from calculations import normalized
from performance_versions import FORMAT as CURRENT


LEGACY = "acceptance-reservations-v1"
SUPPLIER = "acceptance-reservations-v2"
OPINIONS = "acceptance-reservations-v3"
FORMAT = "acceptance-reservations-v4"
OPINION_FORMATS = (OPINIONS, FORMAT)
SUPPLIER_FORMATS = (SUPPLIER, *OPINION_FORMATS)
SELLER = {"供应方","供方","卖方","乙方","供应商","供货方","供货单位","销售方","销方"}
DELIVERY = re.compile(r"实际(?:供货|供应|交付)(?:单位|方|人|商)?|(?:代为|代行|委托|代替|代为其|受托|另行指定).{0,22}(?:供货|交付|交货)|第三方(?:供货|交付|送货)")
INCOMPLETE = re.compile(r"[*＊×□…]|待定|待填|不详|未提供|同(?:主)?合同|另见|尾号|^(?:无|略|乙方|供方|卖方|同上|—+|-+)$")


def supplier_kind(raw):
    label,sep,_=unicodedata.normalize("NFKC",raw).strip().partition(":")
    if DELIVERY.search(normalized(raw)) or label.strip() in {"交付单位","送货单位","发货单位","代供单位","受托供货方"}:
        return "delivery_note"
    if sep and label.strip() in SELLER:
        return "seller"
    return None
LABELS = {"验收备注", "验收保留意见", "验收附注", "签收说明", "验收限制", "保留意见", "复验备注", "复验保留意见"}
CLEAR = {"无", "无保留意见", "无验收保留意见", "无其他验收限制"}
LIMIT = re.compile(
    r"(?:仅|只|暂)(?:作|为|确认|代表|完成|办理|进行|核对|验收|查验|检验|检查){0,3}(?:本次)?(?:到货|签收|外观|数量|包装|初验|暂收|点收)"
    r"|(?:不作为|不代表|不构成|不能视为|不等于|不得作为|仅为暂收).{0,8}(?:最终验收|终验|合格验收|验收合格)"
    r"|(?:尚未|未经|未完成|未进行|待完成|待补做)(?:整机|功能|性能|联调|最终|全部|质量|现场|项目){0,3}(?:测试|检测|检验|试验|调试|验收|复验|联调)"
    r"|(?:整机|功能|性能|联调|质量)(?:项目|指标)?(?:待检|未检|待测|未测)"
    r"|(?:最终验收|终验|复验|性能测试|功能测试)(?:将|须|需|应|尚待)?(?:另行|另约|待补|待办|暂缓|尚未|未完成|待完成)"
    r"|(?:有条件|附条件)(?:通过|验收|合格)|(?:临时|暂作|暂予|仅作)签收"
)


def classify(quote):
    text = normalized(quote).rstrip("。")
    label, separator, value = text.partition(":")
    if LIMIT.search(text):
        return "limited"
    if label in LABELS and separator and value not in CLEAR:
        return "unclear"
    return None


def sources(graph, read_text, format=FORMAT):
    units = {unit for kind in ("acceptance", "reinspection") for unit in graph["documents_by_kind"].get(kind, [])}
    sections = {(d["source"], d["page"]): d["id"] for d in graph.get("audit_documents", []) if "source" in d}
    observations = defaultdict(list)
    for fact in graph["facts"]:
        observations[fact["doc"], fact["page"]].append(fact)
    contracts=set(graph["documents_by_kind"].get("contract",[])) if format in SUPPLIER_FORMATS else set()
    opinions,qualifications=[],[]
    if format in OPINION_FORMATS:
        from graph import LABELS as fields
        known={label for key,labels in fields.items() if key!="release_signed_on" for label in labels} | LABELS | acceptance_payments.HEADINGS
    supplier_rows, supplier_pages = [], []
    pages, lines = [], []
    for node in graph["nodes"]:
        if node["type"] != "page":
            continue
        doc, number = node["id"].rsplit("/p", 1)
        page = int(number)
        unit = sections.get((doc, page), doc)
        if unit not in units and unit not in contracts:
            continue
        place = {"unit": unit, "doc": doc, "page": page}
        native = node.get("layer") == "text"
        coverage={**place,"native":native,"text_only":node.get("clause_text_only") is True}
        if unit in units:
            pages.append(coverage)
        if format in SUPPLIER_FORMATS:
            supplier_pages.append({**coverage,"role":"contract" if unit in contracts else "receipt"})
        anchored = defaultdict(list)
        for fact in observations[doc, page]:
            loc = fact.get("source_line") or {}
            if native and loc.get("rects"):
                anchored[loc["number"], loc["text"]].append(fact["id"])
            elif format in SUPPLIER_FORMATS and (party_kind:=supplier_kind(fact["quote"])):
                supplier_rows.append({**place,"line":None,"kind":party_kind,"quote":fact["quote"],"facts":[fact["id"]]})
                if unit in units and (kind:=classify(fact["quote"])):
                    lines.append({**place,"line":None,"kind":kind,"quote":fact["quote"],"facts":[fact["id"]]})
            elif unit in units and (kind := classify(fact["quote"])):
                lines.append({**place, "line": None, "kind": kind, "quote": fact["quote"], "facts": [fact["id"]]})
        text=None
        if native:
            text = read_text(doc, page)
            if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != node.get("text_sha256"):
                raise ValueError("验收保留意见所据的原页文字摘要不符")
            for i, raw in enumerate(text.splitlines(), 1):
                if format in SUPPLIER_FORMATS and (party_kind:=supplier_kind(raw)):
                    supplier_rows.append({**place,"line":i,"kind":party_kind,"quote":raw,"facts":anchored[i,raw]})
                if unit in units and (kind := classify(raw)):
                    lines.append({**place, "line": i, "kind": kind, "quote": raw, "facts": anchored[i, raw]})
        if format in OPINION_FORMATS and unit in units:
            items,extra=acceptance_payments.page_rows(place,text,observations[doc,page],known)
            opinions.extend(items)
            qualifications.extend(extra)
    result={"format":format,"pages":pages,"lines":lines}
    if format in SUPPLIER_FORMATS:
        result.update(supplier_rows=supplier_rows,supplier_pages=supplier_pages)
    if format in OPINION_FORMATS:
        active={s["unit"] for s in opinions}
        result["payment_opinions"]=opinions+[s for s in qualifications if s["unit"] in active]
    if format == FORMAT:
        result["final_register"] = inspection_register.sources(graph, read_text)
    return result


def edges(ledger):
    result=[]
    for key,relation in (("lines","acceptance_reservation"),("supplier_rows","supplier_identity_basis"),
                         ("payment_opinions","acceptance_payment_opinion")):
        for row in ledger.get(key,[]):
            page=f"{row['doc']}/p{row['page']}"
            result.append({"type":relation,"from":row["unit"],"to":page,"line":row["line"],"evidence":[page,*row["facts"]]})
    if "final_register" in ledger:
        result.extend(inspection_register.edges(ledger["final_register"]))
    return result


def supplier_check(ledger, scope, graph):
    pages=[p for p in ledger["supplier_pages"] if p["unit"] in scope]
    rows=[s for s in ledger["supplier_rows"] if s["unit"] in scope]
    names={}
    facts={f["id"]:f for f in graph["facts"]}
    by_unit=defaultdict(set)
    for fact in graph["facts"]:
        if fact["field"]=="seller":
            by_unit[fact.get("unit",fact["doc"])].add(fact["id"])
    for unit in dict.fromkeys(p["unit"] for p in pages):
        entries=[s for s in rows if s["unit"]==unit and s["kind"]=="seller"]
        if len(entries)!=1 or not entries[0]["line"]:
            continue
        source=entries[0]
        supported=[facts[ref] for ref in source["facts"] if ref in facts and facts[ref]["field"]=="seller"
                   and facts[ref]["status"] in ("anchored","confirmed") and facts[ref]["quote"]==source["quote"]]
        if len(supported)==1 and by_unit[unit]=={supported[0]["id"]}:
            raw=source["quote"].replace("：",":").partition(":")[2].strip()
            if raw and not INCOMPLETE.search(raw) and supported[0]["value"].strip() in (raw,source["quote"]):
                names[unit]=raw
    inspected = [p for p in graph.get("supplier_page_sources", {}).get("pages", []) if p["unit"] in scope]
    supported = {(p["doc"], p["page"]) for p in inspected if supplier_pages.supported(p, rows, facts)}
    if len(set(names.values()))>1:
        status,detail="risk","合同与验收或复验原件所列供应方名称不一致，请核实主体归属及有无委托交付约定。"
    elif any(row["kind"]=="delivery_note" for row in rows):
        status,detail="missing","另有实际供货或委托交付说明，须取得其与合同供应方的关系及对应交付依据。"
    elif any(p["state"] == "annotations" for p in inspected):
        has_reason = any(a["kind"] == "signature_reason" for p in inspected for a in p["annotations"])
        detail = ("PDF 签名属性另有签署原因，请核对其对供货主体与验收范围的影响。" if has_reason else
                  "供应方原页含 PDF 批注或表单，请核对其对供货主体及验收归属的影响。")
        status = "missing"
    elif len(names)!=len({p["unit"] for p in pages}) or any(not p["native"] or not p["text_only"] and (p["doc"],p["page"]) not in supported for p in pages):
        status,detail="missing","须核对合同及各次验收原页的完整供应方名称、影像附注或补充可关联的交付凭证。"
    else:
        status,detail="ok","合同与所据验收原件的供应方名称相符。"
    result = {"status":status,"detail":detail,"pages":pages,"lines":rows,"names":names}
    if inspected:
        result["page_inspections"] = [p["id"] for p in inspected]
        result["matching_print"] = [p["id"] for p in inspected if (p["doc"], p["page"]) in supported]
    return result


def apply(finding, ledger, graph=None):
    scope = set(finding["scope"])
    pages = [p for p in ledger.get("pages", []) if p["unit"] in scope]
    if not pages:
        return False
    lines = [s for s in ledger["lines"] if s["unit"] in scope]
    mixed = [p for p in pages if not p["native"] or not p["text_only"]]
    refs = [f"{p['doc']}/p{p['page']}" for p in pages] + [ref for row in lines for ref in row["facts"]]
    finding["acceptance_reservations"] = {"pages": pages, "lines": lines, "mixed_pages": mixed}
    supplier_hold=False
    if ledger.get("format") in SUPPLIER_FORMATS and graph is not None:
        supplier=supplier_check(ledger,scope,graph)
        finding["acceptance_reservations"]["supplier"]=supplier
        refs.extend(f"{p['doc']}/p{p['page']}" for p in supplier["pages"])
        refs.extend(ref for s in supplier["lines"] for ref in s["facts"])
        refs.extend(supplier.get("page_inspections", []))
        supplier_hold=supplier["status"]!="ok"
        if supplier_hold:
            if finding["status"]=="ok":
                finding.update(status=supplier["status"],detail=supplier["detail"])
            else:
                if finding["status"]=="missing" and supplier["status"]=="risk":
                    finding["status"]="risk"
                finding["detail"]+=" "+supplier["detail"]
            if finding.get("reinspection"):
                finding["reinspection"]["state"]="open"
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *refs]))
    if not (lines or mixed):
        return supplier_hold
    printed_limit = any(s["line"] and s["kind"] == "limited" for s in lines)
    before = finding["status"]
    if before not in ("issue", "risk"):
        finding["status"] = "risk" if printed_limit else "missing"
    detail = ("验收原页另载检查范围或终验限制，须核实其覆盖的项目及后续正式验收记录。" if printed_limit else
              "验收原页有待辨的保留意见或影像，须核实完整检查范围及正式终验记录。")
    if before == "ok":
        finding["detail"] = detail
    else:
        finding["detail"] += " " + detail
    if finding.get("reinspection"):
        finding["reinspection"]["state"] = "open"
    return True


def verify(report, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("acceptance_reservations")
    if signing and marker != FORMAT:
        positives = [f for f in report["findings"] if f["rule"] == "H02" and f["status"] == "ok" and f.get("reinspection")]
        if positives:
            register = inspection_register.sources(graph, read_text)
            for finding in positives:
                check = inspection_register.assess(finding, register, graph)
                if check and check["status"] != "ok":
                    raise ValueError("旧版复验结论仍有待核的整改明细或签认附言，请重新审计后签收。")
    if not marker:
        if ("acceptance_reservations.py" in policy.get("code_sha256", {}) or "acceptance_reservation_sources" in graph
                or policy.get("performance_checks") == CURRENT):
            raise ValueError("缺少验收保留意见程序标记")
        if signing:
            current=sources(graph,read_text)
            acceptance_payments.legacy_signoff(report,current)
            for f in report["findings"]:
                if f["rule"] == "H02" and f["status"] == "ok" and not f.get("batch_acceptance"):
                    if apply(dict(f, reinspection=dict(f.get("reinspection") or {})), current,graph):
                        raise ValueError("旧版终验仍有保留意见或原页影像待核，请重新审计后签收。")
        return
    if signing and marker==LEGACY:
        current=sources(graph,read_text)
        for f in report["findings"]:
            if f["rule"]=="H02" and f["status"]=="ok" and not f.get("batch_acceptance"):
                if supplier_check(current,set(f["scope"]),graph)["status"]!="ok":
                    raise ValueError("旧版验收供应方或第三方供货依据待核，请按现行程序重审后签收。")
    if signing and marker not in OPINION_FORMATS:
        acceptance_payments.legacy_signoff(report,sources(graph,read_text))
    ledger = sources(graph,read_text,marker)
    actual = [e for e in graph["edges"] if e["type"] in ("acceptance_reservation","supplier_identity_basis","acceptance_payment_opinion","reinspection_register_line")]
    version=policy.get("version","")
    if (marker not in (*SUPPLIER_FORMATS,LEGACY) or "2026.11.25.04"<=version<acceptance_payments.SINCE and marker!=SUPPLIER
            or acceptance_payments.SINCE<=version<inspection_register.SINCE and marker!=OPINIONS
            or version>=inspection_register.SINCE and marker!=FORMAT or policy.get("performance_checks") != CURRENT
            or graph.get("acceptance_reservation_sources") != ledger or actual != edges(ledger)):
        raise ValueError("验收保留意见、整页影像覆盖或证据关系与归档不符")
