"""Create watermarked bank receipts naming either the failed inspection or the later reinspection."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from contract_milestones import PROFILE
from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
from quality_reinspection import reinspection_records
from release_originals_demo import check_fields
from run import submit

MASTER = "9033c73e1cd89272ec27027d0c45b2b0482b3e9a8c716b6a3a0f20ed11534e29"
BANK = "银行付款回单.pdf"
LABEL = "付款依据验收单号"
CASES = {
    "original": ("复验后付款但回单引用不合格初验单", "YS-92B34462", 21),
    "final": ("第二期回单引用次日前已列合格的复验单", "FY-92B34462", 21),
    "early": ("第二期回单引用三天后才列日期的复验单", "FY-92B34462", 17),
    "same": ("第二期回单和所引复验单列同日", "FY-92B34462", 20),
    "unlocated": ("第二期回单引用未提交的复验单号", "FY-92B34463", 21),
}


def write_receipt(dest, rows, code, day):
    require(len(rows) == 7 and tuple(rows[-1]) == ("付款日期", "2026年9月21日"), "回单母本日期及行数")
    updated = [*rows[:-1], ("付款日期", f"2026年9月{day}日"), (LABEL, code)]
    pdf(dest, dest.stem, updated, font=embedded_font("RetestReference"), spacing=28)


def materials(archive, folder, key):
    title, code, day = CASES[key]
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    if archive is None:
        font = embedded_font("QualityReinspectionCJK")
        for name, rows in sorted(reinspection_records("92B34462", "closed").items()):
            dest = folder / (name + ".pdf")
            if dest.name == BANK:
                write_receipt(dest, rows, code, day)
            else:
                pdf(dest, name, rows, font=font)
            paths.append(dest)
        return title, paths, PROFILE
    with ZipFile(archive) as z:
        raw=z.read("report.json")
        require(digest(raw)==MASTER,"固定水印复验母本")
        p=json.loads(raw)
        for doc in p["graph"]["documents"]:
            unit=doc["id"];data=z.read("originals/"+unit+doc["ext"])
            lines=z.read(f"pages/{unit}/1.txt").decode().splitlines()
            require(doc["pages"]==1 and lines[0]==WATERMARK and digest(data)==doc["sha256"],"原件及水印")
            dest=folder/doc["name"]
            if doc["name"]==BANK:
                require(lines[1] == dest.stem, "回单标题")
                write_receipt(dest, [line.split("：", 1) for line in lines[2:]], code, day)
            else:dest.write_bytes(data)
            paths.append(dest)
    return title,paths,p["policy"]["profile"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,nargs="?",help="可选，用已出具 R8 证据包生成或核字")
    parser.add_argument("folder",type=Path,help="输出五组水印原件的目录")
    parser.add_argument("--run",action="store_true");parser.add_argument("--check-fields",action="store_true")
    args=parser.parse_args()
    if args.check_fields and (not args.run or not args.archive):
        parser.error("按既有底稿核字需要 --run 和已出具 R8 证据包")
    ids={}
    for key in CASES:
        title,paths,profile=materials(args.archive,args.folder/key,key)
        if args.run:
            signature=digest("".join(digest(f.read_bytes()) for f in paths).encode())
            ids[key]=submit("合成演练 · "+title,paths,"retest-receipt-"+signature,profile)
        print(key,ids.get(key) or args.folder/key,flush=True)
    if args.check_fields:
        for key,cid in ids.items():
            title,code,day=CASES[key]
            check_fields(args.archive,key,cid,args.folder/key,case_title=title,master_hash=MASTER,kind="bank_receipt",
                         reviewer="复验回单水印核字",replacement=(BANK,"付款日期",f"2026年9月{day}日"),
                         addition=(BANK,"payment_acceptance_ref",LABEL,code,"middle"),visual_fields=("repaired_on",))
            print(key,"水印原行已核",flush=True)
