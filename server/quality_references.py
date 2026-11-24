"""Keep partially displayed acceptance and defect numbers out of exact graph matches."""

import hashlib
import re
from collections import defaultdict

from calculations import normalized
from invoice_masks import MASK, NUMERIC_X
from reinspection import LABELS, NUMBER_TYPES


FORMAT = "quality-reference-visibility-v1"
PRINTED = {label: field for field in NUMBER_TYPES for label in LABELS[field]}
DISPLAY_NOTE = re.compile(r"(?:展示|显示)?(?:说明|范围)|备注")
PARTIAL = re.compile(r"(?:尾号|[后末][零一二两三四五六七八九十0-9]+位|已脱敏|中段(?:已)?隐去|已遮盖)")
OTHER_FIELD = re.compile(r"[,;。](?:收款|付款|银行|账户|账号|发票|合同|验收|复验|整改|缺陷|问题单)")
EMBEDDED_X = re.compile(r"(?<=[0-9])[xX]{2,}(?=[0-9]|$)")


def incomplete_number(value):
    value = normalized(value)
    return bool(MASK.search(value) or PARTIAL.search(value) or EMBEDDED_X.search(value)
                or any(NUMERIC_X.fullmatch(part) for part in re.split(r"[-_.]", value)))


def qualified_field(line):
    label, separator, body = normalized(line).partition(":")
    if not separator:
        return None
    # A note printed for a bank account on the same line belongs to that account.
    body = OTHER_FIELD.split(body, maxsplit=1)[0]
    for name, field in PRINTED.items():
        if label == name or (label.startswith(name) and DISPLAY_NOTE.fullmatch(label[len(name):])):
            return field if incomplete_number(body) else None
        if label.startswith(name + "(") and label.endswith(")") and incomplete_number(label[len(name):]):
            return field
    return None


def marked_fields(graph, read_text):
    pages = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    visual_notes = defaultdict(list)
    for observation in graph["facts"]:
        address = observation["doc"], observation["page"]
        if pages.get(f"{address[0]}/p{address[1]}", {}).get("layer") in ("image", "image_overlay", "unknown"):
            target = qualified_field(observation["quote"])
            if target:
                visual_notes[(*address, target)].append({"fact": observation["id"], "quote": observation["quote"]})
    notes = {}
    marked = []
    for fact in graph["facts"]:
        field = fact["field"]
        if field not in NUMBER_TYPES or fact["status"] not in ("anchored", "confirmed"):
            continue
        address = fact["doc"], fact["page"]
        if address not in notes:
            page = pages[f"{address[0]}/p{address[1]}"]
            by_field = defaultdict(list)
            if page.get("layer") == "text":
                text = read_text(*address)
                if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != page.get("text_sha256"):
                    raise ValueError("验收及整改编号的展示说明与原页文字层摘要不符")
                for number, line in enumerate(text.splitlines(), 1):
                    target = qualified_field(line)
                    if target:
                        by_field[target].append({"number": number, "quote": line})
            notes[address] = by_field
        lines = notes[address][field]
        observations = [note for note in visual_notes[(*address, field)] if note["fact"] != fact["id"]]
        if lines or observations or incomplete_number(fact["value"]) or qualified_field(fact["quote"]) == field:
            marked.append({"fact": fact["id"], "field": field, "value": fact["value"], "doc": fact["doc"],
                           "page": fact["page"], "unit": fact.get("unit", fact["doc"]), "lines": lines,
                           "observations": observations})
    return marked


def attach(graph, read_text):
    holds = marked_fields(graph, read_text)
    graph["quality_references"] = {"format": FORMAT, "holds": holds}
    if not holds:
        return
    references = {item["fact"] for item in holds}
    replaced = set()
    for edge in graph["edges"]:
        if edge["type"] in NUMBER_TYPES and edge["evidence"][0] in references:
            replaced.add(edge["to"])
            edge.update(type="incomplete_" + edge["type"], to=edge["evidence"][0])
    unused = replaced - {edge["to"] for edge in graph["edges"]}
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in unused]


def verify_report(report, read_text, *, signing=False):
    policy, graph = report["policy"], report["graph"]
    marker = policy.get("quality_references")
    if marker:
        if marker != FORMAT or graph.get("quality_references") != {"format": FORMAT, "holds": marked_fields(graph, read_text)}:
            raise ValueError("验收及整改编号的部分展示记录与所据原文不符")
        return
    if "quality_references.py" in policy.get("code_sha256", {}) or "quality_references" in graph:
        raise ValueError("缺少验收及整改编号展示范围核对程序")
    if signing:
        used = {ref for finding in report["findings"] if finding.get("reinspection", {}).get("state") == "closed"
                for ref in finding["evidence"]}
        if used and any(item["fact"] in used for item in marked_fields(graph, read_text)):
            raise ValueError("旧版关闭缺陷时引用了部分展示的编号，请按现行程序重审")
