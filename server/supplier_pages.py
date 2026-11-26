"""Prove the printed surface used by H02 from both revisions of the submitted PDF."""

from collections import defaultdict
from hashlib import sha256
from io import BytesIO
from itertools import islice
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

LEGACY = "pdf-supplier-pages-v1"
FORMAT = "pdf-supplier-pages-v2"
NOTES_SINCE = "2026.11.26.16"
SINCE = "2026.11.26.15"
MAX_ANNOTATIONS = 64
WIDGET_KEYS = {"/Type", "/Subtype", "/FT", "/F", "/P", "/Rect", "/T", "/V"}


def digest(raw):
    return sha256(raw).hexdigest()


def annotations(reader, page, fields, format):
    from pyhanko.pdf_utils import generic

    ref, _ = reader.find_page_for_modification(page - 1)
    items = ref.get_object().get("/Annots", [])
    result = []
    for index, item in enumerate(islice(items, MAX_ANNOTATIONS), 1):
        obj = item.get_object()
        subtype = str(obj.get("/Subtype", ""))
        text = obj.get("/Contents")
        note = str(text) if isinstance(text, generic.TextStringObject) else ""
        row = {"number": index, "subtype": subtype[:80], "kind": "annotation", "note": note[:512],
               "shortened": len(note) > 512}
        field = fields.get(item.reference) if isinstance(item, generic.IndirectObject) else None
        ordinary = True
        if format == FORMAT and subtype == "/Widget" and obj.get("/FT") == "/Sig" and "/V" in obj:
            sig = obj["/V"]
            reason = sig.get("/Reason")
            if reason is not None:
                literal = str(reason) if isinstance(reason, generic.TextStringObject) else ""
                row.update(kind="signature_reason", signing_reason=literal[:512], reason_shortened=len(literal) > 512)
            ordinary = set(sig).issubset({"/Type", "/Filter", "/SubFilter", "/Contents", "/ByteRange", "/M"})
            if not ordinary and reason is None:
                row["kind"] = "signature_details"
            if field:
                row["field"] = field
        if ordinary and field and "/P" in obj and set(obj).issubset(WIDGET_KEYS) and obj.get("/Type", "/Annot") == "/Annot" and subtype == "/Widget" and obj.get("/FT") == "/Sig":
            rect = obj.get("/Rect")
            if (isinstance(rect, generic.ArrayObject) and len(rect) == 4 and
                    all(isinstance(x, (generic.NumberObject, generic.FloatObject)) for x in rect) and
                    rect[0] == rect[2] and rect[1] == rect[3] and obj.raw_get("/P") == ref):
                row.update(kind="signature_field", field=field)
        result.append(row)
    return len(items), result


def revisions(raw, reader, signatures):
    """Cross-check PDFium trailer ends with the independently verified signed ranges."""
    import ctypes
    import pypdfium2 as pdfium
    from pdf_execution import PDFIUM_LOCK
    from pyhanko.sign.diff_analysis import DEFAULT_DIFF_POLICY, ModificationLevel

    with PDFIUM_LOCK, pdfium.PdfDocument(raw) as pdf:
        count = pdfium.raw.FPDF_GetTrailerEnds(pdf, None, 0)
        if count < 2 or count > 128 or count != reader.xrefs.total_revisions:
            return None
        ends = (ctypes.c_uint * count)()
        if pdfium.raw.FPDF_GetTrailerEnds(pdf, ends, count) != count:
            return None
    if list(ends) != sorted(set(ends)) or not 0 < ends[0] < len(raw) or ends[-1] != len(raw):
        return None
    if any(not 1 < s["revision"] <= count or ends[s["revision"] - 1] != s["ends_at"] for s in signatures):
        return None
    # A later unclassified change keeps the page under review even when the name looks the same.
    last_signed = max(s["revision"] for s in signatures)
    if last_signed < count:
        diff = DEFAULT_DIFF_POLICY.review_file(reader, last_signed - 1)
        if getattr(diff, "modification_level", None) not in (ModificationLevel.NONE, ModificationLevel.LTA_UPDATES):
            return None
    return ends[0]


def render_pages(source, target):
    from config import MAX_PAGES
    from documents import render
    from pdf_execution import PDFIUM_LOCK

    target.mkdir()
    with PDFIUM_LOCK:
        render(source, target, MAX_PAGES)
    return json.loads((target / "manifest.json").read_bytes())


def inspect(source, targets, execution, format):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    raw = source.read_bytes()
    rows = {n: {"state": "review", "count": None, "annotations": []} for n in targets}
    try:
        reader = PdfFileReader(BytesIO(raw), strict=True)
        if reader.encrypted:
            return rows
        signatures = (execution or {}).get("signatures", [])
        complete = (execution or {}).get("state") in {"current", "earlier"} and bool(signatures) and all(
            s["state"] in {"current", "earlier"} for s in signatures)
        fields = {}
        if complete:
            filled = list(enumerate_sig_fields(reader, filled_status=True))
            if len(filled) == len(signatures) and all(str(f[0]) == s["field"] for f, s in zip(filled, signatures)):
                fields = {field.reference: str(name) for name, _, field in filled}
        candidates = []
        for page in rows:
            try:
                total, notes = annotations(reader, page, fields, format)
            except Exception:
                continue
            rows[page].update(count=total, annotations=notes)
            if total > len(notes) or any(note["kind"] != "signature_field" for note in notes):
                rows[page]["state"] = "annotations"
            elif total and fields:
                candidates.append(page)
        if not candidates:
            return rows
        end = revisions(raw, reader, signatures)
        if end is None:
            return rows
        initial_bytes = raw[:end]
        initial_reader = PdfFileReader(BytesIO(initial_bytes), strict=True)
        if initial_reader.xrefs.total_revisions != 1:
            return rows
        first = source.parent / "first.pdf"
        first.write_bytes(initial_bytes)
        previous = render_pages(first, source.parent / "first-pages")
        current = render_pages(source, source.parent / "current-pages")
        if len(previous) != len(current):
            return rows
        first_hash = digest(initial_bytes)
        for page in candidates:
            old, new = previous[page - 1], current[page - 1]
            if initial_reader.find_page_for_modification(page - 1)[0] != reader.find_page_for_modification(page - 1)[0]:
                continue
            before, after = old["layer"], new["layer"]
            proof = {"revision": 1, "ends_at": end, "original_sha256": first_hash,
                     "first_page_sha256": old["sha256"], "page_sha256": new["sha256"],
                     "first_text_sha256": digest(old["text"].encode()), "text_sha256": digest(new["text"].encode()),
                     "same_positions": before["lines"] == after["lines"]}
            rows[page]["comparison"] = proof
            if (before["type"] == after["type"] == "text" and before.get("clause_text_only") is True and
                    old["sha256"] == new["sha256"] and old["text"] == new["text"] and proof["same_positions"] and
                    old["width"] == new["width"] and old["height"] == new["height"]):
                rows[page]["state"] = "same_print"
                lines = new["text"].splitlines()
                rows[page]["readings"] = [{"line": number, "quote": lines[number - 1], "rects": after["lines"].get(str(number), [])}
                                         for number in targets[page] if 0 < number <= len(lines)]
        return rows
    except Exception:
        # Unsupported annotations, revisions or page encodings retain human review.
        return rows


def inspect_isolated(raw, targets, execution, format):
    # PDFium rendering runs in a short-lived process, independent of simultaneous signoffs.
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "original.pdf"
        source.write_bytes(raw)
        try:
            run = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(source)],
                                 input=json.dumps([targets, execution, format]), text=True, capture_output=True, timeout=150)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF 供应方页版式核对超时，请重试。") from exc
        if run.returncode:
            raise ValueError("PDF 供应方页版式核对中断，请重试。")
        return {int(n): row for n, row in json.loads(run.stdout).items()}


def sources(graph, read_original, format=FORMAT):
    ledger = graph.get("acceptance_reservation_sources", {})
    documents = {d["id"]: d for d in graph["documents"]}
    nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    signed = {r["doc"]: r for r in graph.get("pdf_execution_sources", {}).get("documents", [])}
    grouped = defaultdict(list)
    pages = ledger.get("supplier_pages", [])
    if {p["role"] for p in pages} == {"contract", "receipt"}:
        for page in pages:
            if not page["text_only"] and documents[page["doc"]].get("ext") == ".pdf":
                grouped[page["doc"]].append(page)
    result = []
    for doc, places in grouped.items():
        original = documents[doc]
        raw = read_original(original) if read_original else None
        if raw is not None and digest(raw) != original["sha256"]:
            raise ValueError("供应方页所据 PDF 与入库原件摘要不符")
        targets = {p["page"]: sorted({s["line"] for s in ledger["supplier_rows"] if s["doc"] == doc and
                   s["page"] == p["page"] and s["kind"] == "seller" and s["line"]}) for p in places}
        observed = inspect_isolated(raw, targets, signed.get(doc), format) if raw is not None else {}
        for p in places:
            ref = f"{doc}/p{p['page']}"
            check = observed.get(p["page"], {"state": "review", "count": None, "annotations": []})
            node = nodes[ref]
            comparison = check.get("comparison")
            if comparison and (comparison["page_sha256"] != node.get("sha256") or comparison["text_sha256"] != node.get("text_sha256")):
                raise ValueError("供应方页复算影像或文字与当版原件不符")
            result.append({**p, "id": "supplier-page/" + ref, "original_sha256": original["sha256"],
                           "page_sha256": node["sha256"], "signature_source": signed.get(doc, {}).get("id"), **check})
    return {"format": format, "pages": result}


def source_graph(ledger):
    nodes, edges = [], []
    for p in ledger["pages"]:
        ref = f"{p['doc']}/p{p['page']}"
        evidence = [p["doc"], ref] + ([p["signature_source"]] if p["signature_source"] else [])
        nodes.append({"id": p["id"], "type": "supplier_page_inspection", "doc": p["doc"], "page": p["page"], "label": "供应方页版式核对"})
        edges.append({"from": ref, "to": p["id"], "type": "supplier_page_source", "evidence": evidence})
    return nodes, edges


def supported(page, rows, facts):
    if page["role"] != "contract" or not page["native"] or page["state"] != "same_print":
        return False
    readings = {r["line"]: r for r in page.get("readings", [])}
    for row in rows:
        if (row["doc"], row["page"], row["kind"]) != (page["doc"], page["page"], "seller"):
            continue
        reading = readings.get(row["line"])
        if not reading or not reading["rects"] or reading["quote"] != row["quote"]:
            return False
        matches = [facts[ref] for ref in row["facts"] if facts[ref]["field"] == "seller"]
        if len(matches) != 1:
            return False
        fact = matches[0]
        if (fact["source_sha256"] != page["original_sha256"] or fact["page_sha256"] != page["page_sha256"] or
                fact.get("source_line") != {"number": row["line"], "text": reading["quote"], "rects": reading["rects"]}):
            return False
    return True


def verify(report, read_original, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("supplier_page_inspection")
    if marker is None and "supplier_page_sources" not in graph:
        if policy.get("version", "") >= SINCE or "supplier_pages.py" in policy.get("code_sha256", {}):
            raise ValueError("本版缺少供应方页版式核查记录")
        return
    if marker not in (LEGACY, FORMAT) or policy.get("version", "") >= NOTES_SINCE and marker != FORMAT:
        raise ValueError("供应方页版式核查程序标记不符")
    ledger = sources(graph, read_original, marker)
    nodes, edges = source_graph(ledger)
    if (graph.get("supplier_page_sources") != ledger or
            [n for n in graph["nodes"] if n["type"] == "supplier_page_inspection"] != nodes or
            [e for e in graph["edges"] if e["type"] == "supplier_page_source"] != edges):
        raise ValueError("供应方页所据修订、批注、影像或图谱关系与原件不符")

    if signing and marker == LEGACY:
        accepted = {ref for f in report.get("findings", []) if f["rule"] == "H02" and f["status"] == "ok"
                    for ref in f.get("acceptance_reservations", {}).get("supplier", {}).get("matching_print", [])}
        if accepted:
            current = sources(graph, read_original)
            if any(p["id"] in accepted and p["state"] != "same_print" for p in current["pages"]):
                raise ValueError("旧版验收供应方结论所据的 PDF 另有签名属性待核，请重新审计后签收。")


if __name__ == "__main__":
    targets, execution, format = json.load(sys.stdin)
    result = inspect(Path(sys.argv[1]), {int(k): v for k, v in targets.items()}, execution, format)
    print(json.dumps(result, ensure_ascii=False))
