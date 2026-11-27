"""Make a scanned acceptance and a Word reinspection from marked Chinese procurement fixtures."""

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from contract_milestones import normalize
from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
from documents import prepare
from quality_reinspection import reinspection_records
from run import get, post, submit, wait
from word_percentage import word_file


CLEAN = ("42400d4c7b5d40b8965a3a2ca69121ea", 8, "2ce676776552778ee386a6a73a1169b912795a959db8be70494158c006548b0d")
CASES = {"scan": "扫描验收单 · 四台冷柜签认", "retest": "整改后复验 · Word 签认定稿"}


def materials(archive, folder):
    with ZipFile(archive) as bundle:
        paper = bundle.read("report.json")
        report = json.loads(paper)
        require(digest(paper) == CLEAN[2] and report["case_id"] == CLEAN[0], "水印采购案固定底稿")
        graph = report["graph"]
        scan = folder / "scan"
        scan.mkdir(parents=True, exist_ok=True)
        scanned = []
        for doc in graph["documents"]:
            unit = doc["id"]
            text = bundle.read("pages/" + unit + "/1.txt").decode()
            require(normalize(WATERMARK) in normalize(text) and doc["pages"] == 1, "单页水印材料")
            raw = bundle.read("originals/" + unit + doc["ext"])
            require(digest(raw) == doc["sha256"], "原件 " + unit)
            path = scan / doc["name"]
            if unit == "d02":
                require(doc["name"] == "验收报告.docx", "Word 验收单")
                raw = bundle.read("pages/d02/1.jpg")
                page = next(n for n in graph["nodes"] if n["id"] == "d02/p1")
                require(digest(raw) == page["sha256"], "验收打印页图")
                path = path.with_suffix(".jpg")
            path.write_bytes(raw)
            scanned.append(path)
    retest = folder / "retest"
    retest.mkdir(parents=True, exist_ok=True)
    records = reinspection_records("BD73615E", "closed")
    files = []
    font = embedded_font("AcceptanceEvidenceCJK")
    for title, rows in records.items():
        if title == "复验报告":
            path = retest / (title + ".docx")
            word_file(path, rows, title)
        else:
            path = retest / (title + ".pdf")
            pdf(path, title, rows, font=font)
        files.append(path)
    return report["policy"]["profile"], {"scan": scanned, "retest": files}


def check_fields(archive, key, case, paths):
    target = next(p for p in paths if p.suffix in (".docx", ".jpg"))
    page, = prepare(target, 1, save_images=False)
    if key == "scan":
        with ZipFile(archive) as bundle:
            require(target.read_bytes() == bundle.read("pages/d02/1.jpg"), "水印 Word 打印页")
            printed = bundle.read("pages/d02/1.txt").decode().splitlines()
        fields = {"acceptance": "验收报告", "acceptance_signer": "验收签认：演练许澄（已签字）"}
    else:
        printed = page["text"].splitlines()
        fields = {"acceptance_signer": "复验签认：演练许澄（已签字）"}
    require(all(normalize(t) in [normalize(s) for s in printed] for t in fields.values()), "标题及签认栏的打印字样")
    api = "/api/cases/" + case
    report, detail = wait(case), get(api)
    require(detail["title"] == "合成演练 · " + CASES[key] and detail["status"] == "ready" and not detail["decisions"]
            and {d["name"]:d["sha256"] for d in detail["documents"]} == {p.name:digest(p.read_bytes()) for p in paths}, "水印演练原件")
    graph = report["graph"]
    doc, = [d for d in graph["documents"] if d["name"] == target.name]
    require(next(n for n in graph["nodes"] if n["id"] == doc["id"]+"/p1")["sha256"] == page["sha256"], "本次演练页图")
    selected = []
    for field, line in fields.items():
        fact, = [f for f in graph["facts"] if f["doc"] == doc["id"] and f["page"] == 1 and f["field"] == field
                 and normalize(f["quote"]) == normalize(line) and normalize(f["value"]) == normalize(line.split("：")[-1])]
        if fact["status"] in ("anchored", "visual"):
            selected.append(fact["id"])
    if selected:
        post(api+"/attest", {"rev":detail["rev"], "reviewer":"水印验收原件演练", "facts":selected, "decision":"confirm",
                             "note":"已比对合成原件及生成页，仅核对栏内可见文字，签认人身份及签认行为留待核实。"})
        wait(case)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="水印 Word 验收单的固定 R8 证据包")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--run", action="store_true", help="通过本机服务上传水印材料并调用模型")
    parser.add_argument("--check-fields", action="store_true", help="对本次水印案的标题或签认栏模拟字段核图，配合 --run 使用")
    args = parser.parse_args()
    profile, groups = materials(args.archive, args.folder)
    for key, paths in groups.items():
        if args.run:
            fingerprint = digest("".join(digest(path.read_bytes()) for path in paths).encode())
            case = submit("合成演练 · " + CASES[key], paths, "acceptance-original-" + fingerprint, profile)
            print(key, case, flush=True)
            if args.check_fields:
                check_fields(args.archive, key, case, paths)
        else:
            print(key, *(p.name for p in paths))
