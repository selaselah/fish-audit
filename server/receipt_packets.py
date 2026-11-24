"""Bind independent acceptance forms to their physical pages before evaluating performance."""

import hashlib
import re
from collections import Counter, defaultdict
from unicodedata import normalize

from acceptance_authority import TITLES, covers, parts
from delivery_batches import receipt_numbers


LEGACY = "numbered-acceptance-pages-v1"
FORMAT = "numbered-acceptance-pages-v2"
SINCE = "2026.11.25.10"
DISTINCT_RETEST = "2026.11.25.11"
LABELS = {"acceptance_number":("验收单编号","验收报告编号"), "contract_id":("合同编号","合同号"),
          "acceptance_scope":("验收范围","验收批次","验收阶段"), "accepted_on":("验收日期","验收时间")}
NAMES = {"acceptance":"验收标题","acceptance_number":"本单编号","contract_id":"合同编号",
         "acceptance_scope":"验收范围","accepted_on":"验收日期"}
CONTINUATION = re.compile(r"续页|续表|承前页|接上页|转下页|见下页|接续前|附页|另附签字页|第\s*\d+\s*页.{0,6}共\s*(?:[2-9]|\d{2,})\s*页")
PARTIAL = re.compile(r"(?:单号|编号).{0,15}(?:隐去|遮盖|省略|末[几一二三四五六七八九十\d]+位|尾号|后[几一二三四五六七八九十\d]+位)")


def native_value(raw):
    return normalize("NFKC",raw).strip()


def inspect_page(doc, number, node, text, facts, kinds, version):
    proofs = defaultdict(list)
    for line, raw in enumerate(text.splitlines(), 1):
        label, body = parts(raw)
        field = next((k for k,names in LABELS.items() if label in names), None)
        if native_value(raw) in TITLES["acceptance"]:
            field = "acceptance"
        elif CONTINUATION.search(native_value(raw)):
            field = "continuation"
        elif PARTIAL.search(native_value(raw)):
            field = "partial_number"
        if not field:
            continue
        matched = []
        for fact in facts:
            source = fact.get("source_line") or {}
            if (fact["field"]!=field or fact["status"] not in ("anchored","confirmed") or
                    source.get("number")!=line or source.get("text")!=raw or not source.get("rects") or
                    native_value(fact["quote"])!=native_value(raw) or not covers(field,fact["value"],raw)):
                continue
            if field=="acceptance" and min(rect[1] for rect in source["rects"])>=.36:
                continue
            if native_value(fact["value"]) not in (native_value(raw),body):
                continue
            matched.append(fact["id"])
        proofs[field].append({"doc":doc,"page":number,"line":line,"quote":raw,"facts":matched})
    native = node.get("layer")=="text" and node.get("clause_text_only") is True
    title = proofs["acceptance"]
    own = proofs["acceptance_number"]
    another = any(f["field"] in kinds-{"acceptance"} and f["status"] in ("anchored","confirmed")
                  and (f.get("source_line") or {}).get("rects") for f in facts)
    observed = any(f["field"]=="acceptance" for f in facts)
    for fact in facts:
        if fact["field"]!="acceptance_number":
            continue
        label,_ = parts(fact["quote"])
        if (version==LEGACY or label in LABELS["acceptance_number"] or not another and
                label not in ("复验单编号","复验报告编号","原验收单编号","所附批次验收单号")):
            observed = True
    number_text = parts(own[0]["quote"])[1] if len(own)==1 else ""
    errors = []
    if not native:
        errors.append("需通读原页影像及批注")
    if proofs["continuation"]:
        errors.append("页内标有续页或跨页说明")
    if proofs["partial_number"]:
        errors.append("原页说明单号有遮盖或仅列部分字符")
    if another and (observed or title or own):
        errors.append("页内另有其他单据标题")
    for field,label in NAMES.items():
        rows = proofs[field]
        if len(rows)!=1 or len(rows[0]["facts"])!=1:
            errors.append(label+"缺少唯一可定位的原行")
    if len(own)==1 and receipt_numbers(number_text)!=[number_text]:
        errors.append("本单编号不完整或字符间隔待核")
    return {"doc":doc,"page":number,"text_only":native,"number":number_text or None,
            "rows":[{"field":field,**row} for field,rows in proofs.items() for row in rows],
            "reasons":errors}, bool(observed or title or own), another, max(len(title),len(own))


def sources(graph, read_text, version=FORMAT):
    by_doc, by_page = defaultdict(dict), defaultdict(list)
    partial = {(g["doc"],g["page"]) for g in graph["gaps"] if g["quality"] in ("partial","unreadable")}
    other_hints = {(g["doc"],g["page"]) for g in graph["gaps"] if g.get("title_hint") not in (None,"acceptance")}
    for node in graph["nodes"]:
        if node["type"]=="page":
            doc, n = node["id"].rsplit("/p",1)
            by_doc[doc][int(n)] = node
    for fact in graph["facts"]:
        by_page[fact["doc"],fact["page"]].append(fact)
    kinds = set(graph["documents_by_kind"])
    packets = []
    for source in graph["documents"]:
        doc = source["id"]
        if source.get("ext",".pdf")!=".pdf":
            continue
        entries,starts,multiple = [],0,False
        for n,node in sorted(by_doc[doc].items()):
            text = read_text(doc,n) if node.get("layer")=="text" else ""
            if node.get("layer")=="text" and node.get("text_sha256") and hashlib.sha256(text.encode()).hexdigest()!=node["text_sha256"]:
                raise ValueError("合订验收原页文字与归档摘要不符")
            page,signal,other,count = inspect_page(doc,n,node,text,by_page[doc,n],kinds,version)
            if (doc,n) in partial:
                page["reasons"].append("原页辨读记录尚有缺口")
            if (doc,n) in other_hints:
                page["reasons"].append("另有尚未归属的单据标题")
            if signal or not other:
                entries.append(page)
            starts += int(signal)
            multiple |= count>1
        if not (multiple or starts and len(entries)>1):
            continue
        numbers = Counter(p["number"].casefold() for p in entries if p["number"])
        for p in entries:
            if p["number"] and numbers[p["number"].casefold()]>1:
                p["reasons"].append("本单编号在合订件内重复")
        status = "review" if any(p["reasons"] for p in entries) else "split"
        packets.append({"doc":doc,"status":status,"pages":entries})
    return {"format":version,"packets":packets}


def gaps(source):
    return [{"doc":p["doc"],"page":p["page"],"id":f"{p['doc']}/p{p['page']}",
             "quality":"receipt_packet","field":"acceptance","detail":"；".join(p["reasons"])}
            for packet in source["packets"] for p in packet["pages"] if p["reasons"]]


def edges(source):
    return [{"from":f"unit/{p['doc']}/p{p['page']}","to":row["facts"][0],"type":"acceptance_page_identity",
             "evidence":[f"{p['doc']}/p{p['page']}",row["facts"][0]]}
            for packet in source["packets"] if packet["status"]=="split" for p in packet["pages"]
            for row in p["rows"] if row["field"] in ("acceptance","acceptance_number")]


def verify_sources(report,read_text,*,signing=False):
    graph, policy = report["graph"],report["policy"]
    marker = policy.get("receipt_packets")
    saved = graph.get("receipt_packet_sources")
    if marker is None:
        if saved is not None or policy.get("version","")>=SINCE or "receipt_packets.py" in policy.get("code_sha256",{}):
            raise ValueError("验收合订件缺少原页归属程序")
        if signing and any(f["rule"]=="H02" and f["status"]=="ok" for f in report["findings"]) and sources(graph,read_text)["packets"]:
            raise ValueError("旧版验收结论涉及多页验收资料，请按现行程序重审后签收。")
        return
    required = FORMAT if policy.get("version","")>=DISTINCT_RETEST else LEGACY
    expected = sources(graph,read_text,required)
    if (policy.get("version","")<SINCE or marker!=required or saved!=expected or
            [g for g in graph["gaps"] if g["quality"]=="receipt_packet"]!=gaps(expected) or
            [e for e in graph["edges"] if e["type"]=="acceptance_page_identity"]!=edges(expected)):
        raise ValueError("验收单边界、原页编号或引文关系与归档不符")
    for packet in expected["packets"]:
        for page in packet["pages"]:
            doc,n = page["doc"],page["page"]
            page_id = f"{doc}/p{n}"
            unit = f"unit/{doc}/p{n}"
            sections = [d for d in graph.get("audit_documents",[]) if d.get("source")==doc and d.get("page")==n]
            if packet["status"]=="split" and (len(sections)!=1 or graph["documents_by_kind"].get("acceptance",[]).count(unit)!=1):
                raise ValueError("独立验收单未按原页唯一归属")
            owner = unit if sections else doc
            if sections and ([s["id"] for s in sections]!=[unit] or
                    {"from":unit,"to":page_id,"type":"section_page","evidence":[page_id]} not in graph["edges"]):
                raise ValueError("验收单的单据与原件分页关系不符")
            facts = {f["id"]:f for f in graph["facts"] if (f["doc"],f["page"])==(doc,n)}
            if (any(f.get("unit",doc)!=owner for f in facts.values()) or
                any(e["from"]!=owner for e in graph["edges"] if e["evidence"] and e["evidence"][0] in facts
                    and e["type"]==facts[e["evidence"][0]]["field"])):
                raise ValueError("验收单的字段与所在原页归属不符")
