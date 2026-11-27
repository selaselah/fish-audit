"""Submit the same watermarked second-instalment agreement as Word, commented Word and a scan."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image

from generate import WATERMARK
from publish_addendum_signing import PAYMENT, fixed_paper
from publish_batch_version import digest, require
from contract_milestones import normalize
from documents import prepare
from run import get, post, submit, wait
from word_percentage import save_document, word_file


CASES = {"word_text": "第二期收票条款 · Word 排印协议", "word_review": "第二期收票条款 · Word 原批注",
         "photo": "第二期收票条款 · 扫描协议"}
COMMENT = "收票条件尚待双方确认，请以签署定稿为准。"
AUTHOR = "演练采购复核员"
AGREEMENT = "采购合同补充协议"


def materials(archive, folder):
    report, pages = fixed_paper(PAYMENT, archive, "第二期收票样本")
    source = pages["d04"]
    lines = source["lines"]
    require(lines[:2] == [WATERMARK, AGREEMENT], "补充协议水印和名称")
    rows = [line.split("：", 1) for line in lines[2:]]
    require(all(len(row) == 2 for row in rows), "协议逐行字段")
    files = {}
    for mode in CASES:
        target = folder / mode
        target.mkdir(exist_ok=True, parents=True)
        ext = ".jpg" if mode == "photo" else ".docx"
        agreement = target / (AGREEMENT + ext)
        if mode == "photo":
            # The physical scanned image retains the full watermarked page, including both signature lines.
            agreement.write_bytes(source["image"])
            with Image.open(BytesIO(source["image"])) as scan:
                require(scan.format == "JPEG", "原始扫描载体")
        else:
            word_file(agreement, rows, AGREEMENT)
            document = Document(agreement)
            label, value = next(r for r in rows if r[0] == "变更后付款条款")
            clause, = [p for p in document.paragraphs if p.text == label + "：" + value]
            before, marker, after = value.partition("且买方收到本合同对应的发票")
            require(bool(marker and after), "拟新增收票条件")
            clause.runs[0].text = label + "：" + before
            selected = clause.add_run(marker)
            clause.add_run(after)
            if mode == "word_review":
                note = document.add_comment(selected, text=COMMENT, author=AUTHOR, initials="YL")
                note._element.set(qn("w:date"), "2026-09-15T02:00:00Z")
            save_document(document, agreement)
        paths = []
        for ident, original in pages.items():
            if ident == "d04":
                paths.append(agreement)
                continue
            path = target / original["doc"]["name"]
            path.write_bytes(original["original"])
            paths.append(path)
        files[mode] = paths
    return report["policy"]["profile"], files


def upload(folder, profile, files):
    cases = {}
    for mode, paths in files.items():
        hashes = [digest(p.read_bytes()) for p in paths]
        key = "addendum-original-" + digest((mode + "".join(hashes)).encode())
        cases[mode] = submit("合成演练 · " + CASES[mode], paths, key, profile)
        print(mode, cases[mode], flush=True)
    (folder / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")


def review_printed_rows(mode, case, paths):
    """Reconcile the printed agreement fields in this watermarked training packet."""
    agreement, = [p for p in paths if p.stem == AGREEMENT]
    page, = prepare(agreement, 1, save_images=False)
    hashes = {p.name: digest(p.read_bytes()) for p in paths}
    api = "/api/cases/" + case
    for _ in range(9):
        report = wait(case)
        detail = get(api)
        require(detail["title"] == "合成演练 · " + CASES[mode] and detail["status"] == "ready" and not detail["decisions"]
                and {d["name"]: d["sha256"] for d in detail["documents"]} == hashes
                and report["case_id"] == case and report["policy"]["version"] == "2026.11.27.09", "本次演练范围")
        graph = report["graph"]
        doc, = [d for d in graph["documents"] if d["name"] == agreement.name]
        ref = doc["id"] + "/p1"
        require(next(n for n in graph["nodes"] if n["id"] == ref)["sha256"] == page["sha256"], "本次演练原页")
        facts = [f for f in graph["facts"] if f["doc"] == doc["id"] and f["page"] == 1]
        note = {"rev": detail["rev"], "reviewer": "水印补充协议核图演练",
                "note": "已核对本次合成演练上传原件及页图，仅记录该栏所见文字。双方用印及最终版本仍待核实。"}
        if mode == "photo":
            if any(r["doc"] == doc["id"] for r in graph["addendum_original_sources"]["records"]):
                break
            # This uploaded JPEG is byte-identical to the marked master page produced in materials().
            title, = [f for f in facts if f["field"] == "contract_addendum" and normalize(f["quote"]) == AGREEMENT
                      and normalize(f["value"]) == AGREEMENT and f["status"] == "visual"]
            post(api + "/attest", {**note, "facts": [title["id"]], "decision": "confirm"})
            continue
        require(page["text"].splitlines()[1] == AGREEMENT and page["layer"]["type"] == "text", "协议原页文字")
        for label, field in (("变更后付款条款", "revised_payment_stage"), ("原付款条款", "previous_payment_stage"),
                             ("甲方签章", "buyer_signature"), ("乙方签章", "seller_signature")):
            number, line = next((i, q) for i, q in enumerate(page["text"].splitlines(), 1) if q.startswith(label + "："))
            value = line.partition("：")[2]
            selected = [f for f in facts if f["field"] == field or normalize(f["quote"]) == normalize(line)]
            require(len(selected) <= 1, "唯一候选 " + label)
            f = selected[0] if selected else {}
            location = f.get("source_line") or {}
            if (f.get("field") == field and f.get("quote") == line and location.get("number") == number
                    and location.get("rects") == page["layer"]["lines"][str(number)] and f["status"] in ("anchored", "confirmed")):
                continue
            require(not f.get("amendment"), label + " 已有补正，须核对")
            bounds = page["layer"]["lines"][str(number)]
            y = (min(r[1] for r in bounds) + max(r[3] for r in bounds)) / 2
            region = "top" if y < 1/3 else "bottom" if y >= 2/3 else "middle"
            post(api + "/amend", {**note, "doc": doc["id"], "page": 1, "target": f.get("id"), "field": field,
                                  "value": value, "quote": line, "region": region})
            break
        else:
            break
    else:
        raise ValueError("演练字段核对次数超出预期")
    print(mode, case, "R" + str(detail["rev"]), flush=True)
    return detail["rev"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="签发的第二期收票 R10 演练包")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-fields", action="store_true", help="在本次水印案中逐项核对打印名目及原行")
    args = parser.parse_args()
    profile, files = materials(args.archive, args.folder)
    if args.run:
        upload(args.folder, profile, files)
    if args.check_fields:
        cases = json.loads((args.folder / "cases.json").read_text())
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks = {mode: pool.submit(review_printed_rows, mode, cases[mode], paths) for mode, paths in files.items()}
            revisions = {key: task.result() for key, task in tasks.items()}
        (args.folder / "revisions.json").write_text(json.dumps(revisions, indent=2) + "\n")
