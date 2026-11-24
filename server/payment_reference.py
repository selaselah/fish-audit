"""Bind a partial transaction reference to its printed field or an explicit note on the same receipt page."""

import hashlib
import re

from calculations import normalized
from payment_notes import annotated_fields, note_edges
from payment_visibility import image_holds


LEGACY_FORMAT = "receipt-reference-v1"
NOTE_FORMAT = "receipt-reference-v2"
FORMAT = "receipt-reference-v3"
SUPPORTED = {LEGACY_FORMAT,NOTE_FORMAT,FORMAT}
LABEL = re.compile(r"(?:交易|银行)?流水号")
LAST = r"(?:尾号|(?:后|末)[0-9一二三四五六七八九十]+位)"
PART = re.compile(r"(?:仅(?:显示|展示|保留|列示|列出)?)?" + LAST + r"|已(?:脱敏|遮盖|隐去部分位数)")
REVERSED = re.compile(r"仅(?:显示|展示|保留|列示|列出)(?:交易|银行)?流水号(?:的)?" + LAST)
MASK = re.compile(r"[*•●■□×…]|\.{2,}|[xX]{3,}")
NUMERIC_X = re.compile(r"[0-9Xx]*[Xx]{2,}[0-9Xx]*")
OTHER_FIELD = re.compile(r"(?:收款|付款)(?:人)?(?:账号|账户|户名)|(?:银行)?卡号|账户|账号|合同编号|发票号|交易状态")


def masked_value(value):
    return bool(MASK.search(value) or NUMERIC_X.fullmatch(value) or PART.match(value))


def printed_partial_value(quote,value):
    marker = r"(?:仅(?:显示|展示|保留|列示|列出)?)?" + LAST
    if not re.fullmatch(r"[A-Za-z0-9_-]+",value):
        return False
    number = re.escape(value)
    return bool(re.fullmatch(r"(?:交易|银行)流水号[:(]*(?:" + marker + r"[):]*" + number +
                             r"|" + number + r"\(" + marker + r"\))[。.]?", quote))


def partial_line(line):
    plain = normalized(line)
    if REVERSED.search(plain):
        return True
    for label in LABEL.finditer(plain):
        # Another field on the same printed line can have its own, unrelated masking instruction.
        rest = OTHER_FIELD.split(plain[label.end():], maxsplit=1)[0]
        rest = re.sub(r"^(?:显示说明|说明|备注)?[(:【「]*", "", rest)
        if PART.match(rest):
            return True
        printed = re.match(r"[A-Za-z0-9_*•●■□×….\-]+", rest)
        if printed and (masked_value(printed[0]) or PART.match(rest[printed.end():].lstrip("(,;【「"))):
            return True
    return False


def marked_fields(graph, read_text):
    banks = set(graph["documents_by_kind"].get("bank_receipt", []))
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    notes, marked = {}, []
    for fact in graph["facts"]:
        unit = fact.get("unit", fact["doc"])
        if fact["field"] != "transfer_ref" or unit not in banks or fact["status"] not in ("anchored","confirmed"):
            continue
        address = fact["doc"], fact["page"]
        if address not in notes:
            lines = []
            page = nodes[f"{address[0]}/p{address[1]}"]
            if page.get("layer") == "text" and page.get("text_sha256"):
                text = read_text(*address)
                if hashlib.sha256(text.encode()).hexdigest() != page["text_sha256"]:
                    raise ValueError("回单流水说明与归档文字层摘要不符")
                lines = [{"number":i,"text":line} for i,line in enumerate(text.splitlines(),1) if partial_line(line)]
            notes[address] = lines
        if notes[address] or masked_value(normalized(fact["value"])) or partial_line(fact["quote"]):
            marked.append({"fact":fact["id"],"field":"transfer_ref","unit":unit,"doc":fact["doc"],"page":fact["page"],
                           "value":fact["value"],"lines":notes[address]})
    return marked


def excluded_edges(graph, marked):
    units = {item["unit"] for item in marked}
    return {fact["id"]:{"from":unit,"to":fact["id"],"type":"incomplete_transfer_ref","evidence":[fact["id"]]}
            for fact in graph["facts"] if fact["field"]=="transfer_ref" and fact["status"] in ("anchored","confirmed")
            and (unit := fact.get("unit",fact["doc"])) in units}


def attach(graph, read_text, version=FORMAT):
    marked = marked_fields(graph, read_text)
    if version in (NOTE_FORMAT,FORMAT):
        marked = annotated_fields(graph,marked,partial_line)
        if version==FORMAT:
            marked = image_holds(graph,marked,trust_reviews=True)
        graph["edges"].extend(note_edges(marked))
    graph["transfer_references"] = {"format":version, "facts":marked}
    replacements = excluded_edges(graph, marked)
    if replacements:
        old = set()
        for edge in graph["edges"]:
            if edge["type"]=="transfer_ref" and edge["evidence"][0] in replacements:
                old.add(edge["to"])
                edge.update(replacements[edge["evidence"][0]])
        unused = old - {e["to"] for e in graph["edges"]}
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in unused]


def verify(graph, marked, version=FORMAT):
    if graph.get("transfer_references") != {"format":version, "facts":marked}:
        raise ValueError("遮盖流水的原页字段或说明行不符")
    expected = excluded_edges(graph, marked)
    edges = [e for e in graph["edges"] if e["type"]=="incomplete_transfer_ref"]
    if (len(edges)!=len(expected) or {e["evidence"][0]:e for e in edges}!=expected or
            any(e["type"]=="transfer_ref" and any(ref in expected for ref in e["evidence"]) for e in graph["edges"])):
        raise ValueError("不完整的流水号进入了精确比对，或缺少原文关系")
    if version in (NOTE_FORMAT,FORMAT):
        actual = [e for e in graph["edges"] if e["type"] in {"proposed_transfer_note","qualifies_transfer_ref"}]
        if actual!=note_edges(marked):
            raise ValueError("同页流水说明的引文关系或核图状态不符")


def issued_format(policy):
    modules = policy.get("code_sha256",{})
    for name,version in (("payment_visibility.py",FORMAT),("payment_notes.py",NOTE_FORMAT),("payment_reference.py",LEGACY_FORMAT)):
        if name in modules:
            return version
    return None


def check(graph, policy, read_text, *, compare_as=FORMAT):
    issued = issued_format(policy)
    if (policy.get("payment_references")!=issued or graph.get("transfer_references",{}).get("format")!=issued
            or compare_as not in SUPPORTED):
        raise ValueError("流水完整性核验格式与发行程序不符")
    versions = {issued,compare_as}
    fields = {LEGACY_FORMAT:marked_fields(graph,read_text)}
    if versions & {NOTE_FORMAT,FORMAT}:
        fields[NOTE_FORMAT] = annotated_fields(graph,fields[LEGACY_FORMAT],partial_line)
    if FORMAT in versions:
        fields[FORMAT] = image_holds(graph,fields[NOTE_FORMAT],trust_reviews=issued==FORMAT)
    if issued:
        verify(graph,fields[issued],issued)
    return fields[compare_as]
