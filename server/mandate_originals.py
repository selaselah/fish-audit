"""Review the submitted Word or image mandate and retain the provenance of its signing fields."""

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import acceptance_comments as word
from mandate_execution import depends_on_positive
from pdf_execution import apply_unit_records, unit_graph


FORMAT = "mandate-original-execution-v1"
SINCE = (2026, 11, 27, 4)
WORD = {".doc", ".docx"}
DETAIL = {
    "word_text": "委托书 Word 打印页仅见排印文字。请核对委托方签发的原件或对应签署记录。",
    "word_visual": "委托书 Word 页含图形或其他版面元素。请对照签章栏与委托方的签发记录。",
    "word_review": "委托书 Word 的批注、修订或审阅范围待核。请核对定稿及委托方签发依据。",
    "photo": "委托书为上传的影像。请对照原图核实委托方签章、用印或其他签发依据。",
    "review": "委托书原件的签发依据待核。请核对提交版本、签章和签发记录。",
}


def filings(graph):
    from config import FORMATS

    assigned = set(graph.get("documents_by_kind", {}).get("power_of_attorney", ()))
    units = defaultdict(list)
    for unit in graph.get("audit_documents", graph["documents"]):
        if unit["id"] in assigned:
            units[unit.get("source", unit["id"])].append(unit)
    return [(doc, units[doc["id"]]) for doc in graph["documents"]
            if doc["id"] in units and doc.get("ext") in FORMATS and doc["ext"] != ".pdf"]


def sources(graph, read_original, read_text):
    from config import MAX_PAGES

    available = set()

    def original(doc):
        raw = read_original(doc) if read_original else None
        if raw is not None:
            if sha256(raw).hexdigest() != doc["sha256"]:
                raise ValueError("委托书原件与入库摘要不符")
            available.add(doc["id"])
        return raw

    documents = word.sources(graph, original, read_text, kinds=("power_of_attorney",),
                             role="mandate", format_id=FORMAT)["documents"]
    reviews = {r["doc"]: r for r in documents}
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    records = []
    for doc, units in filings(graph):
        ident, ext = doc["id"], doc["ext"]
        review = reviews.get(ident)
        if ext not in WORD:
            original(doc)
        total = doc.get("pages")
        if total is None:
            total = sum(ref.startswith(ident + "/p") for ref in nodes)
        if type(total) is not int or not 1 <= total <= MAX_PAGES:
            raise ValueError("委托书物理页数待核")
        for unit in units:
            numbers = [unit["page"]] if "source" in unit else range(1, total + 1)
            pages, has_text = [], False
            for number in numbers:
                ref = f"{ident}/p{number}"
                node = nodes.get(ref)
                if type(number) is not int or not 1 <= number <= total or node is None:
                    raise ValueError("委托书单元的物理页缺失")
                text = read_text(ident, number)
                if not isinstance(text, str) or sha256(text.encode()).hexdigest() != node.get("text_sha256"):
                    raise ValueError("委托书原页文字与留存摘要不符")
                has_text |= bool(text.strip())
                pages.append({"ref": ref, "sha256": node["sha256"], "layer": node["layer"],
                              "text_only": node.get("clause_text_only") is True})
            fields = [f["id"] for f in graph["facts"] if (f.get("unit") or f["doc"]) == unit["id"]
                      and f["doc"] == ident and f["page"] in numbers and f["field"] == "grant_signature"]
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
            records.append({"id": "mandate-original/" + unit["id"], "unit": unit["id"], "doc": ident,
                            "original_sha256": doc["sha256"], "kind": "word" if review else "image", "state": state,
                            "pages": pages, "fields": fields, "review": review["id"] if review else None,
                            "notes": notes, "unplaced": unplaced})
    return {"format": FORMAT, "records": records, "documents": documents}


def source_graph(ledger):
    nodes, edges = unit_graph(ledger, "mandate_original", "委托书原件签发凭证")
    word_nodes, word_edges = word.source_graph(ledger, role="mandate", label="委托书", relation="mandate_word_review")
    notes = {n["id"]: n for doc in ledger["documents"] for n in doc["notes"]}
    for record in ledger["records"]:
        if record["review"]:
            refs = [record["doc"], record["review"]]
            edges.append({"from": record["review"], "to": record["id"], "type": "mandate_original_word", "evidence": refs})
            for ident in record["notes"]:
                edges.append({"from": record["id"], "to": ident, "type": "mandate_original_comment",
                              "evidence": refs + note_page_refs(record["doc"], notes[ident])})
    return nodes + word_nodes, edges + word_edges


def note_page_refs(doc, note):
    loc = note["location"]
    return [f"{doc}/p{loc['page']}", *loc["facts"]] if loc else []


def review_entries(entries, ledger):
    notes = {n["id"]: n for d in ledger.get("documents", ()) for n in d["notes"]}
    for entry in entries:
        selected = [r for r in ledger.get("records", ()) if r["unit"] in entry["units"]]
        if not apply_unit_records(entry, selected, "mandate_originals", DETAIL):
            continue
        refs = list(entry["evidence"])
        for record in selected:
            if record["review"]:
                refs.append(record["review"])
            for ident in record["notes"]:
                refs.extend([ident, *note_page_refs(record["doc"], notes[ident])])
        entry["evidence"] = list(dict.fromkeys(refs))


def verify_rendered(graph, records, read_original):
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
            raise ValueError("委托书原件与入库摘要不符")
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
                    raise ValueError("委托书打印页的原文与记录不符")
                if (page["sha256"], layer["type"], layer.get("clause_text_only") is True) != (
                        pages[ref]["sha256"], pages[ref]["layer"], pages[ref]["text_only"]):
                    raise ValueError("委托书签章页图或版式不能从原件重现")
                text = page["text"].splitlines()
                for line in lines[ref]:
                    number = line["number"]
                    if (type(number) is not int or not 1 <= number <= len(text) or text[number-1] != line["text"]
                            or layer["lines"].get(str(number), []) != line["rects"]):
                        raise ValueError("委托书引文位置不能从原件重现")
                checked.add(ref)
        if len(rendered) != doc["pages"] or checked != {ref for ref in pages if ref.startswith(doc["id"] + "/p")}:
            raise ValueError("委托书签章原件的物理页清单不符")


def legacy_records(graph):
    for doc, units in filings(graph):
        for unit in units:
            fields = [f["id"] for f in graph["facts"] if f["doc"] == doc["id"] and f["field"] == "grant_signature"
                      and (f.get("unit") or f["doc"]) == unit["id"]]
            yield {"unit": unit["id"], "fields": fields}


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    nodes = [n for n in graph["nodes"] if n["type"] in {"mandate_original_inspection", "mandate_word_review", "mandate_word_comment"}]
    edges = [e for e in graph["edges"] if e["type"].startswith(("mandate_original_", "mandate_word_review_"))]
    entries = [e for f in report["findings"] if f["rule"] == "H01" for e in f.get("delegations", ())]
    marker = policy.get("mandate_originals")
    if marker is None:
        version = tuple(map(int, (policy.get("version") or "0").split(".")))
        if (version >= SINCE or "mandate_originals.py" in policy.get("code_sha256", {}) or nodes or edges or
                "mandate_original_sources" in graph or any("mandate_originals" in e for e in entries)):
            raise ValueError("缺少委托书 Word 或影像的签发核查记录")
        if signing and depends_on_positive(entries, report["findings"], lambda: legacy_records(graph)):
            raise ValueError("旧版相符结论依赖尚未核验签发依据的 Word 或影像委托书，请重审后签收。")
        return
    if "code_sha256" in policy and "mandate_originals.py" not in policy["code_sha256"]:
        raise ValueError("委托书原件签发程序缺少归档源码摘要")
    expected = sources(graph, read_original, read_text)
    if marker != FORMAT or graph.get("mandate_original_sources") != expected or (nodes, edges) != source_graph(expected):
        raise ValueError("委托书原件、审阅记录、签章字段或图谱关系不符")
    if signing and expected["records"]:
        cited = {ref for f in report["findings"] if f["rule"] in ("H01", "H04", "H05") for ref in f["evidence"]}
        verify_rendered(graph, [r for r in expected["records"] if r["id"] in cited], read_original)
