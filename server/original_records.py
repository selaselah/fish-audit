"""Physical Word and image signing evidence, scoped to the filed document or bound page."""

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

import acceptance_comments as word
from pdf_execution import unit_graph


WORD = {".doc", ".docx"}


@dataclass(frozen=True)
class Family:
    role: str
    kinds: tuple[str, ...]
    label: str
    inspection: str
    fields: tuple[str, ...]
    format: str
    compare: Callable[[str], str] | None = None


def filings(graph, family):
    from config import FORMATS

    assigned = {unit for kind in family.kinds for unit in graph.get("documents_by_kind", {}).get(kind, ())}
    units = defaultdict(list)
    for unit in graph.get("audit_documents", graph["documents"]):
        if unit["id"] in assigned:
            units[unit.get("source", unit["id"])].append(unit)
    return [(doc, units[doc["id"]]) for doc in graph["documents"]
            if doc["id"] in units and doc.get("ext") in FORMATS and doc["ext"] != ".pdf"]


def sources(graph, read_original, read_text, family, *, reviews=None):
    from config import MAX_PAGES

    available = set()

    def original(doc):
        raw = read_original(doc) if read_original else None
        if raw is not None:
            if sha256(raw).hexdigest() != doc["sha256"]:
                raise ValueError(f"{family.label}原件与入库摘要不符")
            available.add(doc["id"])
        return raw

    documents = reviews if reviews is not None else word.sources(graph, original, read_text, kinds=family.kinds,
                             role=family.role, format_id=family.format, compare=family.compare)["documents"]
    by_doc = {r["doc"]: r for r in documents}
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    records = []
    for doc, units in filings(graph, family):
        ident, ext = doc["id"], doc["ext"]
        review = by_doc.get(ident)
        if ext not in WORD or reviews is not None:
            original(doc)
        total = doc.get("pages")
        if total is None:
            total = sum(ref.startswith(ident + "/p") for ref in nodes)
        if type(total) is not int or not 1 <= total <= MAX_PAGES:
            raise ValueError(f"{family.label}物理页数待核")
        for unit in units:
            numbers = [unit["page"]] if "source" in unit else range(1, total + 1)
            pages, has_text = [], False
            for number in numbers:
                ref = f"{ident}/p{number}"
                node = nodes.get(ref)
                if type(number) is not int or not 1 <= number <= total or node is None:
                    raise ValueError(f"{family.label}单元的物理页缺失")
                text = read_text(ident, number)
                if not isinstance(text, str) or sha256(text.encode()).hexdigest() != node.get("text_sha256"):
                    raise ValueError(f"{family.label}原页文字与留存摘要不符")
                has_text |= bool(text.strip())
                pages.append({"ref": ref, "sha256": node["sha256"], "layer": node["layer"],
                              "text_only": node.get("clause_text_only") is True})
            fields = [f["id"] for f in graph["facts"] if (f.get("unit") or f["doc"]) == unit["id"]
                      and f["doc"] == ident and f["page"] in numbers and f["field"] in family.fields]
            notes, unplaced = [], 0
            if review:
                for note in review["notes"]:
                    loc = note["location"]
                    if (loc and loc["unit"] == unit["id"]) or (not loc and unit["id"] == ident):
                        notes.append(note["id"])
                    elif not loc:
                        unplaced += 1
            state = "review"
            if ident in available and review:
                if notes or unplaced or review["coverage"] != "complete":
                    state = "word_review"
                elif all(p["layer"] == "text" and p["text_only"] for p in pages) and has_text:
                    state = "word_text"
                elif any(p["layer"] == "image_overlay" or p["layer"] == "text" and not p["text_only"] for p in pages):
                    state = "word_visual"
            elif ident in available and ext not in WORD and all(p["layer"] == "image" for p in pages):
                state = "photo"
            records.append({"id": family.role + "-original/" + unit["id"], "unit": unit["id"], "doc": ident,
                            "original_sha256": doc["sha256"], "kind": "word" if review else "image", "state": state,
                            "pages": pages, "fields": fields, "review": review["id"] if review else None,
                            "notes": notes, "unplaced": unplaced})
    ledger = {"format": family.format, "records": records}
    if reviews is None:
        ledger["documents"] = documents
    return ledger


def source_graph(ledger, family, *, reviews=None):
    nodes, edges = unit_graph(ledger, family.role + "_original", family.inspection)
    documents = ledger["documents"] if reviews is None else reviews
    notes = {n["id"]: n for doc in documents for n in doc["notes"]}
    for record in ledger["records"]:
        if record["review"]:
            refs = [record["doc"], record["review"]]
            edges.append({"from": record["review"], "to": record["id"], "type": family.role + "_original_word", "evidence": refs})
            for ident in record["notes"]:
                edges.append({"from": record["id"], "to": ident, "type": family.role + "_original_comment",
                              "evidence": refs + note_page_refs(record["doc"], notes[ident])})
    if reviews is not None:
        return nodes, edges
    word_nodes, word_edges = word.source_graph(ledger, role=family.role, label=family.label, relation=family.role + "_word_review")
    return nodes + word_nodes, edges + word_edges


def note_page_refs(doc, note):
    loc = note["location"]
    return [f"{doc}/p{loc['page']}", *loc["facts"]] if loc else []


def review_refs(records, ledger):
    notes = {n["id"]: n for doc in ledger["documents"] for n in doc["notes"]}
    for record in records:
        if record["review"]:
            yield record["review"]
        for ident in record["notes"]:
            yield ident
            yield from note_page_refs(record["doc"], notes[ident])


def verify_rendered(graph, records, read_original, label):
    # Called outside the signoff write transaction. Reproduce each relevant physical original once.
    from documents import prepare

    pages = {p["ref"]: p for r in records for p in r["pages"]}
    docs = {r["doc"] for r in records}
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    lines = defaultdict(list)
    for fact in graph["facts"]:
        ref = f"{fact['doc']}/p{fact['page']}"
        if ref in pages and fact.get("source_line"):
            lines[ref].append(fact["source_line"])
    for doc in graph["documents"]:
        if doc["id"] not in docs:
            continue
        raw = read_original(doc)
        if sha256(raw).hexdigest() != doc["sha256"]:
            raise ValueError(f"{label}原件与入库摘要不符")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ("original" + doc["ext"])
            path.write_bytes(raw)
            rendered = prepare(path, doc["pages"], save_images=False)
        checked = set()
        for page in rendered:
            ref = f"{doc['id']}/p{page['number']}"
            if ref in pages:
                layer = page["layer"]
                if sha256(page["text"].encode()).hexdigest() != nodes[ref]["text_sha256"]:
                    raise ValueError(f"{label}打印页的原文与记录不符")
                if (page["sha256"], layer["type"], layer.get("clause_text_only") is True) != (
                        pages[ref]["sha256"], pages[ref]["layer"], pages[ref]["text_only"]):
                    raise ValueError(f"{label}签章页图或版式不能从原件重现")
                text = page["text"].splitlines()
                for line in lines[ref]:
                    number = line["number"]
                    if (type(number) is not int or not 1 <= number <= len(text) or text[number-1] != line["text"]
                            or layer["lines"].get(str(number), []) != line["rects"]):
                        raise ValueError(f"{label}引文位置不能从原件重现")
                checked.add(ref)
        if len(rendered) != doc["pages"] or checked != {ref for ref in pages if ref.startswith(doc["id"] + "/p")}:
            raise ValueError(f"{label}签章原件的物理页清单不符")
