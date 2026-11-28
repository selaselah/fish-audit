"""Compare printed party names with the signing block and separate seal-holder fields on a contract."""

import re
import unicodedata

from contract_changes import SOURCE_LABELS
from delegation import PARTY_SIGNATURES


NATIVE_FORMAT = "contract-effect-sources-v4"
IMAGE_FORMAT = "contract-effect-sources-v5"
WORD_FORMAT = "contract-effect-sources-v6"
CALENDAR_FORMAT = "contract-effect-sources-v7"
FORM_FORMAT = "contract-effect-sources-v8"
CALENDAR_FORMATS = (CALENDAR_FORMAT, FORM_FORMAT)
WORD_FORMATS = (WORD_FORMAT, *CALENDAR_FORMATS)
IMAGE_FORMATS = (IMAGE_FORMAT, *WORD_FORMATS)
IMPRINT_FIELDS={"buyer_seal_name":("甲方印章单位名称","采购方印章单位名称","买方印章单位名称"),
                "seller_seal_name":("乙方印章单位名称","供应方印章单位名称","卖方印章单位名称")}
SIDES={"buyer":"甲方","seller":"乙方"}
FIELDS={}
for _side in SIDES:
    for _role,_field,_labels in (("party",_side,SOURCE_LABELS[_side]),
                                 ("signature",_side+"_signature",PARTY_SIGNATURES[_side+"_signature"]),
                                 ("imprint",_side+"_seal_name",IMPRINT_FIELDS[_side+"_seal_name"])):
        for _label in _labels:
            FIELDS[_label]=(_side,_role,_field)
FIELDS["印章单位名称"]=("unspecified","imprint",None)
SEAL=re.compile(r"(.+?)(?:（已盖章）|\(已盖章\)|已盖章)$")
ORG=re.compile(r"[\u3400-\u9fffA-Za-z0-9（）()·&-]{2,90}(?:公司|中心|厂|商行|银行|分行|支行|合作社|事务所|研究院|研究所|经营部|工作室)")
UNCERTAIN=re.compile(r"简称|疑似|不清|模糊|遮挡|部分|字样|另见|暂用|不详|尾号|代章|代签|曾用名|[＊*×?？…□]")


def split(raw):
    pieces=re.split("[:：]",raw,maxsplit=1)
    if len(pieces)!=2:
        return raw.strip(),""
    return pieces[0].strip(),unicodedata.normalize("NFC",pieces[1].strip())


def row(place,raw,line,facts):
    label,_=split(raw)
    if label not in FIELDS:
        return None
    side,role,field=FIELDS[label]
    refs=[f["id"] for f in facts if f.get("unit",f["doc"])==place["unit"]]
    if line is None and not refs:
        return None
    key=f"{place['doc']}/p{place['page']}/l{line}" if line is not None else refs[0]
    return {**place,"id":"signing-line/"+key,"side":side,"role":role,"field":field,
            "line":line,"quote":raw,"facts":refs}


def source_graph(ledger):
    nodes,edges=[],[]
    for r in ledger.get("signing_rows",[]):
        page=f"{r['doc']}/p{r['page']}"
        nodes.append({"id":r["id"],"type":"contract_signing_line","label":r["quote"],"doc":r["doc"],"page":r["page"],"line":r["line"]})
        edges.append({"from":page,"to":r["id"],"type":"contract_signing_source","evidence":[page,*r["facts"]]})
    return nodes,edges


def complete(value):
    return bool(ORG.fullmatch(value) and not UNCERTAIN.search(value))


def typed(r,contract):
    matches=[f for f in contract.fields.get(r["field"],[]) if f["id"] in r["facts"] and f["doc"]==r["doc"] and f["page"]==r["page"]
             and (f.get("source_line") or {}).get("number")==r["line"] and (f.get("source_line") or {}).get("text")==r["quote"]
             and (f.get("source_line") or {}).get("rects") and f["quote"]==r["quote"] and
             unicodedata.normalize("NFC",f["value"].strip()) in (unicodedata.normalize("NFC",r["quote"]),split(r["quote"])[1])]
    return matches[0] if len(matches)==1 else None


def checked(f,graph):
    if not f or f["status"]!="confirmed":
        return False
    a=f.get("attestation") or {}
    c=a.get("source_check") or {}
    doc=next((d for d in graph["documents"] if d["id"]==f["doc"]),{})
    page=next((n for n in graph["nodes"] if n["id"]==f"{f['doc']}/p{f['page']}" and n["type"]=="page"),{})
    if not (doc.get("sha256") and page.get("sha256") and
            a.get("decision")=="confirm" and a.get("fact")==f["id"] and c.get("format")=="field-source-v1" and
            c.get("doc")==f["doc"] and c.get("page")==f["page"] and c.get("original_sha256")==doc.get("sha256") and
            c.get("original_sha256")==f.get("source_sha256") and c.get("page_sha256")==page.get("sha256")==f.get("page_sha256") and
            c.get("rev")==a.get("rev") and type(c.get("rev")) is int and c["rev"]>0 and
            re.fullmatch(r"[0-9a-f]{64}",c.get("report_hash",""))):
        return False
    if c.get("operation")=="confirm":
        return True
    correction=f.get("amendment") or {}
    return (c.get("operation") in ("add","correct") and correction.get("source_check")==c and
            correction.get("target")==f["id"] and correction.get("field")==f["field"] and
            correction.get("value")==f["value"] and correction.get("quote")==f["quote"])


def word_signatures(ledger, graph, unit):
    """Separate the reading of a printed Word signing line from proof of execution."""
    pages = [p for p in ledger["pages"] if p["unit"] == unit]
    word = {d["id"] for d in graph["documents"] if d.get("ext") in (".doc", ".docx")}
    text_pages = {(p["doc"], p["page"]) for p in pages
                  if p["doc"] in word and p["native"] and p["text_only"]}
    if not text_pages:
        return None
    rows = [r for r in ledger.get("signing_rows", []) if r["unit"] == unit and r["role"] == "signature"
            and r["line"] is not None and (r["doc"], r["page"]) in text_pages]
    # A wholly typeset copy can have a blank, unlabelled or delegated signing block.
    if not rows and len(text_pages) != len(pages):
        return None
    facts = {f["id"]: f for f in graph["facts"] if f.get("unit", f["doc"]) == unit}
    readings = []
    for row in rows:
        ref = row["facts"][0] if len(row["facts"]) == 1 else None
        fact = facts.get(ref)
        receipt = None
        if not fact:
            state = "multiple" if row["facts"] else "unread"
        elif fact["status"] == "disputed":
            state = "disputed"
        elif fact["field"] != row["field"]:
            state = "field"
        elif (fact["quote"] == row["quote"] and fact["value"].strip() in (split(row["quote"])[1], row["quote"])
              and (fact.get("source_line") or {}).get("rects") and checked(fact, graph)):
            state, receipt = "checked", fact["attestation"]["rev"]
        else:
            state = "pending"
        readings.append({"row": row["id"], "state": state, "fact": ref, "receipt_rev": receipt})
    selected = {(r["doc"], r["page"]) for r in rows} or text_pages
    return {"unit": unit, "pages": [f"{doc}/p{page}" for doc, page in sorted(selected)], "rows": readings}


def review_word(finding, ledger, contract, graph):
    record = word_signatures(ledger, graph, contract.unit)
    if record is None:
        return
    finding["effect_review"]["word_signatures"] = record
    selected = {reading["row"] for reading in record["rows"]}
    refs = [ref for row in ledger["signing_rows"] if row["id"] in selected for ref in (row["id"], *row["facts"])]
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"], *record["pages"], *refs]))
    detail = "Word 原页仅见排印文字。请取得签署页或可对应本合同版本的电子签署记录，核实约定的签署条件。"
    if finding["status"] == "ok":
        finding.update(status="missing", detail=detail)
    else:
        finding["detail"] += " " + detail


def field_source(row, pages, facts, contract, graph):
    """Describe what supports this one reading, independently of coverage of the whole contract."""
    page = pages.get((row["doc"], row["page"]), {})
    layer = page.get("layer")
    if layer == "text" and row["line"] is not None:
        kind = "text" if page.get("clause_text_only") else "mixed"
    elif layer in ("image", "image_overlay") and row["line"] is None:
        kind = "image"
    else:
        kind = "unlocated"
    candidates = [facts[ref] for ref in row["facts"] if ref in facts]
    exact = [f for f in candidates if f["field"] == row["field"] and f["doc"] == row["doc"] and
             f["page"] == row["page"] and f.get("unit", f["doc"]) == row["unit"] and
             f["quote"] == row["quote"] and unicodedata.normalize("NFC", f["value"].strip()) in
             (unicodedata.normalize("NFC", row["quote"]), split(row["quote"])[1])]
    fact = exact[0] if len(exact) == 1 else None
    receipt_rev = None
    if fact and fact in contract.fields.get(row["field"], []) and checked(fact,graph):
        receipt_rev = fact["attestation"]["rev"]
    return {"row": row["id"], "kind": kind, "fact": fact["id"] if fact else None,
            "receipt_rev": receipt_rev, "disputed": any(f["status"] == "disputed" for f in exact)}


def usable(row, origin, contract, graph):
    if not row:
        return False
    if origin:
        if origin["kind"] == "unlocated" or origin["disputed"]:
            return False
        if origin["kind"] in ("image", "mixed"):
            return origin["receipt_rev"] is not None
    if row["role"] == "imprint":
        return row["line"] is not None
    fact = typed(row, contract)
    return checked(fact, graph) if row["role"] == "signature" else bool(fact)


def assess(ledger,contract,graph):
    rows=[r for r in ledger.get("signing_rows",[]) if r["unit"]==contract.unit]
    clean=bool(rows) and all(p["native"] and p["text_only"] for p in ledger["pages"] if p["unit"]==contract.unit)
    current = ledger.get("format") in IMAGE_FORMATS
    sources = {}
    if current and rows:
        physical = {f"{p['doc']}/p{p['page']}":(p["doc"],p["page"]) for p in ledger["pages"] if p["unit"]==contract.unit}
        pages = {physical[n["id"]]:n for n in graph["nodes"] if n["type"]=="page" and n["id"] in physical}
        facts = {f["id"]:f for f in contract.refs}
        sources = {r["id"]:field_source(r,pages,facts,contract,graph) for r in rows}
    records=[]
    for side in (*SIDES,"unspecified"):
        own=[r for r in rows if r["side"]==side]
        groups={role:[r for r in own if r["role"]==role] for role in ("party","signature","imprint")}
        single={role:items[0] for role,items in groups.items() if len(items)==1}
        names={role:split(r["quote"])[1] for role,r in single.items()}
        seal=SEAL.fullmatch(names.get("signature",""))
        holder=seal[1].strip() if seal else None
        party=names.get("party","")
        if not groups["imprint"] and not (party and holder and holder!=party and (complete(holder) or complete(party))):
            continue
        origins = {role:sources.get(r["id"]) for role,r in single.items()}
        def legible(role):
            return usable(single.get(role), origins.get(role), contract, graph)
        def awaiting_image(role):
            return (origins.get(role) or {}).get("kind") in ("image","mixed") and not legible(role)
        state,status,target="pending","missing",None
        if side=="unspecified":
            state="side"
        elif current and any(sources[r["id"]]["disputed"] for r in own):
            state="disputed"
        elif current and any(sources[r["id"]]["kind"]=="unlocated" for r in own):
            state="unlocated"
        elif any(len(items)>1 for items in groups.values()):
            repeated=[r for items in groups.values() if len(items)>1 for r in items]
            state="ambiguous" if current and any(sources[r["id"]]["kind"]!="text" and
                       not sources[r["id"]]["receipt_rev"] for r in repeated) else "multiple"
        elif not current and (not clean or any(r["line"] is None for r in own)):
            state="image"
        elif awaiting_image("party") or awaiting_image("imprint"):
            state="image_pending"
        elif not complete(party) or not legible("party"):
            state="party"
        elif "imprint" in single and not complete(names["imprint"]):
            state="partial"
        elif "imprint" in single and names["imprint"]!=party:
            state,status,target="different","risk","imprint"
        elif awaiting_image("signature"):
            state="image_pending"
        elif not holder or not complete(holder) or not legible("signature"):
            state="signature"
        elif holder!=party:
            state,status,target="different","risk","signature"
        elif "imprint" in single:
            state,status,target="match","ok","imprint"
        evidence=[]
        for r in own:
            evidence.extend([r["id"],f"{r['doc']}/p{r['page']}",*r["facts"]])
        record={"side":side,"state":state,"status":status,"unit":contract.unit,
                        "rows":{k:[r["id"] for r in rs] for k,rs in groups.items()},
                        "comparison":[single["party"]["id"],single[target]["id"]] if target else [],
                        "evidence":list(dict.fromkeys(evidence))}
        if current:
            record["field_sources"]=[sources[r["id"]] for r in own]
        records.append(record)
    return records


def comparisons(findings):
    return [{"type":"contract_seal_name_comparison","from":r["comparison"][0],"to":r["comparison"][1],
             "side":r["side"],"status":r["status"],"evidence":r["evidence"]}
            for f in findings if f["rule"]=="H01" for r in f.get("effect_review",{}).get("party_seals",[]) if r["comparison"]]


def review(finding,ledger,contract,graph):
    results=assess(ledger,contract,graph)
    if not results:
        return
    finding["effect_review"]["party_seals"]=results
    finding["evidence"]=list(dict.fromkeys([*finding["evidence"],*(ref for r in results for ref in r["evidence"])]))
    if finding["status"]=="ok" and any(r["status"]!="ok" for r in results):
        finding["detail"]="合同列明了签署及生效约定，签章主体仍待核实。"
    for r in results:
        side=SIDES.get(r["side"],"")
        if r["status"]=="risk":
            finding["status"]="risk"
            which="签章栏" if r["comparison"][1] in r["rows"]["signature"] else "印章单位名称栏"
            detail=side+which+"与约定主体的名称不一致，需核对用印单位、代表或代理权限。"
        elif r["status"]=="missing":
            if finding["status"]=="ok":
                finding["status"]="missing"
            detail=side+{"multiple":"名称或签章有多栏，需核对各栏用途及所据原件。","partial":"印章单位名称记载不完整，需核对清晰原件。",
                         "side":"另有未注明甲乙方的印章单位名称，归属待核。","image":"签章主体所据原页含影像，需核对整页。",
                         "image_pending":"签章影像的名称栏需要核对原页并记录相应字段。","disputed":"签章栏位有已登记的异议，需核对原文。",
                         "ambiguous":"同一签章栏有多条候选记录，需核对其在原页的位置和实际记载。",
                         "unlocated":"签章候选文字尚未定位至对应原行，需核对原页。",
                         "party":"合同约定主体名称及其出处待核。","signature":"签章栏的完整名称和核图记录待核。"}.get(r["state"],"签章主体待核。")
        elif any(s["kind"] in ("image","mixed") for s in r.get("field_sources",[])):
            detail=side+"所核三栏的单位名称相符，影像页的其他约定仍须通读。"
        else:
            detail=side+"约定主体、核图签章栏与单列印章单位名称相符。"
        finding["detail"]+=" "+detail
