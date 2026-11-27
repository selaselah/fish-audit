"""Retain both reviewed observations when a corrected party name and a supplement cite one printed line."""
from collections import defaultdict
from hashlib import sha256
import re

from delegation import is_page_marker
from payment_acceptance import column


KEY = "reviewed_party_lines"
FORMAT = "reviewed-party-line-v1"
SINCE = (2026,11,27,22)
KINDS = {"contract","acceptance","remediation","reinspection"}
ROLES = {"buyer","seller"}
EDGES = {"locates_party_reading","compares_party_readings","shares_party_line"}


def checked(fact, operation, doc, page):
    edit, decision = fact.get("amendment") or {}, fact.get("attestation") or {}
    receipt = edit.get("source_check") or {}
    confirmed = decision.get("source_check") or {}
    address = (doc["id"],1,doc["sha256"],page["sha256"])
    if (fact["status"]!="confirmed" or edit.get("target")!=fact["id"] or decision.get("fact")!=fact["id"]
            or decision.get("decision")!="confirm" or receipt.get("operation")!=operation or
            confirmed.get("operation") not in (operation,"confirm") or
            any(edit.get(k)!=fact[k] for k in ("field","value","quote","page","doc"))):
        return False
    for source, action in ((receipt,edit),(confirmed,decision)):
        if (source.get("format")!="field-source-v1" or not re.fullmatch(r"[a-f0-9]{32}",str(source.get("case_id","")))
                or not re.fullmatch(r"[a-f0-9]{64}",str(source.get("report_hash",""))) or type(source.get("rev")) is not int
                or source["rev"]<1 or source["rev"]!=action.get("rev")
                or tuple(source.get(k) for k in ("doc","page","original_sha256","page_sha256"))!=address):
            return False
    return (receipt["case_id"]==confirmed["case_id"] and receipt["rev"]<=confirmed["rev"]
            and (confirmed["operation"]=="confirm" or confirmed==receipt))


def record(model, added, names, doc, page, rows, role_labels):
    loc = added.get("source_line") or {}
    line = loc.get("number")
    if (not checked(added,"add",doc,page) or added.get("original_candidate") or not loc.get("rects")
            or type(line) is not int or not 1<=line<=len(rows) or rows[line-1]!=added["quote"] or loc["text"]!=added["quote"]):
        return None
    label, value = column(loc["text"])
    if (label not in role_labels or value!=added["value"] or value!=model["value"] or not value
            or re.search(r"[*×□…/、；;：:]|待定|不详|同上|另见|同(?:主)?合同",value)
            or sum(column(raw)[0] in role_labels for raw in rows)!=1):
        return None
    original = model.get("original_candidate") if model.get("amendment") else model
    if not original or original.get("field")!=added["field"] or original.get("value")!=value:
        return None
    old_label, old_value = column(original["quote"])
    if old_value!=value or "".join(old_label.split()) not in role_labels:
        return None
    if model.get("amendment"):
        if (not checked(model,"correct",doc,page) or model["quote"]!=loc["text"] or model.get("source_line")!=loc
                or model["amendment"]["source_check"]["case_id"]!=added["amendment"]["source_check"]["case_id"]):
            return None
        outcome = "same_line"
    else:
        if model["status"]!="visual" or model.get("source_line") or model.get("attestation") or original["quote"]==loc["text"]:
            return None
        outcome = "pending"
    observed = {f["id"] for f in names if (f.get("source_line") or {}).get("number")==line}
    if observed!=({model["id"],added["id"]} if outcome=="same_line" else {added["id"]}):
        return None
    return {"id":f"party-line/{doc['id']}/p1/l{line}", "doc":doc["id"], "unit":doc["id"], "page":1, "line":line,
            "state":outcome, "field":added["field"], "value":value, "quote":loc["text"], "model_quote":original["quote"],
            "model_ref":model["id"], "added_ref":added["id"], "rects":loc["rects"],
            "original_sha256":doc["sha256"], "page_sha256":page["sha256"]}


def sources(graph, read_text, read_layout=None):
    from graph import LABELS, PRINTED_TITLES, entity_id

    pages = graph.get("payment_window_sources",{}).get("pages",[])
    by_doc = defaultdict(list)
    for fact in graph["facts"]:
        by_doc[fact["doc"]].append(fact)
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    docs = {d["id"]:d for d in graph["documents"]}
    found = []
    for place in pages:
        unit = place["doc"]
        doc = docs[unit]
        if (place["document_kind"] not in KINDS or unit!=place["unit"] or place["page"]!=1 or doc.get("pages")!=1
                or doc.get("ext")!=".pdf" or not place["native"] or not place["text_only"]
                or any(g["doc"]==unit for g in graph.get("gaps",()))):
            continue
        page = nodes[unit+"/p1"]
        if not all(re.fullmatch(r"[a-f0-9]{64}",str(source.get("sha256",""))) for source in (doc,page)):
            continue
        names = by_doc[unit]
        for role in sorted(ROLES):
            facts = [f for f in names if f["field"]==role]
            if len(facts)!=2:
                continue
            model, added = sorted(facts,key=lambda f:f["id"])
            if (not re.fullmatch(unit+r"/p1/f[1-9]\d*",model["id"]) or not re.fullmatch(unit+r"/p1/h[a-f0-9]{12}",added["id"])
                    or any(f["page"]!=1 or f.get("unit",unit)!=unit or f["source_sha256"]!=doc["sha256"]
                           or f["page_sha256"]!=page["sha256"] for f in facts)):
                continue
            text = read_text(unit,1)
            if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=page.get("text_sha256"):
                raise ValueError("主体核字所据原页文字与底稿摘要不符")
            lines = text.splitlines()
            headings = [PRINTED_TITLES[raw.strip()] for raw in lines if raw.strip() in PRINTED_TITLES]
            first = next((raw.strip() for raw in lines if raw.strip() and not is_page_marker(raw)),"")
            if headings!=[place["document_kind"]] or PRINTED_TITLES.get(first)!=place["document_kind"]:
                continue
            pair = record(model,added,names,doc,page,lines,LABELS[role])
            if pair:
                target = entity_id("party",pair["value"])
                for fact in facts:
                    links = [e for e in graph["edges"] if e["evidence"]==[fact["id"]] and e["type"] in ("records",role)]
                    needed = [(unit+"/p1","records",fact["id"])]
                    if fact["status"]=="confirmed":
                        needed.append((unit,role,target))
                    if [(e["from"],e["type"],e["to"]) for e in links]!=needed:
                        raise ValueError("主体观察与所属原页、主体名称的图关系不符")
                if read_layout and read_layout(unit,1).get("lines",{}).get(str(pair["line"]))!=pair["rects"]:
                    raise ValueError("主体核字所据原行与留存行框不符")
                found.append(pair)
    return found


def source_graph(rows):
    nodes, edges = [], []
    for row in rows:
        pid, rid, original, added = row["doc"]+"/p1",row["id"],row["model_ref"],row["added_ref"]
        nodes.append({"id":rid,"type":"party_reading_line","label":row["quote"],"state":row["state"],
                      "doc":row["doc"],"page":1,"line":row["line"]})
        edges.append({"from":pid,"to":rid,"type":"locates_party_reading","evidence":[pid,added]})
        edges.append({"from":original,"to":added,"type":"shares_party_line" if row["state"]=="same_line" else "compares_party_readings",
                      "evidence":[original,rid,added]})
    return nodes,edges


def attach(graph, findings):
    rows = graph.get(KEY,{}).get("rows",())
    for finding in findings:
        used = [r for r in rows if r["unit"] in finding["scope"] and
                (r["model_ref"] in finding["evidence"] or r["added_ref"] in finding["evidence"])]
        if used:
            finding["party_readings"] = [r["id"] for r in used]
            refs = (ref for r in used for ref in (r["id"],r["doc"]+"/p1",r["model_ref"],r["added_ref"]))
            finding["evidence"] = list(dict.fromkeys([*finding["evidence"],*refs]))


def verify_originals(report, read_original):
    from payment_quality import verify_units

    g = report["graph"]
    rows = g.get(KEY,{}).get("rows",[])
    if rows:
        verify_units(g,{r["unit"] for r in rows},read_original,"主体核字",extra_lines=rows)


def verify(report, read_text, *, read_layout=None, signing=False):
    g,p,fs = report["graph"],report["policy"],report["findings"]
    revision = tuple(map(int,p.get("version","0").split(".")))
    module = "party_readings.py" in p.get("code_sha256",{})
    if "code_sha256" in p and module!=(revision>=SINCE):
        raise ValueError("主体核字方法与底稿版本不符")
    nodes = [n for n in g["nodes"] if n["type"]=="party_reading_line"]
    edges = [e for e in g["edges"] if e["type"] in EDGES]
    claims = [f for f in fs if "party_readings" in f]
    if revision<SINCE:
        if KEY in g or p.get("party_readings") or nodes or edges or claims:
            raise ValueError("历史底稿含未出具的主体核字依据")
        if signing:
            guard_legacy(report,read_text,read_layout)
        return
    rows = sources(g,read_text,read_layout)
    ledger = {"format":FORMAT,"rows":rows} if rows else None
    if (g.get(KEY)!=ledger or p.get("party_readings")!=(FORMAT if rows else None) or (nodes,edges)!=source_graph(rows)):
        raise ValueError("主体核字的原件、字段或同一原行的图关系不符")
    if not rows and not claims:
        return
    calls = {(c["doc"],c["page"]):c for c in report["calls"]["pages"]}
    facts = {f["id"]:f for f in g["facts"]}
    for row in rows:
        model, added = facts[row["model_ref"]],facts[row["added_ref"]]
        call = calls[row["doc"],1]
        entries = call["output"]["facts"]
        index = int(model["id"].rsplit("/f",1)[1])-1
        candidate = entries[index] if 0<=index<len(entries) else {}
        if (not call.get("response_id") or call["response_id"]!=model["response_id"] or call["page_sha256"]!=row["page_sha256"]
                or not call.get("check",{}).get("response_id") or call["check"]["response_id"]!=model.get("check_response_id")
                or candidate.get("field")!=row["field"] or candidate.get("quote")!=row["model_quote"] or candidate.get("value")!=row["value"]
                or added["amendment"]["source_check"]["case_id"]!=report["case_id"]):
            raise ValueError("主体核字与原模型读数、独立复读或本案核图记录不符")
    support = {(e["from"],e["to"]) for e in g["edges"] if e["type"]=="supports_result" and e["evidence"]==[e["from"]]}
    for f in fs:
        used = [r for r in rows if f["rule"].startswith("H") and r["unit"] in f["scope"] and
                (r["model_ref"] in f["evidence"] or r["added_ref"] in f["evidence"])]
        if f.get("party_readings")!=([r["id"] for r in used] or None) or any(
                ref not in f["evidence"] or (ref,"finding/"+f["id"]) not in support for r in used
                for ref in (r["id"],r["model_ref"],r["added_ref"],r["doc"]+"/p1")):
            raise ValueError("履约发现所引的主体核字或两条读数缺失")


def guard_legacy(report, read_text, read_layout):
    from performance import FORMAT as PERFORMANCE_FORMAT, compute
    import inspection_use

    g,p = report["graph"],report["policy"]
    if p.get("performance_checks")!=PERFORMANCE_FORMAT or not any(f.get("amendment") and f["field"] in ROLES for f in g["facts"]):
        return
    rows = sources(g,read_text,read_layout)
    if not any(r["state"]=="same_line" for r in rows):
        return
    current = {**g,KEY:{"format":FORMAT,"rows":rows}}
    if read_layout:
        current[inspection_use.KEY]=inspection_use.sources(g,read_text,read_layout)
    def grounds(findings):
        for finding in findings:
            if finding["status"]!="risk":
                continue
            identity = (finding["rule"],tuple(sorted(finding["scope"])),finding.get("stage",{}).get("clause_ref"))
            yield (*identity,"risk")
            for name in ("payment_quality","retest_reference","inspection_use","payment_acceptance","approval"):
                parent = finding.get("inspection_use",{}) if name=="approval" else finding
                proof = parent.get(name,{})
                if proof.get("status")=="risk":
                    yield (*identity,name,proof.get("state"))
    new = [f for f in compute(current) if f.get("party_readings")]
    if set(grounds(new))-set(grounds(report["findings"])):
        raise ValueError("旧版的两条主体读数实际对应同一原行，重新核对出现新的履约或实付风险，请重审后签收")
