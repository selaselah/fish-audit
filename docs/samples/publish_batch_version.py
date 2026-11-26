"""Export the two issued editions of the watermarked batch-standard case.

Run with server/.venv/bin/python. By default the two fixed archives are read
from localhost. Use --r14 and --r15 for offline archives, or --check to compare
all public files byte for byte without writing them.
"""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unicodedata
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from PIL import Image
from generate import WATERMARK

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "server"))
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
from documents import render

CASE = "7e3e44b82d394ed4a9324a0d3be0f8b7"
TITLE = "合成演练 · 两批之间收紧柜温上限，第二批仍用旧标准"
REPORTS = {
    15: "3b62ab68e3d8a370f8ac6d4349b4af44d0da34edffc1ca94bc8a25516c22ef73",
    14: "eeaa92a4c3d534eb224de7cea10ae63cc5a832baa833157d068ba21226aafcbb",
}
PUBLIC_INDEX = "assets/batch-standard-versions.json"
CHANGE_FIELDS = ("previous_criterion", "revised_criterion", "change_timing", "change_effect_clause",
                 "buyer_sealed_on", "seller_sealed_on")
BATCH_FIELDS = ("accepted_on", "inspection_basis", "measured_result")
SHEETS = (
    ("d04", "contract", "contract", ("acceptance_criteria",)),
    ("d05", "addendum", "addendum", CHANGE_FIELDS),
    ("d01", "acceptance", "first", BATCH_FIELDS),
    ("d02", "acceptance", "second", BATCH_FIELDS),
)


def require(condition, subject):
    if not condition:
        raise ValueError(f"演练包核验失败 · {subject}")


def digest(content):
    return sha256(content).hexdigest()


def pick(record, *keys):
    return {key: record[key] for key in keys}


def fixed_archive(revision):
    url = f"http://127.0.0.1:8000/api/cases/{CASE}/reports/{revision}/bundle"
    with build_opener(ProxyHandler({})).open(url, timeout=60) as response:
        return BytesIO(response.read())


def read_report(bundle, revision):
    manifest = json.loads(bundle.read("manifest.json"))
    raw = bundle.read("report.json")
    expected = REPORTS[revision]
    require(manifest["case_id"] == CASE and manifest["revision"] == revision
            and digest(raw) == manifest["report_sha256"] == expected, f"R{revision} 底稿 SHA-256")
    files = manifest["files"]
    names = {"manifest.json", *(entry["path"] for entry in files)}
    require(names == set(bundle.namelist()) and len(names) == len(bundle.namelist()) == len(files) + 1,
            f"R{revision} 包内目录")
    for entry in files:
        content = bundle.read(entry["path"])
        require(len(content) == entry["bytes"] and digest(content) == entry["sha256"], entry["path"])
    journal = json.loads(bundle.read("journal.json"))
    report = json.loads(raw)
    require(report["case_id"] == journal["id"] == CASE and journal["title"] == TITLE
            and [v["hash"] for v in journal["revisions"] if v["rev"] == revision] == [expected],
            f"R{revision} 案件题名与版本记录")
    return report


def physical_pages(bundle, report):
    graph = report["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    documents = graph["documents"]
    calls = {(call["doc"], call["page"]): call for call in report["calls"]["pages"]}
    require(len(documents) == 6 and set(calls) == {(d["id"], 1) for d in documents}, "六份实页")
    pages = {}
    for doc in documents:
        unit = doc["id"]
        node = nodes[unit + "/p1"]
        require(doc["pages"] == 1 and doc["ext"] == ".pdf", doc["name"])
        original = bundle.read(f"originals/{unit}.pdf")
        image = bundle.read(f"pages/{unit}/1.jpg")
        text = bundle.read(f"pages/{unit}/1.txt")
        require(len(original) == doc["size"] and digest(original) == doc["sha256"] == nodes[unit]["sha256"]
                and digest(image) == node["sha256"] == calls[unit, 1]["page_sha256"]
                and digest(text) == node["text_sha256"], unit + " 原件与归档页")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source.pdf"
            source.write_bytes(original)
            render(source, directory, 1)
            page, = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            require((directory / "1.jpg").read_bytes() == image and page["sha256"] == node["sha256"]
                    and page["text"].encode() == text, unit + " 原件重绘")
        lines = page["text"].splitlines()
        require(lines[0] == WATERMARK and page["layer"]["type"] == "text" and page["layer"]["lines"].get("1"),
                unit + " 实页首行水印")
        pages[unit] = dict(doc=doc, original=original, image=image, lines=lines, page=page)
    return pages


def public_line(fact, page, records):
    unit = page["doc"]["id"]
    ref = fact["id"]
    loc = fact["source_line"]
    number = loc["number"]
    require(fact["doc"] == unit and fact["page"] == 1 and fact["status"] in ("anchored", "confirmed")
            and fact["source_sha256"] == page["doc"]["sha256"] and fact["page_sha256"] == page["page"]["sha256"]
            and (unit + "/p1", ref) in records and 1 <= number <= len(page["lines"]), ref)
    quote = page["lines"][number - 1]
    rects = page["page"]["layer"]["lines"][str(number)]
    require(loc["text"] == quote and rects and loc["rects"] == rects
            and all(0 <= x < right <= 1 and 0 <= y < bottom <= 1 for x, y, right, bottom in rects),
            ref + " 原行与矩形")
    label, value = quote.split("：", 1)
    # The model sometimes transcribes the printed ℃ as two characters, °C.
    require(unicodedata.normalize("NFKC", fact["quote"]) == unicodedata.normalize("NFKC", quote)
            and unicodedata.normalize("NFKC", fact["value"]) == unicodedata.normalize("NFKC", value), ref + " 原文")
    left, top, right, bottom = zip(*rects)
    return dict(ref=ref, field=fact["field"], label=label, value=value, quote=quote, line=number,
                rect=[min(left), min(top), max(right), max(bottom)], rects=rects)


def basis_crop(image, rect):
    with Image.open(BytesIO(image)) as sheet:
        width, height = sheet.size
        left, top, right, bottom = rect
        bounds = (max(0, math.floor(left * width) - 6), max(0, math.floor(top * height) - 4),
                  min(width, math.ceil(right * width) + 6), min(height, math.ceil(bottom * height) + 4))
        buffer = BytesIO()
        sheet.crop(bounds).save(buffer, format="WEBP", lossless=True)
        return buffer.getvalue()


def supports(finding, refs, links):
    for ref in refs:
        require(ref in finding["evidence"] and (ref, "finding/" + finding["id"]) in links,
                ref + " → " + finding["id"])


def documents(graph, pages, phases, acceptance, links):
    facts = {fact["id"]: fact for fact in graph["facts"]}
    records = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "records" and e["evidence"] == [e["to"]]}
    docs, files = [], {}
    for unit, kind, suffix, fields in SHEETS:
        page = pages[unit]
        selected = []
        for field in fields:
            fact, = [f for f in facts.values() if f["doc"] == unit and f["field"] == field]
            selected.append(fact)
        if kind == "contract":
            selected.extend(facts[f["stage"]["clause_ref"]] for f in phases)
        lines = [public_line(fact, page, records) for fact in selected]
        supports(acceptance, [line["ref"] for line in lines], links)
        slug = "batch-version-" + suffix
        pdf, image = "showcase/" + slug + ".pdf", "assets/" + slug + ".jpg"
        files[pdf], files[image] = page["original"], page["image"]
        for line in lines:
            if line["field"] == "inspection_basis":
                crop = "assets/" + slug + "-basis.webp"
                files[crop] = basis_crop(page["image"], line["rect"])
                line["crop"] = "/" + crop
        docs.append(dict(id=unit, kind=kind, title=Path(page["doc"]["name"]).stem, version="合成采购 · R15 / R14",
                         page=1, pdf="/" + pdf, image="/" + image, **pick(page["page"], "width", "height"),
                         source_sha256=page["doc"]["sha256"], page_sha256=page["page"]["sha256"], lines=lines))
    return docs, files


def batch_result(row, phase, lines, comparisons, links, change):
    standard = row["standard"]
    stage = phase["stage"]
    fields = {line["field"]: pick(line, "ref", "value") for line in lines}
    refs = {fields[field]["ref"] for field in BATCH_FIELDS}
    require(row["index"] == stage["batch_index"] and standard["date_ref"] == fields["accepted_on"]["ref"]
            and standard["reading_ref"] == fields["measured_result"]["ref"]
            and standard["effective_on"] == change["effective_on"], row["unit"] + " 批次对应")
    edges = [e for e in comparisons if e["batch"] == row["index"]]
    criterion = standard["criterion_ref"]
    if standard["state"] == "pending":
        require(not edges and criterion is None and standard["criterion"] is None and change["effective_on"] is None,
                row["unit"] + " 适用标准待核")
    else:
        edge, = edges
        require((edge["from"], edge["to"], edge["version"]) == (criterion, standard["reading_ref"], standard["state"])
                and edge["evidence"] == standard["evidence"], row["unit"] + " 读数与适用标准的边")
        refs.add(criterion)
    require(refs <= set(row["evidence"]) and refs <= set(standard["evidence"]), row["unit"] + " 验收依据")
    supports(phase, refs | {stage["clause_ref"]}, links)
    issued = {**pick(row, "index", "status", "detail"),
              "standard": pick(standard, "state", "criterion", "criterion_ref", "date_ref", "reading_ref", "effective_on"),
              "stage": {**pick(stage, "name", "share", "clause", "clause_ref"), **pick(phase, "id", "status", "detail")}}
    return fields, issued


def project_edition(archive, revision):
    with ZipFile(archive) as bundle:
        report = read_report(bundle, revision)
        pages = physical_pages(bundle, report)
    graph = report["graph"]
    acceptance, = [f for f in report["findings"] if f["rule"] == "H02"]
    phases = sorted((f for f in report["findings"] if f["rule"] == "H04" and "batch_index" in f["stage"]),
                    key=lambda f: f["stage"]["batch_index"])
    rows = sorted(acceptance["batch_acceptance"]["records"], key=lambda r: r["index"])
    change = acceptance["quality_change"]
    require([(r["index"], r["unit"]) for r in rows] == [(1, "d01"), (2, "d02")]
            and [f["stage"]["batch_index"] for f in phases] == [1, 2] and change["units"] == ["d05"],
            "两批验收与两期付款条款")
    links = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}
    docs, files = documents(graph, pages, phases, acceptance, links)
    contract, addendum, *receipts = docs
    printed_change = {"original_ref": contract["lines"][0]["ref"],
                      **{line["field"]: pick(line, "ref", "value") for line in addendum["lines"]}}
    clause_refs = {printed_change["original_ref"], *(line["ref"] for line in addendum["lines"])}
    require(clause_refs <= set(change["evidence"]), "七条原标准及协议依据")
    comparisons = [e for e in graph["edges"] if e["type"] == "batch_quality_comparison"]
    printed_rows, issued_rows = [], []
    for row, phase, receipt, clause in zip(rows, phases, receipts, contract["lines"][1:], strict=True):
        require(receipt["id"] == row["unit"], "验收来源归属")
        require((clause["ref"], clause["label"], clause["value"]) ==
                (phase["stage"]["clause_ref"], phase["stage"]["name"], phase["stage"]["clause"]), "本期付款条款原行")
        fields, issued = batch_result(row, phase, receipt["lines"], comparisons, links, change)
        if issued["standard"]["criterion_ref"] is not None:
            criterion_ref = issued["standard"]["criterion_ref"]
            criterion_line, = [line for doc in (contract, addendum) for line in doc["lines"] if line["ref"] == criterion_ref]
            require(unicodedata.normalize("NFKC", criterion_line["value"]) == unicodedata.normalize("NFKC", issued["standard"]["criterion"]),
                    criterion_ref + " 适用值")
        printed_rows.append(dict(index=row["index"], label=receipt["title"].removesuffix("验收报告"),
                                 unit=row["unit"], date=row["date"], **fields))
        issued_rows.append(issued)
    edition = dict(rev=revision, report_sha256=REPORTS[revision], rule_version=report["policy"]["version"],
                   quality_change=pick(change, "state", "detail", "effective_on"), batches=issued_rows)
    return edition, docs, files, printed_change, printed_rows


def build(r14=None, r15=None):
    latest, docs, files, change, rows = project_edition(r15 or fixed_archive(15), 15)
    history, old_docs, old_files, old_change, old_rows = project_edition(r14 or fixed_archive(14), 14)
    require(docs == old_docs and files == old_files and change == old_change and rows == old_rows,
            "R15 与 R14 共用的原件、实页、原行、坐标与证据编号")
    public = dict(case_id=CASE, default_rev=latest["rev"], docs=docs, change=change,
                  batches=rows, editions=[latest, history])
    files[PUBLIC_INDEX] = (json.dumps(public, ensure_ascii=False, indent=2) + "\n").encode()
    return files


def publish(files, root, check):
    for name, content in files.items():
        path = root / name
        if path.is_file() and path.read_bytes() == content:
            continue
        require(not check, name + " 公开文件")
        with tempfile.TemporaryDirectory(dir=path.parent) as temp:
            staged = Path(temp) / path.name
            staged.write_bytes(content)
            staged.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r14", type=Path, help="历史 R14 证据包")
    parser.add_argument("--r15", type=Path, help="默认 R15 证据包")
    parser.add_argument("--check", action="store_true", help="按两个固定底稿重建并比对每个公开文件")
    args = parser.parse_args()
    files = build(args.r14, args.r15)
    publish(files, PROJECT / "frontend", args.check)
    print(f"{'已核验' if args.check else '已生成'} {len(files)} 个静态文件 · R15 / R14 · /{PUBLIC_INDEX}")
