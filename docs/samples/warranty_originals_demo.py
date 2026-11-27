"""Generate alternative carriers for the same watermarked warranty certificate."""

import argparse
from pathlib import Path
from zipfile import ZipFile

from docx import Document

import publish_warranty_register as master
from generate import WATERMARK
from pdf_signing import signed_copy, later_copy
from publish_batch_version import digest, require
from release_originals_demo import check_fields
from run import submit
from word_percentage import save_document, word_file


CASES = {"current":"质保期满单 · 测试签名覆盖本版", "earlier":"质保期满单 · 签后另存",
         "draft":"质保期满单 · 遗留缺陷待复核批注", "photo":"质保期满单 · 扫描签认栏"}
COMMENT = "风扇维修记录尚未结清。本单为待签稿，请核对复验和关闭凭证。"


def materials(archive, target):
    with ZipFile(archive) as pack:
        report, journal = master.fixed_report(pack, master.REV, master.REPORT_SHA256)
        require(not journal["decisions"] and not journal["referrals"], "未签收的演练母本")
        pages = master.fixed_pages(pack, report)
        unit, title, _ = master.SHEETS["certificate"]
        certificate = pages[unit]
        lines = pack.read(f"pages/{unit}/1.txt").decode().splitlines()
        require(lines[:2] == [WATERMARK, title], "期满确认单的水印与题名")
        rows = [line.split("：",1) for line in lines[2:]]
        require(all(len(row)==2 for row in rows), "确认单的印刷行")
        signed = signed_copy(certificate["original"], "SyntheticWarranty")
        copies = {"current":signed, "earlier":later_copy(signed), "photo":certificate["image"]}
        groups = {}
        for key in CASES:
            folder = target/key
            folder.mkdir(parents=True,exist_ok=True)
            paths = []
            for ident, source in pages.items():
                path = folder/source["doc"]["name"]
                if ident != unit:
                    path.write_bytes(source["original"])
                elif key == "draft":
                    path = path.with_suffix(".docx")
                    word_file(path, rows, title)
                    word = Document(path)
                    paragraph, = [p for p in word.paragraphs if p.text == "质保遗留事项：无未关闭缺陷"]
                    paragraph.clear()
                    paragraph.add_run("质保遗留事项：")
                    selected = paragraph.add_run("无未关闭缺陷")
                    word.add_comment(selected, COMMENT, author="合成演练复核员", initials="YL")
                    save_document(word, path)
                else:
                    path = path.with_suffix(".jpg" if key == "photo" else ".pdf")
                    path.write_bytes(copies[key])
                paths.append(path)
            groups[key] = paths
    return report["policy"]["profile"], groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--check-fields",action="store_true")
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run 提交水印演练")
    profile, groups = materials(args.archive,args.folder)
    ids = {}
    for key, paths in groups.items():
        if args.run:
            token = digest("".join(digest(p.read_bytes()) for p in paths).encode())
            ids[key] = submit("合成演练 · "+CASES[key],paths,"warranty-original-"+token,profile)
            print(key,ids[key],flush=True)
        else:
            print(key,paths[0].parent)
    if args.check_fields:
        for key, case in ids.items():
            check_fields(args.archive,key,case,args.folder/key,case_title=CASES[key],master_hash=master.REPORT_SHA256,
                         kind="warranty",reviewer="质保期满单水印核字")
            print(key,"已按水印原件核字",flush=True)
