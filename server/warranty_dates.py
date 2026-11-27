"""Read the two printed date lines cited by a warranty installment."""

import re
from collections import defaultdict
from datetime import date
from hashlib import sha256


FORMAT = "warranty-written-dates-v1"
KEY = "warranty_date_sources"
EDGE = "warranty_payment_dates"
SINCE = (2026, 11, 27, 14)
CERTIFICATE_LABELS = ("质保期满确认", "质保期满记录")
# All translations are one-to-one, so match offsets also select the literal in the original.
DISPLAY = str.maketrans("０１２３４５６７８９：／－．\u00a0\u2002\u2003\u2009\u202f\u3000",
                        "0123456789:/-.      ")
DATE = (r"(?P<literal>(?P<year>[0-9]{4}) *(?:年 *(?P<month>[0-9]{1,2}) *月 *(?P<day>[0-9]{1,2}) *日"
        r"|(?P<sep>[-/.]) *(?P<nmonth>[0-9]{1,2}) *(?P=sep) *(?P<nday>[0-9]{1,2})))")
STATEMENT = re.compile(" *" + DATE + r" *(?:双方确认 *)?质保期(?:已届满|届满|已满) *。? *")
RECEIPT = re.compile(" *" + DATE + " *")


def read_date(fact, labels, pattern):
    line = fact.get("source_line") or {}
    raw = line.get("text") or ""
    label, sep, body = raw.translate(DISPLAY).partition(":")
    if not sep or label.strip(" ") not in labels or not line.get("rects") or fact["status"] not in ("anchored", "confirmed"):
        return None
    match = pattern.fullmatch(body)
    if not match:
        return None
    # Each transcription must independently have complete digit groups and the very same statement.
    for text, require_label in ((fact["quote"], True), (fact["value"], False)):
        head, mark, value = text.translate(DISPLAY).partition(":")
        if mark and head.strip(" ") != label.strip(" ") or require_label and not mark:
            return None
        value = value if mark else head
        if not pattern.fullmatch(value) or value.replace(" ", "") != body.replace(" ", ""):
            return None
    try:
        parsed = date(int(match["year"]), int(match["month"] or match["nmonth"]), int(match["day"] or match["nday"]))
    except ValueError:
        return None
    start, end = match.span("literal")
    offset = len(label) + 1
    return {"ref":fact["id"], "doc":fact["doc"], "unit":fact.get("unit",fact["doc"]), "page":fact["page"],
            "line":line["number"], "literal":raw[offset+start:offset+end], "iso":parsed.isoformat()}


def sources(graph, read_text):
    from performance import DATE_LABELS

    pages, lines = [], []
    ledger = {"format":FORMAT, "pages":pages, "lines":lines}
    kinds = graph["documents_by_kind"]
    if not kinds.get("warranty") or not kinds.get("bank_receipt"):
        return ledger
    units = set(kinds["bank_receipt"])
    sections = {(u["source"],u["page"]):u["id"] for u in graph.get("audit_documents",()) if "source" in u}
    facts = defaultdict(list)
    for f in graph["facts"]:
        src = f.get("source_line") or {}
        if src.get("rects"):
            facts[f["doc"],f["page"],src["number"],src["text"]].append(f["id"])
    for n in graph["nodes"]:
        if n["type"] != "page":
            continue
        doc, suffix = n["id"].rsplit("/p",1)
        page = int(suffix)
        unit = sections.get((doc,page),doc)
        if unit not in units:
            continue
        place = {"doc":doc,"unit":unit,"page":page}
        native = n["layer"] == "text"
        pages.append({**place,"native":native})
        if native:
            text = read_text(doc,page)
            if not isinstance(text,str) or sha256(text.encode()).hexdigest() != n["text_sha256"]:
                raise ValueError("质保金回单日期的原页文字摘要不符")
            for number, raw in enumerate(text.splitlines(),1):
                label, sep, _ = raw.translate(DISPLAY).partition(":")
                if sep and label.strip(" ") in DATE_LABELS["paid_on"]:
                    lines.append({**place,"line":number,"quote":raw,"facts":facts[doc,page,number,raw]})
    return ledger


def single_reading(graph, material, field, pages, rows, labels, pattern):
    pages = [p for p in pages if p["unit"] == material.unit]
    rows = [r for r in rows if r["unit"] == material.unit]
    facts = material.fields[field]
    if not pages or not all(p["native"] for p in pages) or len(rows)!=1 or len(facts)!=1:
        return None
    row, fact = rows[0], facts[0]
    doc = next((d for d in graph["documents"] if d["id"]==row["doc"]),None)
    page_ref = f"{row['doc']}/p{row['page']}"
    node = next((n for n in graph["nodes"] if n["type"]=="page" and n["id"]==page_ref),None)
    if (not doc or not node or doc["sha256"]!=fact["source_sha256"] or node["sha256"]!=fact["page_sha256"]):
        return None
    heading_refs = []
    if material.incomplete(field):
        if field!="warranty_release" or any(not g.get("field") or g["field"]==field for g in material.gaps):
            return None
        # A title misclassified by the model has no date. Retain its exact independently located title witness.
        titles = material.fields["warranty"]
        if len(titles)!=1:
            return None
        title = titles[0]
        title_line = title.get("source_line") or {}
        if not title_line.get("rects") or title_line["text"] not in ("质保期满确认单","质保期满确认书"):
            return None
        for extra in material.refs:
            if extra["field"]!=field or extra["id"]==fact["id"]:
                continue
            if (extra["status"]!="visual" or extra.get("source_line")!=title_line or
                    any(extra[k]!=title[k] for k in ("doc","page","page_sha256","source_sha256")) or
                    extra["value"]!=extra["quote"] or extra["quote"]!=title_line["text"]):
                return None
            heading_refs.extend([title["id"],extra["id"]])
        if not heading_refs:
            return None
    source = fact.get("source_line") or {}
    if (row["facts"] != [fact["id"]] or row["doc"]!=fact["doc"] or row["page"]!=fact["page"] or
            not row["line"] or row["line"]!=source.get("number") or row["quote"]!=source.get("text")):
        return None
    reading = read_date(fact,labels,pattern)
    if reading:
        reading.update(original_sha256=doc["sha256"], page_sha256=node["sha256"])
        if heading_refs:
            reading["heading_refs"] = list(dict.fromkeys(heading_refs))
    return reading


def certificate(graph, material):
    ledger = graph["warranty_sources"]
    rows = [r for r in ledger["lines"] if r["kind"]=="warranty_release"]
    return single_reading(graph,material,"warranty_release",ledger["pages"],rows,CERTIFICATE_LABELS,STATEMENT)


def compare(graph, check, bank, paid, clause):
    from performance import DATE_LABELS

    cert = check["certificate"]
    stated = cert.get("date")
    if not stated:
        return None
    ledger = graph[KEY]
    bank_date = single_reading(graph,bank,"paid_on",ledger["pages"],ledger["lines"],DATE_LABELS["paid_on"],RECEIPT)
    if not bank_date or bank_date["iso"] != paid.isoformat():
        return None
    refs = [clause,*cert["records"],stated["doc"],f"{stated['doc']}/p{stated['page']}",stated["ref"],*stated.get("heading_refs",()),
            bank_date["doc"],f"{bank_date['doc']}/p{bank_date['page']}",bank_date["ref"],
            *bank.evidence("contract_id","payer","payee","transfer_status","payment_designation")]
    return {"stated_ref":stated["ref"], "bank":bank_date, "days":(paid-date.fromisoformat(stated["iso"])).days,
            "evidence":list(dict.fromkeys(refs))}


def edges(findings):
    return [{"from":c["stated_ref"], "to":c["bank"]["ref"], "type":EDGE, "evidence":c["evidence"]}
            for f in findings if f["rule"]=="H05" and (c:=f.get("warranty_payment",{}).get("comparison"))]


def verify(report, read_text, *, read_original=None):
    graph, policy = report["graph"], report["policy"]
    current = tuple(map(int,policy.get("version","0").split("."))) >= SINCE
    links = [e for e in graph["edges"] if e["type"]==EDGE]
    if not current:
        if (KEY in graph or "warranty_dates" in policy or "warranty_dates.py" in policy.get("code_sha256",{}) or links or
                any("date" in f.get("warranty_check",{}).get("certificate",{}) or "comparison" in f.get("warranty_payment",{})
                    for f in report["findings"])):
            raise ValueError("旧版质保金底稿出现未发行的书面日期程序")
        return
    if (policy.get("warranty_dates")!=FORMAT or "code_sha256" in policy and "warranty_dates.py" not in policy["code_sha256"] or
            graph.get(KEY)!=sources(graph,read_text) or links!=edges(report["findings"])):
        raise ValueError("质保金书面日期、回单原行或日期对照关系不符")
    if read_original:
        from original_records import verify_rendered
        units = {c["bank"]["unit"] for f in report["findings"] if (c:=f.get("warranty_payment",{}).get("comparison"))}
        nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
        records = []
        for page in graph[KEY]["pages"]:
            if page["unit"] in units:
                ref = f"{page['doc']}/p{page['page']}"
                node = nodes[ref]
                records.append({"doc":page["doc"],"pages":[{"ref":ref,"sha256":node["sha256"],"layer":node["layer"],
                                                           "text_only":node.get("clause_text_only") is True}]})
        if records:
            verify_rendered(graph,records,read_original,"质保金回单")
