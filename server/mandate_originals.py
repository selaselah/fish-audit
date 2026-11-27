"""Review the submitted Word or image mandate and retain the provenance of its signing fields."""

import original_records as originals
from mandate_execution import depends_on_positive
from pdf_execution import apply_unit_records


FORMAT = "mandate-original-execution-v1"
SINCE = (2026, 11, 27, 4)
FAMILY = originals.Family("mandate", ("power_of_attorney",), "委托书", "委托书原件签发凭证", ("grant_signature",), FORMAT)
DETAIL = {
    "word_text": "委托书 Word 打印页仅见排印文字。请核对委托方签发的原件或对应签署记录。",
    "word_visual": "委托书 Word 页含图形或其他版面元素。请对照签章栏与委托方的签发记录。",
    "word_review": "委托书 Word 的批注、修订或审阅范围待核。请核对定稿及委托方签发依据。",
    "photo": "委托书为上传的影像。请对照原图核实委托方签章、用印或其他签发依据。",
    "review": "委托书原件的签发依据待核。请核对提交版本、签章和签发记录。",
}


def sources(graph, read_original, read_text):
    return originals.sources(graph, read_original, read_text, FAMILY)


def source_graph(ledger):
    return originals.source_graph(ledger, FAMILY)


def review_entries(entries, ledger):
    for entry in entries:
        selected = [r for r in ledger.get("records", ()) if r["unit"] in entry["units"]]
        if not apply_unit_records(entry, selected, "mandate_originals", DETAIL):
            continue
        entry["evidence"] = list(dict.fromkeys([*entry["evidence"], *originals.review_refs(selected, ledger)]))


def verify_rendered(graph, records, read_original):
    originals.verify_rendered(graph, records, read_original, FAMILY.label)


def legacy_records(graph):
    for doc, units in originals.filings(graph, FAMILY):
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
