"""Create watermarked bank receipts naming either the failed inspection or the later reinspection."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
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


def materials(archive, folder, key):
    title, code, day = CASES[key]
    folder.mkdir(parents=True,exist_ok=True)
    with ZipFile(archive) as z:
        raw=z.read("report.json")
        require(digest(raw)==MASTER,"固定水印复验母本")
        p=json.loads(raw);paths=[]
        for doc in p["graph"]["documents"]:
            unit=doc["id"];data=z.read("originals/"+unit+doc["ext"])
            lines=z.read(f"pages/{unit}/1.txt").decode().splitlines()
            require(doc["pages"]==1 and lines[0]==WATERMARK and digest(data)==doc["sha256"],"原件及水印")
            dest=folder/doc["name"]
            if doc["name"]==BANK:
                require(lines[-1]=="付款日期：2026年9月21日" and len(lines)==9,"回单母本日期及行数")
                rows=[s.split("：",1) for s in lines[2:-1]]+[("付款日期",f"2026年9月{day}日"),(LABEL,code)]
                pdf(dest,lines[1],rows,font=embedded_font("RetestReference"),spacing=28)
            else:dest.write_bytes(data)
            paths.append(dest)
    return title,paths,p["policy"]["profile"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path);parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true");parser.add_argument("--check-fields",action="store_true")
    args=parser.parse_args()
    if args.check_fields and not args.run:parser.error("--check-fields 需要 --run")
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
