"""Recheck two archived first reads of watermarked pages and replay the new image responses offline."""

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from quality_reinspection import CASES, materials
from run import BASE

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from documents import prepare
from graph import build_graph, heading_candidates
from model import FIELDS, VISUAL_CHECK, attach_check, validate
from quality_labels import FORMAT, proposed, verify_report
from verify import sha, verify, verify_request


CASE = "2fba126660fa4336af9940338fbdcf48"
SEED = "synthetic-quality-reinspection-v1"
TARGETS = {"整改记录单.pdf", "复验报告.pdf"}


def readback(bundle, case_report, folder, prior, live):
    checks = {}
    for doc in case_report["graph"]["documents"]:
        if doc["name"] not in TARGETS:
            continue
        doc_id = doc["id"]
        source = folder / doc["name"]
        prefix = f"pages/{doc_id}/1"
        if source.read_bytes() != bundle.read(f"originals/{doc_id}.pdf"):
            raise ValueError("归档原件与重新生成的水印样本不同")
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "sample.pdf"
            pdf.write_bytes(source.read_bytes())
            page, = prepare(pdf, 1)
            image = pdf.with_name("1.jpg")
            if (image.read_bytes() != bundle.read(prefix + ".jpg") or
                    page["text"] != bundle.read(prefix + ".txt").decode() or "无交易效力" not in page["text"]):
                raise ValueError("历史页图、文字层与重新渲染的水印资料不同")
            first = next(t for t in case_report["calls"]["pages"] if (t["doc"], t["page"]) == (doc_id, 1))
            trace = {key: value for key, value in first.items() if key != "check"}
            page.update(doc=doc_id, extraction=trace)
            candidates = proposed(page)
            if len(candidates) != 1 or candidates[0]["field"] != FIELDS["repair_number"]:
                raise ValueError("该版本不具有预期的首次编号分类错误")
            trace["native_candidates"] = heading_candidates(page) + candidates
            if not live and prior is None:
                print(doc["name"], candidates[0]["quote"], "可独立读图复检")
                continue
            if live:
                attach_check(image, trace)
            else:
                trace["check"] = prior[doc_id]
            check = trace["check"]
            originals = [{"index": str(i), "field": FIELDS[raw["field"]], "value": raw["value"], "quote": raw["quote"]}
                         for i, raw in enumerate(first["output"]["facts"], 1)]
            if (check["input"] != originals + trace["native_candidates"] or not check["response_id"] or
                    check.get("instruction") != VISUAL_CHECK or check.get("request_format") != "responses-json-v1"):
                raise ValueError("复检请求与原始候选、视觉核验指令或响应编号不符")
            validate(check["output"], check["schema"])
            verify_request(check, {sha(VISUAL_CHECK.encode()): VISUAL_CHECK}, image.read_bytes())
            graph = build_graph([doc], [page], {})
            verify_report({"policy": {"quality_number_classification": FORMAT}, "graph": graph,
                           "calls": {"pages": [trace]}}, lambda *_: page["text"])
            key = candidates[0]["index"]
            fact = next(f for f in graph["facts"] if f["id"] == f"{doc_id}/p1/f{key[1:]}")
            votes = {row["index"]: row["support"] for row in check["output"]["checks"]}
            changed = fact.get("origin") == "printed_quality_number"
            if changed != (votes[key[1:]] == "conflict" and votes[key] == "clear"):
                raise ValueError("图谱采信结果与两项读图结果不符")
            title = "、".join(graph["documents_by_kind"]) or "标题待核"
            print(doc["name"], fact["quote"], votes[key[1:]], votes[key],
                  "归入整改编号" if changed else "保留待核", title, flush=True)
            checks[doc_id] = check
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, help="可指定此水印案例 R1 的本机证据包")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--run", action="store_true", help="对两页水印原件实际调用模型")
    choice.add_argument("--verify-receipt", type=Path, help="离线复核已有的读图回执")
    args = parser.parse_args()
    if args.bundle:
        archive = args.bundle.read_bytes()
    else:
        with urlopen(f"{BASE}/api/cases/{CASE}/reports/1/bundle", timeout=30) as response:
            archive = response.read()
    if verify(io.BytesIO(archive))[:2] != (CASE, 1):
        raise ValueError("仅支持指定水印案例的首次提取版本")
    folder, _ = materials(SEED, "closed")
    prior = json.loads(args.verify_receipt.read_text()) if args.verify_receipt else None
    with ZipFile(io.BytesIO(archive)) as bundle:
        if json.loads(bundle.read("journal.json"))["title"] != "合成演练 · " + CASES["closed"]:
            raise ValueError("演练标题不符")
        report = bundle.read("report.json")
        source = {"case": CASE, "revision": 1, "report_sha256": sha(report)}
        if prior is not None and prior["source"] != source:
            raise ValueError("读图回执引用了不同的历史底稿")
        checks = readback(bundle, json.loads(report), folder, prior["checks"] if prior else None, args.run)
    if (args.run or prior is not None) and len(checks) != len(TARGETS):
        raise ValueError("读图回执未覆盖两份水印原件")
    if args.run:
        body = json.dumps({"source": source, "checks": checks}, ensure_ascii=False, indent=2).encode()
        receipt = folder / f"编号独立读图-{sha(body)[:16]}.json"
        receipt.write_bytes(body)
        print(receipt)
