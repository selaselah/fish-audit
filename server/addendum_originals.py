"""Check the Word or photographed supplementary agreement behind a proposed change."""

import original_records as originals
from contract_comments import line_key


FORMAT = "addendum-original-execution-v1"
SINCE = (2026, 11, 27, 9)
KEY = "addendum_original_sources"
FAMILY = originals.Family("addendum", ("contract_addendum",), "补充协议", "补充协议原件签署凭证",
                          ("buyer_signature", "seller_signature"), FORMAT, compare=line_key)
DETAIL = {
    "word_text": "补充协议 Word 打印页仅见排印文字，请取得双方签署的定稿或对应签署记录。",
    "word_visual": "补充协议 Word 打印页含图形或其他版面元素，请对照双方签章及签署版本。",
    "word_review": "补充协议 Word 的批注、修订或审阅范围待核，请核对双方签署的最终条款。",
    "photo": "补充协议为上传影像，请对照双方签署的原件核实签章及版本。",
    "review": "补充协议原件的签署依据待核，请核对双方签署的最终版本。",
}


def sources(graph, read_original, read_text):
    return originals.sources(graph, read_original, read_text, FAMILY)


def source_graph(ledger):
    return originals.source_graph(ledger, FAMILY)


def bind(entry, graph, units):
    ledger = graph.get(KEY)
    if not ledger:
        return ""
    records = [r for r in ledger["records"] if r["unit"] in units]
    if not records:
        return ""
    entry["original_execution"] = [r["id"] for r in records]
    refs = [ref for r in records for ref in (r["id"], r["doc"], *(p["ref"] for p in r["pages"]), *r["fields"])]
    entry["evidence"] = list(dict.fromkeys([*entry["evidence"], *refs, *originals.review_refs(records, ledger)]))
    return " ".join(dict.fromkeys(DETAIL[r["state"]] for r in records))


def verify(report, read_original, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("addendum_originals")
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    methods = policy.get("code_sha256", {})
    nodes = [n for n in graph["nodes"] if n["type"] in {"addendum_original_inspection", "addendum_word_review", "addendum_word_comment"}]
    edges = [e for e in graph["edges"] if e["type"].startswith(("addendum_original_", "addendum_word_review_"))]
    if marker is None:
        changes = [c for f in report["findings"] for c in (f.get("quality_change"), f.get("payment_change")) if c]
        if (version >= SINCE or "addendum_originals.py" in methods or KEY in graph or nodes or edges
                or any("original_execution" in c for c in changes)):
            raise ValueError("底稿缺少补充协议 Word 或影像签署核查记录")
        if signing:
            applied = {unit for c in changes if c.get("effective_on") or c.get("state") in ("original", "applied", "by_batch")
                       or c.get("applies") in ("amended", "original") for unit in c.get("units", ())}
            if applied and any(unit["id"] in applied for _, units in originals.filings(graph, FAMILY) for unit in units):
                raise ValueError("旧版选用的协议条款或生效日期依赖待核的 Word 或影像签署凭证，请重审后签收。")
        return
    if (version < SINCE or marker != FORMAT or
            "code_sha256" in policy and not {"addendum_originals.py", "original_records.py"} <= methods.keys()):
        raise ValueError("补充协议原件签署程序或源码摘要不符")
    expected = sources(graph, read_original, read_text)
    if graph.get(KEY) != expected or (nodes, edges) != source_graph(expected):
        raise ValueError("补充协议原件、审阅记录、签章字段或图谱关系不符")
    if signing and expected["records"]:
        cited = {ref for f in report["findings"] if f["rule"] in ("H02", "H03", "H04", "H05", "H06") for ref in f["evidence"]}
        originals.verify_rendered(graph, [r for r in expected["records"] if r["id"] in cited], read_original, FAMILY.label)
