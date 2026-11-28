"""Trace a bank account-holder row classified as a different party by the original reader."""

import re
from collections import defaultdict
from hashlib import sha256

from advance_guarantee import legible_name, rectangles
from party_readings import checked, matches_model_reads
from stage_payments import BANK_TITLES, LABELS, literal


KEY = "bank_party_readings"
FORMAT = "printed-bank-party-roles-v1"
SINCE = (2026, 11, 28, 24)
ROLE_NAMES = {"buyer":"采购方", "seller":"供应方", "payer":"付款户名", "payee":"收款户名"}
HEADINGS = {label:role for role in ("payer","payee") for label in LABELS[role]}
EDGES = {"locates_bank_party_reading", "compares_bank_party_role"}


def sources(graph, read_text, calls, read_layout=None):
    from graph import PRINTED_TITLES

    nodes = {n["id"]:n for n in graph["nodes"]}
    files = {d["id"]:d for d in graph["documents"]}
    by_unit = defaultdict(list)
    for fact in graph["facts"]:
        by_unit[fact.get("unit",fact["doc"])].append(fact)
    output = []
    for place in graph.get("payment_window_sources",{}).get("pages",[]):
        if place["document_kind"]!="bank_receipt" or not place["native"] or not place["text_only"]:
            continue
        unit, doc, page = place["unit"],place["doc"],place["page"]
        facts = by_unit[unit]
        titles = [f for f in facts if f["field"]=="bank_receipt"]
        if len(titles)!=1 or (titles[0]["doc"],titles[0]["page"])!=(doc,page) or unit not in graph["documents_by_kind"].get("bank_receipt",[]):
            continue
        page_id = f"{doc}/p{page}"
        file, node = files[doc], nodes[page_id]
        call = calls.get((doc,page)) or {}
        if node.get("layer")!="text" or not call.get("response_id"):
            continue
        for f in facts:
            original = f.get("original_candidate") or f
            label, separator, value = literal(original["quote"]).partition(":")
            role, model_role = HEADINGS.get(label.strip()), original["field"]
            if (not separator or not role or model_role not in ROLE_NAMES or role==model_role or
                    (f["doc"],f["page"])!=(doc,page) or not re.fullmatch(re.escape(page_id)+r"/f[1-9]\d*",f["id"])):
                continue
            name = value.strip()
            loc = f.get("source_line") or {}
            line, quote = loc.get("number"), loc.get("text")
            if (not legible_name(name) or literal(original["value"]) not in (name,literal(original["quote"])) or
                    not quote or original["quote"]!=quote or f["quote"]!=quote or not rectangles(loc.get("rects")) or
                    type(line) is not int or line<1 or f.get("source_sha256")!=file["sha256"] or f.get("page_sha256")!=node["sha256"]):
                continue
            # Multiple candidates on this very line require reconciliation before proposing an edit.
            if any(x["id"]!=f["id"] and (x["doc"],x["page"],(x.get("source_line") or {}).get("number"))==
                   (doc,page,line) for x in facts):
                continue
            records = [e for e in graph["edges"] if e["type"]=="records" and e["to"]==f["id"]]
            if (records!=[{"from":page_id,"to":f["id"],"type":"records","evidence":[f["id"]]}] or
                    nodes.get(doc,{}).get("sha256")!=file["sha256"] or nodes.get(f["id"],{}).get("status")!=f["status"]):
                raise ValueError("回单主体字段与所属原页或核图状态不符")
            if f.get("amendment"):
                if f["field"]!=role or literal(f["value"]) not in (name,literal(quote)) or not checked(f,"correct",file,node):
                    continue
                state = "corrected"
            else:
                if not any(g.get("field")==role and g["id"]==page_id and g.get("line")==line and
                           g.get("quote")==quote for g in graph["gaps"]):
                    continue
                state = "pending"
            text = read_text(doc,page)
            if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=node["text_sha256"]:
                raise ValueError("回单户名所据页文字与归档摘要不符")
            lines = text.splitlines()
            headings = [raw.strip() for raw in lines if raw.strip() in PRINTED_TITLES]
            if (line>len(lines) or lines[line-1]!=quote or len(headings)!=1 or headings[0] not in BANK_TITLES or
                    sum(HEADINGS.get(literal(raw).partition(":")[0].strip())==role for raw in lines)!=1):
                continue
            comparison = {"field":model_role,"value":original["value"],"model_quote":original["quote"]}
            if not matches_model_reads({**f,"label":ROLE_NAMES[model_role]},comparison,call):
                continue
            if read_layout and read_layout(doc,page).get("lines",{}).get(str(line))!=loc["rects"]:
                raise ValueError("回单户名所引原行框与版面不符")
            output.append({"id":f"bank-party/{doc}/p{page}/l{line}","unit":unit,"doc":doc,"page":page,"line":line,
                           "title_ref":titles[0]["id"],"fact":f["id"],"model_role":model_role,"printed_role":role,
                           "state":state,"value":name,"quote":quote,"rects":loc["rects"],
                           "original_sha256":file["sha256"],"page_sha256":node["sha256"]})
    return output


def source_graph(rows):
    nodes, edges = [], []
    for row in rows:
        ref, fact = row["id"],row["fact"]
        pid = f"{row['doc']}/p{row['page']}"
        nodes.append({"id":ref,"type":"bank_party_reading","label":row["quote"],"state":row["state"]})
        edges.extend([{"from":pid,"to":ref,"type":"locates_bank_party_reading","evidence":[pid,fact]},
                      {"from":fact,"to":ref,"type":"compares_bank_party_role","evidence":[fact]}])
    return nodes,edges


def cited(finding, rows):
    if finding["rule"]!="H05":
        return []
    return [r for r in rows if r["unit"] in finding["scope"] and r["title_ref"] in finding["evidence"]]


def references(row):
    return (row["id"],row["fact"],f"{row['doc']}/p{row['page']}")


def attach(graph, findings):
    rows = graph.get(KEY,{}).get("rows",[])
    for finding in findings:
        used = cited(finding,rows)
        if not used:
            continue
        finding[KEY] = [r["id"] for r in used]
        finding["evidence"] = list(dict.fromkeys([*finding["evidence"],*(ref for r in used for ref in references(r))]))
        for r in used:
            expected, observed = ROLE_NAMES[r["printed_role"]],ROLE_NAMES[r["model_role"]]
            if r["state"]=="pending":
                finding["detail"] += f" 回单第 {r['page']} 页第 {r['line']} 行列示{expected}，模型归为{observed}，请据原件核对字段类别。"
            else:
                finding["detail"] += f" 回单第 {r['page']} 页第 {r['line']} 行已由核图人员从{observed}更正为{expected}。"


def verify_originals(paper, read_original):
    from payment_quality import verify_units

    rows = paper["graph"].get(KEY,{}).get("rows",[])
    if rows:
        verify_units(paper["graph"],{r["unit"] for r in rows},read_original,"银行回单主体栏",extra_lines=rows)


def verify(paper, read_text, read_layout=None):
    graph, policy = paper["graph"],paper["policy"]
    nodes = [n for n in graph["nodes"] if n["type"]=="bank_party_reading"]
    edges = [e for e in graph["edges"] if e["type"] in EDGES]
    claims = any(KEY in f for f in paper["findings"])
    if tuple(map(int,(policy.get("version") or "0").split(".")))<SINCE:
        if KEY in policy or KEY in graph or nodes or edges or claims:
            raise ValueError("旧版底稿出现未出具的回单主体分类依据")
        return
    calls = {(p["doc"],p["page"]):p for p in paper.get("calls",{}).get("pages",[])}
    rows = sources(graph,read_text,calls,read_layout)
    if (graph.get(KEY)!=({"format":FORMAT,"rows":rows} if rows else None) or (nodes,edges)!=source_graph(rows)
            or policy.get(KEY)!=(FORMAT if rows else None)):
        raise ValueError("回单主体分类与原行、模型或图谱不符")
    if not (rows or claims):
        return
    if "code_sha256" in policy and "receipt_parties.py" not in policy["code_sha256"]:
        raise ValueError("回单主体分类程序缺少归档源码")
    expert = paper.get("calls",{}).get("expert") or {}
    procedure_rows = expert.get("input",{}).get("procedures",[])
    supports = {(e["from"],e["to"]) for e in graph["edges"] if e["type"]=="supports_result" and e["evidence"]==[e["from"]]}
    facts = {f["id"]:f for f in graph["facts"]}
    for r in rows:
        if calls[r["doc"],r["page"]].get("page_sha256")!=r["page_sha256"] or (r["state"]=="corrected" and
                facts[r["fact"]]["amendment"]["source_check"]["case_id"]!=paper["case_id"]):
            raise ValueError("回单主体分类与本案原页或更正记录不符")
    for f in paper["findings"]:
        used = cited(f,rows)
        if f.get(KEY)!=([r["id"] for r in used] or None) or any(ref not in f["evidence"] or
                (ref,"finding/"+f["id"]) not in supports for r in used for ref in references(r)):
            raise ValueError("实付检查未引用本笔回单所据的主体原行和模型分类")
        if used and (not expert.get("response_id") or not any(p.get("rule")==f["rule"] and p.get("evidence")==f["evidence"] and
                p.get("status")==f["status"] and p.get("observation")==f["detail"] and p.get("stage")==f.get("stage") and
                p.get(KEY)==used for p in procedure_rows)):
            raise ValueError("专家程序与实付所引的回单主体分类不符")
