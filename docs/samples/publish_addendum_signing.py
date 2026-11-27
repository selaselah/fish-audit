"""Publish four fixed watermarked workpapers for supplementary-agreement review.

Use --archives with typeset.zip, current.zip, earlier.zip and payment-R10.zip for offline use.
The two signed originals share a synthetic certificate and identical visible pages.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from zipfile import ZipFile

from publish_batch_version import PROJECT, digest, physical_pages, public_line, publish, require, supports
from pdf_execution import inspect_original
from rule_replay import replay_from_git
from verify import verify

RELEASE = "94c3fbca959a2d1831d4f291b8d29eee033ea27d"
RULE = "2026.11.27.08"
INDEX = "assets/addendum-signing-sample.json"
PAYMENT_INDEX = "assets/addendum-invoice-sample.json"
PAYMENT = ("8c2a157237cf4712856f64225466ee2c", 10, "bace35e61b2a955791e5c6bcbc5f9d2a38570c8730dffb81dab8e02abe633ecb")
EDITIONS = {
    "typeset": ("7e3e44b82d394ed4a9324a0d3be0f8b7", 16, "1478033ccc20027f2b4c05824fa774a32a78fadd0556b5c25eac6e39a8e66b5d"),
    "current": ("9808cf31ac4e4b7d92f0ce016d0a589f", 1, "a27c0ab81752e9cca6d150201d4a709d469ace2229adc4d97aa8fa1c4f294f54"),
    "earlier": ("f9b120301d58400ba532238637ec511f", 1, "ef356e31d956a7039be65f061526aa857c290ca6aea0c897e5ddb8419b5a3e7f"),
}
IMAGE = "assets/batch-version-addendum.jpg"
TYPESET = "showcase/batch-version-addendum.pdf"


def fixed_paper(ident, archive, key):
    case, rev, expected = ident
    require(verify(archive, render_addenda=True)[:2] == (case, rev), key + " 签发资料")
    with ZipFile(archive) as bundle:
        raw = bundle.read("report.json")
        require(digest(raw) == json.loads(bundle.read("manifest.json"))["report_sha256"] == expected, key + " 签发摘要")
        report, journal = json.loads(raw), json.loads(bundle.read("journal.json"))
        require(journal["id"] == report["case_id"] == case and journal["title"].startswith("合成演练 · ")
                and report["policy"]["version"] == RULE and not journal["decisions"] and not journal["referrals"], key + " 水印案")
        graph = report["graph"]
        pages = physical_pages(bundle, report)
    replay = replay_from_git(report, ref=RELEASE, repo=PROJECT, pinned=RELEASE)
    require(replay["state"] == "verified" and replay["commit"] == RELEASE, key + " Git 规则复算")
    require(graph["addendum_pdf_sources"]["format"] == report["policy"]["addendum_pdf"] == "pdf-addendum-execution-v1", key + " 方法")
    return report, pages


def edition(key, archive):
    case, rev, expected = EDITIONS[key]
    report, pages = fixed_paper(EDITIONS[key], archive, key)
    graph = report["graph"]
    record, = graph["addendum_pdf_sources"]["records"]
    unit = record["unit"]
    page = pages[unit]
    doc, original = page["doc"], page["original"]
    require(doc["id"] == record["doc"] == unit and record["id"] == "addendum-pdf/" + unit
            and doc["name"] == "采购合同补充协议.pdf" and doc["sha256"] == record["original_sha256"]
            and record["state"] == key, key + " 补充协议原件")
    technical, signatures = inspect_original(original)
    require(technical == ("unsigned" if key == "typeset" else key) and signatures == record["signatures"], key + " 物理签名范围")
    finding, = [f for f in report["findings"] if f["rule"] == "H02"]
    change = finding["quality_change"]
    require(change["execution"] == [record["id"]] and change["units"] == [unit] and change["state"] == "pending"
            and change["effective_on"] is None and [b["standard"]["state"] for b in finding["batch_acceptance"]["records"]] == ["pending"] * 2,
            key + " 两批验收标准及协议生效日")
    source, = [e for e in graph["edges"] if e["type"] == "addendum_pdf_source" and e["to"] == record["id"]]
    require(source["from"] == unit and source["evidence"] == [doc["id"], unit + "/p1", *record["fields"]], key + " 原件证据边")
    result_links = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
    rows = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "records" and e["evidence"] == [e["to"]]}
    fields = [f for f in graph["facts"] if f["doc"] == unit and
              (f["id"] in record["fields"] or f["field"] in ("previous_criterion", "revised_criterion"))]
    lines = [public_line(f, page, rows) for f in fields]
    supports(finding, [record["id"], *source["evidence"], *(line["ref"] for line in lines)], result_links)
    require(all(line["ref"] in change["evidence"] for line in lines)
            and [line["line"] for line in lines if line["field"].endswith("criterion")] == [9, 10], key + " 同份原件的标准")
    path = TYPESET if key == "typeset" else f"showcase/addendum-signing-{key}.pdf"
    published_doc = dict(id=unit, title=Path(doc["name"]).stem, version=f"合成案例 · R{rev}", page=1,
                         pdf="/" + path, image="/" + IMAGE, source_sha256=doc["sha256"], page_sha256=page["page"]["sha256"], lines=lines)
    published = dict(key=key, case_id=case, rev=rev, report_sha256=expected, finding=finding["id"], state=key, size=len(original),
                     record_id=record["id"], signatures=signatures, doc=published_doc)
    return published, {path: original, IMAGE: page["image"]}


def archive_for(archives, key, ident):
    if archives:
        return archives / (key + ".zip")
    case, rev, _ = ident
    with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:8000/api/cases/{case}/reports/{rev}/bundle", timeout=60) as response:
        return BytesIO(response.read())


def invoice_example(archive):
    case, rev, expected = PAYMENT
    report, pages = fixed_paper(PAYMENT, archive, "新增收票前提")
    graph = report["graph"]
    record, = graph["addendum_pdf_sources"]["records"]
    phase, payment = [f for f in report["findings"] if "payment_change" in f]
    a, b = phase["payment_change"], payment["payment_change"]
    require(phase["rule"] == "H04" and payment["rule"] == "H05" and phase["stage"] == payment["stage"] and
            phase["stage"]["name"] == "第二期" and phase["stage"]["share"] == "60" and
            all(f["status"] == "missing" and c["scope_clear"] and c["applies"] == "pending" and c["effective_on"] is None
                and c["execution"] == [record["id"]] for f, c in ((phase, a), (payment, b))), "合同第二期条件与实付前提")
    require(record["unit"] == record["doc"] == "d04" and record["state"] == "typeset" and not record["signatures"]
            and inspect_original(pages["d04"]["original"]) == ("unsigned", []), "补充协议排印栏与物理签名")
    links = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
    rows = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "records" and e["evidence"] == [e["to"]]}
    docs, files = {}, {}
    for role, unit, name, fields in (
        ("agreement", "d04", "采购合同补充协议", ("previous_payment_stage", "revised_payment_stage", "buyer_sealed_on", "seller_sealed_on", "buyer_signature", "seller_signature")),
        ("bank", "d05", "银行付款回单", ("payment_designation", "transfer_status", "paid_on")),
    ):
        page = pages[unit]
        require(page["doc"]["name"] == name + ".pdf", unit + " 文件名")
        lines = []
        for field in fields:
            fact, = [f for f in graph["facts"] if f["doc"] == unit and f["field"] == field]
            lines.append(public_line(fact, page, rows))
        refs = [r["ref"] for r in lines]
        supports(payment, refs, links)
        if role == "agreement":
            supports(phase, [record["id"], *refs], links)
            require(refs[:4] == [a[k] for k in ("previous_ref","revised_ref","buyer_date_ref","seller_date_ref")]
                    == [b[k] for k in ("previous_ref","revised_ref","buyer_date_ref","seller_date_ref")]
                    and refs[4:] == record["fields"] and record["original_sha256"] == page["doc"]["sha256"], "协议引文与签章观察")
        else:
            require(lines[0]["value"] == phase["stage"]["name"] and lines[1]["value"] == "交易成功" and b["paid_ref"] == refs[2], "回单期次、结果及日期")
        pdf = f"showcase/addendum-invoice-{role}.pdf"
        image = f"assets/addendum-invoice-{role}.jpg"
        files[pdf], files[image] = page["original"], page["image"]
        docs[role] = dict(id=unit, title=name, version=f"合成案例 · R{rev}", page=1, pdf="/"+pdf, image="/"+image,
                          source_sha256=page["doc"]["sha256"], page_sha256=page["page"]["sha256"], lines=lines)
    sample = dict(case_id=case, rev=rev, report_sha256=expected, rule_version=RULE, record_id=record["id"], size=pages["d04"]["doc"]["size"],
                  stage=phase["stage"]["name"], share=phase["stage"]["share"],
                  phase=dict(id=phase["id"], status=phase["status"], applies=a["applies"], effective_on=a["effective_on"]),
                  payment=dict(id=payment["id"], status=payment["status"], applies=b["applies"], effective_on=b["effective_on"]),
                  buyer_on=a["buyer_on"], seller_on=a["seller_on"], paid_on=b["paid_on"], documents=docs)
    files[PAYMENT_INDEX] = (json.dumps(sample, ensure_ascii=False, indent=2) + "\n").encode()
    return files


def build(archives):
    files, samples = {}, []
    for key, ident in EDITIONS.items():
        archive = archive_for(archives, key, ident)
        sample, media = edition(key, archive)
        for path, content in media.items():
            require(path not in files or files[path] == content, key + " 共用实页")
            files[path] = content
        samples.append(sample)
    require(files[samples[2]["doc"]["pdf"][1:]].startswith(files[samples[1]["doc"]["pdf"][1:]]), "已签版本与签后增量修订")
    require(files[IMAGE] == (PROJECT / "frontend" / IMAGE).read_bytes() and files[TYPESET] == (PROJECT / "frontend" / TYPESET).read_bytes(),
            "与已公开水印原件和页图逐字节相同")
    files[INDEX] = (json.dumps(dict(rule_version=RULE, editions=samples), ensure_ascii=False, indent=2) + "\n").encode()
    files.update(invoice_example(archive_for(archives, "payment-R10", PAYMENT)))
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build(args.archives)
    publish(files, PROJECT / "frontend", args.check)
    print(f"{'已核验' if args.check else '已导出'} {len(files)} 个静态文件 · /{INDEX}")
