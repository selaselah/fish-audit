"""Read Word review comments separately from the printed acceptance report."""

from collections import Counter, defaultdict
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import posixpath
import re
from unicodedata import normalize
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

FORMAT = "word-acceptance-comments-v1"
SINCE = "2026.11.26.17"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
COMMENTS_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
TRACKED = {W + name for name in ("ins", "del", "moveFrom", "moveTo", "moveFromRangeStart", "moveToRangeStart",
                                 "rPrChange", "pPrChange", "tblPrChange", "trPrChange", "tcPrChange", "sectPrChange")}
CAP = 64
LIMIT = 1024
# A complete affirmative reservation, without quotation, withdrawal or approval of final inspection.
QUANTITY_ONLY = re.compile(
    r"(?:本次|本栏)?(?:仅|只)(?:核对|确认|查验|清点)(?:到货|实收)?(?:数量|件数)"
    r"[,;。](?:制冷性能|整机性能|性能|功能|质量)(?:须|需|应)(?:由技术部|由质量部)?另行(?:终验|验收|检验)[。.]?"
)
RESULT_LINES = {label + sep + "合格" for label in ("验收结论", "验收结果", "复验结论", "复验结果") for sep in ("：", ":")}


def digest(raw):
    return sha256(raw).hexdigest()


def xml_part(package, path, limit):
    if package.getinfo(path).file_size > limit:
        raise ValueError("审阅部件超出核查范围")
    data = package.read(path)
    return data, ET.fromstring(data)


def anchors(body):
    points = defaultdict(lambda: defaultdict(list))
    texts = []
    tags = {W+"commentRangeStart": "start", W+"commentRangeEnd": "end", W+"commentReference": "reference"}
    totals = Counter((tags[node.tag], node.get(W+"id")) for node in body.iter() if node.tag in tags)
    for number, paragraph in enumerate(body.iter(W+"p"), 1):
        text = []
        offset = 0
        simple = True
        for item in paragraph:
            if item.tag == W+"pPr":
                continue
            if item.tag in tags:
                points[item.get(W+"id")][tags[item.tag]].append((number, offset))
            elif item.tag == W+"r":
                for child in item:
                    if child.tag == W+"t":
                        part = child.text or ""
                        text.append(part)
                        offset += len(part)
                    elif child.tag == W+"commentReference":
                        points[child.get(W+"id")]["reference"].append((number, offset))
                    elif child.tag != W+"rPr":
                        simple = False
            else:
                simple = False
        texts.append("".join(text) if simple else None)
    counts = Counter(texts)
    result = {}
    for key, positions in points.items():
        if any(totals[k, key] != 1 or len(positions[k]) != 1 for k in ("start","end","reference")):
            continue
        (number, start), = positions["start"]
        (last, end), = positions["end"]
        ref, = positions["reference"]
        text = texts[number-1]
        if (text and number == last == ref[0] and ref[1] >= end and 0 <= start < end <= len(text) <= LIMIT
                and counts[text] == 1):
            result[key] = {"paragraph": number, "quote": text, "start": start, "end": end, "selected": text[start:end]}
    return result, {key for _, key in totals}


def comment_text(comment):
    paragraphs = []
    allowed = {W+n for n in ("p", "pPr", "r", "rPr", "t", "tab", "br", "cr", "annotationRef")}
    simple = True
    for paragraph in comment.iter(W+"p"):
        pieces = []
        for run in paragraph:
            if run.tag == W+"pPr":
                continue
            if run.tag != W+"r":
                simple = False
            for node in run.iter():
                if node.tag == W+"t":
                    pieces.append(node.text or "")
                elif node.tag == W+"tab":
                    pieces.append("\t")
                elif node.tag in (W+"br",W+"cr"):
                    pieces.append("\n")
            if run.tag == W+"r" and any(node.tag not in allowed for node in run):
                simple = False
        paragraphs.append("".join(pieces))
    if any(node.tag != W+"p" for node in comment):
        simple = False
    return "\n".join(paragraphs), simple


def package_review(raw):
    with ZipFile(BytesIO(raw)) as package:
        members = package.infolist()
        names = set(package.namelist())
        if len(names) != len(members) or len(names)>2000 or sum(m.file_size for m in members)>80*1024**2:
            raise ValueError("Word 审阅包超出支持范围")
        _, types = xml_part(package, "[Content_Types].xml", 512*1024)
        _, root_rels = xml_part(package, "_rels/.rels", 512*1024)
        if types.tag != CT + "Types" or root_rels.tag != PKG + "Relationships":
            raise ValueError("Word 部件目录待核")
        mains = [r for r in root_rels.findall(PKG+"Relationship") if r.get("Type")==REL+"officeDocument"]
        if len(mains)!=1 or mains[0].get("Target","").lstrip("/")!="word/document.xml" or mains[0].get("TargetMode","Internal")!="Internal":
            raise ValueError("Word 主文档无法定位")
        body_bytes, body = xml_part(package,"word/document.xml",8*1024**2)
        if body.tag!=W+"document" or body.find(W+"body") is None:
            raise ValueError("Word 正文格式待核")
        located, references = anchors(body)
        limitations = []
        if any(node.tag in TRACKED for node in body.iter()):
            limitations.append("tracked")
        parts = {n.get("PartName","").lstrip("/"):n.get("ContentType","") for n in types.findall(CT+"Override")}
        declared = {path for path, mime in parts.items() if mime == COMMENTS_TYPE}
        if any("comment" in mime.lower() and mime!=COMMENTS_TYPE for mime in parts.values()):
            limitations.append("extended")
        rel_path = "word/_rels/document.xml.rels"
        links = []
        if rel_path in names:
            _, rels = xml_part(package, rel_path, 1024*1024)
            if rels.tag != PKG + "Relationships":
                raise ValueError("Word 正文关联目录待核")
            links = [r for r in rels.findall(PKG+"Relationship") if r.get("Type")==REL+"comments"]
        record = {"coverage":"complete","body_sha256":digest(body_bytes),"count":0,"notes":[],"limitations":limitations}
        if links or declared or references or any("comments" in PurePosixPath(n).name.lower() and n.endswith(".xml") for n in names):
            if len(links)!=1 or links[0].get("TargetMode","Internal")!="Internal":
                raise ValueError("批注部件关联待核")
            target = links[0].get("Target","")
            part = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("word",target))
            if declared!={part} or part.startswith("../"):
                raise ValueError("批注部件类型或位置待核")
            if any(n != part and "comments" in PurePosixPath(n).name.lower() and n.endswith(".xml") for n in names) and "extended" not in limitations:
                limitations.append("extended")
            comment_bytes, container = xml_part(package, part, 4*1024**2)
            if container.tag!=W+"comments":
                raise ValueError("批注记录格式待核")
            comments = container.findall(W+"comment")
            ids = [c.get(W+"id") for c in comments]
            if len(comments)!=len(container) or None in ids or len(set(ids))!=len(ids) or set(ids)!=references:
                limitations.append("structure")
            if len(comments)>CAP:
                limitations.append("count")
            record.update(part=part, part_sha256=digest(comment_bytes), count=len(comments))
            for c in comments[:CAP]:
                key = c.get(W+"id","")
                text, simple = comment_text(c)
                if not simple and "content" not in limitations:
                    limitations.append("content")
                record["notes"].append({"key":key[:80], "author":c.get(W+"author","")[:160], "date":c.get(W+"date","")[:80],
                                        "text":text[:LIMIT], "shortened":len(text)>LIMIT, "anchor":located.get(key)})
        if limitations:
            record["coverage"] = "partial"
        return record


def word_units(graph, kinds=("acceptance", "reinspection")):
    ids = {unit for kind in kinds for unit in graph["documents_by_kind"].get(kind, [])}
    grouped = defaultdict(list)
    for unit in graph.get("audit_documents",graph["documents"]):
        if unit["id"] in ids:
            grouped[unit.get("source",unit["id"])].append(unit["id"])
    return [(d,grouped[d["id"]]) for d in graph["documents"] if d["id"] in grouped and d.get("ext") in {".doc",".docx"}]


def source_locations(graph, doc, read_text, wanted, compare=None):
    places = {(u["source"],u["page"]):u["id"] for u in graph.get("audit_documents",[]) if "source" in u}
    matches = defaultdict(list)
    keys = {compare(q) if compare else q for q in wanted}
    for p in graph["nodes"]:
        if p["type"]!="page" or not p["id"].startswith(doc["id"]+"/p"):
            continue
        number = int(p["id"].rsplit("/p",1)[1])
        text = read_text(doc["id"],number)
        if not isinstance(text,str) or digest(text.encode())!=p.get("text_sha256"):
            raise ValueError("Word 批注所据页文摘要与归档不符")
        for line, quote in enumerate(text.splitlines(),1):
            key = compare(quote) if compare else quote
            if key not in keys:
                continue
            facts = [f["id"] for f in graph["facts"] if f["doc"]==doc["id"] and f["page"]==number and
                     (compare(f["quote"]) == key if compare else f["quote"] == quote) and
                     f.get("source_sha256")==doc["sha256"] and f.get("page_sha256")==p["sha256"] and
                     (f.get("source_line") or {}).get("number")==line and f["source_line"].get("text")==quote and f["source_line"].get("rects")]
            where = {"unit":places.get((doc["id"],number),doc["id"]),"page":number,"line":line,
                     "page_sha256":p["sha256"],"text_sha256":p["text_sha256"],"facts":facts}
            if compare:
                where["printed"] = quote
            matches[key].append(where if p.get("layer")=="text" else None)
    located = {key:v[0] for key,v in matches.items() if len(v)==1 and v[0]}
    return {q:located[key] for q in wanted if (key := compare(q) if compare else q) in located}


def sources(graph, read_original, read_text, *, kinds=("acceptance", "reinspection"), role="acceptance", format_id=FORMAT, compare=None):
    records = []
    for doc,units in word_units(graph, kinds):
        raw = read_original(doc) if read_original else None
        if raw is not None and digest(raw)!=doc["sha256"]:
            raise ValueError("Word 批注所据原件摘要不符")
        review = {"coverage":"unreadable","count":None,"notes":[],"limitations":["format"]}
        if raw is not None and doc["ext"]==".docx":
            try:
                review = package_review(raw)
            except (BadZipFile, ET.ParseError, ValueError, KeyError, OSError, RuntimeError, NotImplementedError):
                pass
        ref = role + "-word/" + doc["id"]
        wanted = {n["anchor"]["quote"] for n in review["notes"] if n["anchor"]}
        locations = source_locations(graph,doc,read_text,wanted,compare) if wanted else {}
        for i,n in enumerate(review["notes"],1):
            n["id"] = ref+"/n"+str(i)
            n["location"] = locations.get(n["anchor"]["quote"]) if n["anchor"] else None
        records.append({**review,"id":ref,"doc":doc["id"],"units":units,"original_sha256":doc["sha256"]})
    return {"format":format_id,"documents":records}


def source_graph(ledger, *, role="acceptance", label="验收", relation="word_review"):
    nodes,edges = [],[]
    for doc in ledger["documents"]:
        ref = doc["id"]
        nodes.append({"id":ref,"type":role+"_word_review","doc":doc["doc"],"label":label+" Word 审阅记录"})
        edges.append({"from":doc["doc"],"to":ref,"type":relation+"_source","evidence":[doc["doc"]]})
        for note in doc["notes"]:
            ident = note["id"]
            nodes.append({"id":ident,"type":role+"_word_comment","doc":doc["doc"],"label":label+" Word 批注"})
            edges.append({"from":ref,"to":ident,"type":relation+"_comment","evidence":[doc["doc"],ref]})
            where = note["location"]
            if where:
                page = f"{doc['doc']}/p{where['page']}"
                edges.append({"from":page,"to":ident,"type":relation+"_anchor","evidence":[page,*where["facts"]]})
    return nodes,edges


def assess(ledger, scope, facts):
    files, notes, refs = [], [], []
    status = "ok"
    for d in ledger.get("documents",[]):
        if not set(d["units"]).intersection(scope):
            continue
        files.append(d["id"])
        refs.extend((d["doc"],d["id"]))
        if d["coverage"]!="complete" and status=="ok":
            status = "missing"
        for note in d["notes"]:
            loc = note["location"]
            if loc and loc["unit"] in d["units"] and loc["unit"] not in scope:
                continue
            notes.append(note["id"])
            refs.append(note["id"])
            if loc:
                refs.extend([f"{d['doc']}/p{loc['page']}",*loc["facts"]])
            positive = loc and loc["unit"] in scope and [facts[id] for id in loc["facts"] if id in facts and facts[id]["field"]=="acceptance_result" and
                                facts[id]["status"] in {"anchored","confirmed"} and facts[id]["value"].strip()=="合格"]
            anchor = note["anchor"]
            if (d["coverage"] == "complete" and positive and len(positive) == 1 and anchor and
                    anchor["selected"] in ("合格", anchor["quote"]) and anchor["quote"] in RESULT_LINES and
                    not note["shortened"] and QUANTITY_ONLY.fullmatch(normalize("NFKC", note["text"]).strip())):
                status = "risk"
            elif status=="ok":
                status = "missing"
    if not files:
        return None
    return {"status":status,"documents":files,"notes":notes,"evidence":list(dict.fromkeys(refs))}


def apply(item, graph, scope):
    ledger = graph.get("acceptance_word_reviews")
    if not ledger or not ledger["documents"]:
        return False
    check = assess(ledger,scope,{f["id"]:f for f in graph["facts"]})
    if not check:
        return False
    item["acceptance_comments"] = check
    item["evidence"] = list(dict.fromkeys([*item["evidence"],*check["evidence"]]))
    if check["status"]=="ok":
        return False
    detail = ("Word 验收正文列为合格，关联审阅批注另有限制，请核实正式终验范围及签认版本。" if check["status"]=="risk" else
              "Word 验收资料另有审阅意见或审阅层待核，请取得最终确认的版本和验收依据。")
    before = item["status"]
    if before=="ok" or before=="missing" and check["status"]=="risk":
        item["status"] = check["status"]
    if detail not in item["detail"]:
        item["detail"] = detail if before == "ok" else item["detail"] + " " + detail
    if item.get("reinspection"):
        item["reinspection"]["state"] = "open"
    return True


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("acceptance_word_reviews")
    node_types = {"acceptance_word_review","acceptance_word_comment"}
    edge_types = {"word_review_source","word_review_comment","word_review_anchor"}
    nodes = [n for n in graph["nodes"] if n["type"] in node_types]
    edges = [e for e in graph["edges"] if e["type"] in edge_types]
    if marker is None and "acceptance_word_reviews" not in graph:
        if policy.get("version","")>=SINCE or "acceptance_comments.py" in policy.get("code_sha256",{}) or nodes or edges:
            raise ValueError("缺少 Word 验收审阅记录")
        positive = [f for f in report.get("findings",[]) if f["rule"] in ("H02","H04","H05") and f["status"]=="ok"]
        if signing and positive and word_units(graph):
            ledger = sources(graph,read_original,read_text)
            for f in positive:
                check = assess(ledger,set(f["scope"]),{p["id"]:p for p in graph["facts"]})
                if check and check["status"]!="ok":
                    raise ValueError("旧版相符结论未核对验收 Word 的审阅记录，请重新审计后签收。")
        return
    if marker!=FORMAT:
        raise ValueError("Word 验收审阅程序标记不符")
    ledger = sources(graph,read_original,read_text)
    if graph.get("acceptance_word_reviews")!=ledger or (nodes,edges)!=source_graph(ledger):
        raise ValueError("Word 验收批注、原件位置或图谱引用与原件不符")
    return ledger
