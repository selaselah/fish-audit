"""Bind filed Word and image acceptance signatures to their inspection and dependent payments."""

import acceptance_comments
import original_records as originals
from pdf_execution import apply_unit_records


FORMAT = "acceptance-original-execution-v1"
SINCE = (2026, 11, 27, 10)
KEY = "acceptance_original_sources"
FAMILY = originals.Family("acceptance", ("acceptance", "reinspection"), "验收", "验收原件签认凭证",
                          ("acceptance_signer",), FORMAT)
DETAIL = {
    "word_text": "验收 Word 的签认依据待核。打印页仅见排印文字，请取得签认定稿或对应签署记录。",
    "word_visual": "验收 Word 的打印页含图形或其他版面元素，请对照签字位置及签认范围。",
    "word_review": "验收 Word 含批注、修订或待核的审阅层，请核实签认版本及范围。",
    "photo": "验收资料为上传影像，请对照原件核实签认人、签认痕迹及范围。",
    "review": "验收原件的签认依据待核，请取得可核对的验收单及对应签署记录。",
}


def sources(graph, read_original, read_text, reviews):
    return originals.sources(graph, read_original, read_text, FAMILY, reviews=reviews["documents"])


def source_graph(ledger, reviews):
    return originals.source_graph(ledger, FAMILY, reviews=reviews["documents"])


def apply(item, graph, units):
    records = [r for r in graph.get(KEY, {}).get("records", ()) if r["unit"] in units]
    if not apply_unit_records(item, records, "acceptance_originals", DETAIL):
        return False
    refs = originals.review_refs(records, graph["acceptance_word_reviews"])
    item["evidence"] = list(dict.fromkeys([*item["evidence"], *refs]))
    return True


def positive_legacy(graph, findings):
    positives = [f for f in findings if f["status"] == "ok" and f["rule"] in ("H02", "H04", "H05")]
    settled = {r["unit"] for f in findings if f["rule"] == "H02"
               for r in f.get("batch_acceptance", {}).get("records", ()) if r["status"] == "ok"}
    for finding in findings:
        chain = finding.get("reinspection") or {}
        if finding["rule"] == "H02" and chain.get("state") == "closed":
            settled.update(s["unit"] for s in chain["steps"] if s["role"] in ("original", "final"))
    for doc, units in originals.filings(graph, FAMILY):
        for unit in units:
            ident = unit["id"]
            if ident in settled:
                return True
            fields = {f["id"] for f in graph["facts"] if (f.get("unit") or f["doc"]) == ident and f["field"] in FAMILY.fields}
            pages = [unit["page"]] if "source" in unit else range(1, (doc.get("pages") or 0) + 1)
            fields.update(f"{doc['id']}/p{n}" for n in pages)
            if any(ident in f["scope"] and (f["rule"] == "H02" or fields.intersection(f["evidence"])) for f in positives):
                return True
    return False


def verify(report, read_original, read_text, *, signing=False, verified_reviews=None):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("acceptance_originals")
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    methods = policy.get("code_sha256", {})
    nodes = [n for n in graph["nodes"] if n["type"] == "acceptance_original_inspection"]
    edges = [e for e in graph["edges"] if e["type"].startswith("acceptance_original_")]
    if marker is None:
        if (version >= SINCE or "acceptance_originals.py" in methods or KEY in graph or nodes or edges
                or any("acceptance_originals" in f for f in report["findings"])):
            raise ValueError("底稿缺少 Word 或影像验收签认原件凭证")
        if signing and positive_legacy(graph, report["findings"]):
            raise ValueError("旧版验收或期款相符结论依赖 Word 或影像验收签认，请重审后签收。")
        return
    if (version < SINCE or marker != FORMAT or policy.get("acceptance_word_reviews") != acceptance_comments.FORMAT or
            "code_sha256" in policy and not {"acceptance_originals.py", "original_records.py", "acceptance_comments.py"} <= methods.keys()):
        raise ValueError("验收原件签认程序或源码摘要不符")
    # The Word review ledger is shared with the acceptance-comments procedure and has a single set of graph nodes.
    reviews = verified_reviews if verified_reviews is not None else acceptance_comments.verify(report, read_original, read_text)
    expected = sources(graph, read_original, read_text, reviews)
    if (graph.get("acceptance_word_reviews") != reviews or graph.get(KEY) != expected
            or (nodes, edges) != source_graph(expected, reviews)):
        raise ValueError("验收签认原件、审阅记录、签字栏或图谱关系与原件不符")
    if signing and expected["records"]:
        cited = {ref for f in report["findings"] if f["rule"] in ("H02", "H04", "H05", "H06") for ref in f["evidence"]}
        originals.verify_rendered(graph, [r for r in expected["records"] if r["id"] in cited], read_original, FAMILY.label)
