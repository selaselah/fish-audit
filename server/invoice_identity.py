"""Identify invoices from printed numbers and, for eight-digit numbers, their same-page codes."""

import hashlib
import re
from collections import Counter, defaultdict

from calculations import normalized
from invoice_proof import invoice_number_edges


FORMAT = "printed-invoice-v1"
SHORT = re.compile(r"[0-9]{8}")
CODE = re.compile(r"(?:[0-9]{10}|[0-9]{12})")
PAIR = re.compile(r"([0-9]{10}|[0-9]{12})[/|]([0-9]{8})")
VERIFIED = {"anchored","confirmed"}
FULLWIDTH = str.maketrans("０１２３４５６７８９／｜","0123456789/|")


def printed(value):
    return "".join(value.translate(FULLWIDTH).split())


class InvoiceIdentities:
    def __init__(self, graph):
        self.codes = defaultdict(list)
        self.linked = {(e["from"],e["to"],ref) for e in graph["edges"] if e["type"]=="invoice_code" for ref in e["evidence"]}
        self.gaps = {(g["doc"],g["page"]) for g in graph.get("gaps",[]) if g.get("field")=="invoice_code"}
        for fact in graph["facts"]:
            if fact["field"]=="invoice_code":
                self.codes[fact.get("unit",fact["doc"]),fact["doc"],fact["page"]].append(fact)

    def describe(self, fact):
        number = normalized(fact["value"])
        if not SHORT.fullmatch(number):
            return {"kind":"twenty_digit" if re.fullmatch(r"[0-9]{20}",number) else "number",
                    "number":number,"code":None,"code_refs":[]}
        doc,page = fact["doc"],fact["page"]
        unit = fact.get("unit",doc)
        observations = self.codes[unit,doc,page]
        codes = {printed(f["value"]) for f in observations}
        def supported(f):
            value = normalized(f["value"])
            target = "invoice_code-"+hashlib.sha256(value.encode()).hexdigest()[:18]
            return f["status"] in VERIFIED and value in normalized(f["quote"]) and (unit,target,f["id"]) in self.linked
        complete = (printed(fact["value"])==number and len(codes)==1 and CODE.fullmatch(next(iter(codes)))
                    and (doc,page) not in self.gaps and all(supported(f) for f in observations))
        return {"kind":"code_number" if complete else "short_unresolved","number":number,
                "code":next(iter(codes)) if complete else None,"code_refs":[f["id"] for f in observations]}


def identity_key(identity):
    return None if identity["kind"]=="short_unresolved" else (identity["code"] or "",identity["number"])


def identity_relations(graph):
    identities = InvoiceIdentities(graph)
    facts = {f["id"]:f for f in graph["facts"]}
    nodes,edges = {},[]
    for edge in invoice_number_edges(graph):
        for ref in edge["evidence"]:
            item = identities.describe(facts[ref])
            if item["kind"] not in {"code_number","twenty_digit"}:
                continue
            label = " / ".join(part for part in identity_key(item) if part)
            target = "invoice-identity-"+hashlib.sha256(label.encode()).hexdigest()[:24]
            nodes[target] = {"id":target,"type":"invoice_identity","label":label,"kind":item["kind"]}
            edges.append({"from":edge["from"],"to":target,"type":"identified_invoice","evidence":[ref,*item["code_refs"]]})
    return list(nodes.values()),edges


def within_case(number, identities):
    keys = [identity_key(i) for i in identities]
    duplicates = any(n>1 for key,n in Counter(keys).items() if key is not None)
    codes = list(dict.fromkeys(i["code"] for i in identities if i["code"]))
    detail = f"号码 {number} 出现在本案 {len(keys)} 份已识别发票中。"
    if codes:
        detail += "同页发票代码为 "+"、".join(codes)+"。"
    if duplicates:
        detail += "存在相同票据标识，请核对原票、副本及实际报销次数。"
    if None in keys:
        detail += "八位号码缺少可唯一核定的同页代码，请对照原件。"
    elif len(keys)>1 and not duplicates:
        detail += "各票的代码与号码组合互异。"
    return ("risk" if duplicates else "missing" if None in keys else "ok"),detail


def match_claim(listed, identities):
    keys,labels = [],[]
    for f in listed:
        value = printed(f["value"])
        labels.append(f["value"])
        if f["field"]=="claim_full_ref":
            pair = PAIR.fullmatch(value)
            keys.append(pair.groups() if pair else None)
        else:
            number = normalized(f["value"])
            keys.append(None if SHORT.fullmatch(number) else ("",number))
    actual = [identity_key(i) for i in identities]
    matched = bool(keys) and None not in keys and None not in actual and len(set(actual))==len(actual) and Counter(keys)==Counter(actual)
    attachments = [(i["code"]+" / " if i["code"] else "")+i["number"] for i in identities]
    detail = "申请列示：" + ("、".join(labels) or "缺少票号") + "。附件发票：" + ("、".join(attachments) or "缺少票号") + "。"
    if not matched and any(SHORT.fullmatch(i["number"]) for i in identities):
        detail += "八位票号按申请明列的代码与号码逐票关联。"
    return matched,detail
