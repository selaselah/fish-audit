"""Publish only the watermarked agreement and its cited lines from three fixed audit bundles."""

import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from addendum_originals_demo import AGREEMENT, AUTHOR, CASES, COMMENT
from generate import WATERMARK
from publish_batch_version import PROJECT, digest, public_line, publish, require, supports
from documents import render
from rule_replay import replay_from_git
from verify import verify


RELEASE = "02ae30b1d5ac8dd4f84267e781350e451189c5ad"
PINS = {
    "word_text": ("d5f0bf6237204e48849fdf4726d6727e", 5, "6b163db3c1f7a39a2369e7823ea5f8deb4d46fe7b8e9fcd3b826aa1eb1c123e5"),
    "word_review": ("28dbf5e427094fc59f84a32eb13c0fd5", 5, "e9ce394f2ab7245b6141418945aec677dc0b8aadc6daf2e399efa18ea84cc325"),
    "photo": ("6de2c55a4be14c19a0acf0b78218ff66", 2, "ff1ff301fe1841eebcb675838bfa3abd9be7d2f5311530b43cb1509c8c2e4480"),
}
RULE = "2026.11.27.09"
INDEX = "assets/addendum-originals-sample.json"
FIELDS = ("previous_payment_stage", "revised_payment_stage", "buyer_signature", "seller_signature")


def edition(mode, archives):
    case, rev, expected = PINS[mode]
    if archives:
        source = archives / (mode + ".zip")
    else:
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:8000/api/cases/{case}/reports/{rev}/bundle", timeout=90) as response:
            source = BytesIO(response.read())
    require(verify(source, render_addenda=True)[:2] == (case, rev), "签发底稿与原件复算")
    with ZipFile(source) as bundle:
        raw = bundle.read("report.json")
        report, journal = json.loads(raw), json.loads(bundle.read("journal.json"))
        require(expected == digest(raw) == json.loads(bundle.read("manifest.json"))["report_sha256"]
                and journal["title"] == "合成演练 · " + CASES[mode] and journal["id"] == report["case_id"] == case
                and not journal["decisions"] and not journal["referrals"] and report["policy"]["version"] == RULE, mode + " 签发摘要")
        graph = report["graph"]
        ledger = graph["addendum_original_sources"]
        record, = ledger["records"]
        require(ledger["format"] == report["policy"]["addendum_originals"] == "addendum-original-execution-v1"
                and record["state"] == mode and record["doc"] == record["unit"] == "d04"
                and record["id"] == "addendum-original/d04" and len(record["pages"]) == 1, mode + " 原件依据")
        require(len(report["calls"]["pages"]) == 6 and all(c["response_id"] and c["check"]["response_id"] for c in report["calls"]["pages"])
                and report["calls"]["expert"]["response_id"] and report["result"]["human_required"], "逐页解析、复检及专家调用")
        doc, = [d for d in graph["documents"] if d["id"] == record["doc"]]
        physical, = record["pages"]
        original = bundle.read("originals/d04" + doc["ext"])
        image, text = bundle.read("pages/d04/1.jpg"), bundle.read("pages/d04/1.txt")
        source_hash, page_hash = digest(original), digest(image)
        require(doc["name"] == AGREEMENT + doc["ext"] and len(original) == doc["size"] and doc["pages"] == 1
                and doc["sha256"] == record["original_sha256"] == source_hash and physical["sha256"] == page_hash
                and physical["ref"] == "d04/p1", "补充协议归属")
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / ("source" + doc["ext"])
            path.write_bytes(original)
            render(path, folder, 1)
            page, = json.loads((folder / "manifest.json").read_text())
            require((folder / "1.jpg").read_bytes() == image and text == page["text"].encode(), "补充协议原件独立重绘")
    result = replay_from_git(report, ref=RELEASE, repo=PROJECT, pinned=RELEASE)
    require(result["state"] == "verified" and result["commit"] == RELEASE, "可信 Git 规则复算")
    finding, = [f for f in report["findings"] if f["rule"] == "H03"]
    change = finding["payment_change"]
    links = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
    require(change["original_execution"] == [record["id"]] and change["applies"] == "pending" and change["effective_on"] is None
            and finding["status"] == "missing" and record["unit"] in change["units"] and record["unit"] in finding["scope"],
            "付款变更结论")
    supports(finding, [record["id"], "d04", physical["ref"], *record["fields"], *record["notes"]], links)
    facts = [f for f in graph["facts"] if f["doc"] == "d04"]
    files, lines, notes = {}, [], []
    if mode == "photo":
        photo = "assets/addendum-invoice-agreement.jpg"
        require(not text and physical["layer"] == "image" and not ledger["documents"] and not record["notes"]
                and not record["review"] and not any(f.get("source_line") for f in facts)
                and (PROJECT / "frontend" / photo).read_bytes() == original, "原始水印扫描页")
        original_path, image_path = photo, "assets/addendum-original-scan.jpg"
    else:
        heading = page["text"].splitlines()[:2]
        require(heading[1:] == [AGREEMENT] and "".join(heading[0].split()) == "".join(WATERMARK.split())
                and physical["layer"] == "text" and physical["text_only"], "水印及排印版式")
        word, = ledger["documents"]
        require(word["id"] == record["review"] and word["coverage"] == "complete" and word["original_sha256"] == source_hash, "Word 原包")
        supports(finding, [word["id"]], links)
        records = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "records" and e["evidence"] == [e["to"]]}
        rendered = dict(doc=doc, page=page, lines=page["text"].splitlines())
        for field in FIELDS:
            fact, = [f for f in facts if f["field"] == field]
            supports(finding, [fact["id"]], links)
            require(fact["id"] in change["evidence"], "变更条款引文")
            lines.append(public_line(fact, rendered, records))
        require(record["fields"] == [l["ref"] for l in lines[-2:]] and [l["line"] for l in lines] == [9, 10, 13, 15], "协议原行")
        if mode == "word_review":
            n, = word["notes"]
            loc = n["location"]
            require(n["text"] == COMMENT and n["author"] == AUTHOR and n["anchor"]["selected"] == "且买方收到本合同对应的发票"
                    and record["notes"] == [n["id"]] and not n["shortened"] and loc["unit"] == "d04" and loc["line"] == 10
                    and loc["printed"] == lines[1]["quote"] and loc["page_sha256"] == page_hash and loc["facts"] == [lines[1]["ref"]],
                    "批注正文、原生选区和打印位置")
            notes = [n]
        else:
            require(not word["notes"] and not record["notes"], "排印版本的审阅范围")
        suffix = "commented" if notes else "printed"
        original_path, image_path = "showcase/addendum-original-" + suffix + ".docx", "assets/addendum-original-word.jpg"
        files[original_path] = original
    files[image_path] = image
    review = None if mode == "photo" else {k: word[k] for k in ("coverage","part","part_sha256") if k in word}
    public = dict(key=mode, case_id=case, rev=rev, report_sha256=expected, record_id=record["id"],
                  finding=finding["id"], status=finding["status"], applies=change["applies"], effective_on=change["effective_on"],
                  doc=dict(id=doc["id"], title=AGREEMENT, name=doc["name"], media=record["kind"], page=1, version=f"合成案例 · R{rev}",
                           source_sha256=source_hash, page_sha256=page_hash, original="/" + original_path, image="/" + image_path, lines=lines),
                  notes=notes, review=review)
    return public, files


def build(archives):
    editions, files = [], {}
    for mode in PINS:
        sample, assets = edition(mode, archives)
        for name, content in assets.items():
            require(name not in files or files[name] == content, "两份 Word 打印页逐字节相同")
        files.update(assets)
        editions.append(sample)
    require(len({e["doc"]["source_sha256"] for e in editions}) == 3, "三种不同的提交原件")
    files[INDEX] = (json.dumps(dict(rule_version=RULE, editions=editions), ensure_ascii=False, indent=2) + "\n").encode()
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build(args.archives)
    publish(files, PROJECT / "frontend", args.check)
    print(INDEX, "sha256-" + base64.b64encode(bytes.fromhex(digest(files[INDEX]))).decode())
