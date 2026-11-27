"""Reproduce acceptance-payment chronology from the five originals of the watermarked refrigerator purchase."""

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
from release_originals_demo import check_fields
from run import submit


MASTER = "9aa18520ccee07473e9fcab55aedba1b5c4f89442c9ec90484c2b16dd4aea1d4"
CASES = {
    "early": ("柜温超限 · 第二期回单早于终验单一天", "付款日期", "2026年9月19日"),
    "same": ("柜温超限 · 第二期回单与终验单同日", "付款日期", "2026年9月20日"),
    "unassigned": ("柜温超限 · 六万元回单未注明期次", "款项用途", "设备采购款"),
}


def materials(archive, folder, key):
    title, field, value = CASES[key]
    folder.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as pack:
        content = pack.read("report.json")
        require(digest(content) == MASTER, "水印采购 R7 底稿摘要")
        paper = json.loads(content)
        paths = []
        for doc in paper["graph"]["documents"]:
            unit = doc["id"]
            raw = pack.read("originals/"+unit+doc["ext"])
            lines = pack.read(f"pages/{unit}/1.txt").decode().splitlines()
            require(lines[0] == WATERMARK and digest(raw) == doc["sha256"] and doc["pages"] == 1, "原件摘要及水印")
            dest = folder/doc["name"]
            if doc["name"] == "银行付款回单.pdf":
                rows = [line.split("：",1) for line in lines[2:]]
                require(lines[1] == "银行付款回单" and sum(k == field for k,_ in rows) == 1, "回单原行")
                pdf(dest, lines[1], [(k,value if k == field else v) for k,v in rows], font=embedded_font("QualityTransfer"), spacing=28)
            else:
                dest.write_bytes(raw)
            paths.append(dest)
    return title, paths, paper["policy"]["profile"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--check-fields",action="store_true")
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run 提交水印演练")
    ids = {}
    for key in CASES:
        title, paths, profile = materials(args.archive, args.folder/key, key)
        if args.run:
            token = digest("".join(digest(f.read_bytes()) for f in paths).encode())
            ids[key] = submit("合成演练 · "+title, paths, "quality-transfer-"+token, profile)
        print(key, ids.get(key) or args.folder/key, flush=True)
    if args.check_fields:
        for key, cid in ids.items():
            title, field, value = CASES[key]
            check_fields(args.archive,key,cid,args.folder/key,case_title=title,master_hash=MASTER,kind="bank_receipt",
                         reviewer="验收款水印核字",replacement=("银行付款回单.pdf",field,value))
            print(key, "水印原行已核", flush=True)
