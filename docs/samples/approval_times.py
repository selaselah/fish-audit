"""Add explicitly labeled approval and bank event times to the same watermarked seven-document case."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
from release_originals_demo import check_fields
from run import submit


MASTER = "3a37466c9ba12cddbe8d698646087e247098f18ce2d580b4ac1f3b006f28c5cd"
CASES = {
    "debit_first": ("第二期先扣款后签批", "10:30", "实际扣款时间", "09:15"),
    "approval_first": ("第二期签批早于实际扣款", "09:15", "实际扣款时间", "10:30"),
    "overlap": ("同一分钟签批与扣款", "10:30", "实际扣款时间", "10:30:42"),
    "accepted_only": ("回单时间仅指银行受理", "10:30", "银行受理时间", "09:15"),
}


def new_lines(key):
    _, signed, event, debit = CASES[key]
    return {"付款审批单.pdf":("审批签发时间",signed+"（北京时间）"),
            "银行付款回单.pdf":(event,debit+"（北京时间）")}


def append_printed_rows(archive, folder, additions, master_hash, font):
    folder.mkdir(parents=True,exist_ok=True)
    files = []
    with ZipFile(archive) as z:
        raw=z.read("report.json")
        require(digest(raw)==master_hash,"已核对的水印母本")
        report=json.loads(raw)
        for doc in report["graph"]["documents"]:
            name,unit=doc["name"],doc["id"]
            original=z.read("originals/"+unit+".pdf")
            lines=z.read(f"pages/{unit}/1.txt").decode().splitlines()
            require(doc["pages"]==1 and digest(original)==doc["sha256"] and lines[0]==WATERMARK and lines[1]==Path(name).stem,"水印页及标题")
            path=folder/name
            if name in additions:
                fields=[line.split("：",1) for line in lines[2:]]
                require(all(len(row)==2 for row in fields),"固定母本的打印栏")
                pdf(path,path.stem,[*fields,additions[name]],font=embedded_font(font),spacing=31)
            else:
                path.write_bytes(original)
            files.append(path)
    return files,report["policy"]["profile"]


def materials(archive,folder,key):
    return append_printed_rows(archive,folder,new_lines(key),MASTER,"ApprovalClockCJK")


def check_originals(archive,key,cid,folder):
    fields=("seller","repaired_on","defect_number","repair_number","acceptance_scope")
    changes=[(name,None,label,value,None) for name,(label,value) in new_lines(key).items()]
    check_fields(archive,key,cid,folder,case_title=CASES[key][0],master_hash=MASTER,kind="bank_receipt",
                 reviewer="付款时分水印核字",additions=changes,visual_fields=fields,missing_fields=fields)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,help="同日付款水印 R11 证据包")
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--check-fields",action="store_true")
    args=parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run")
    cases={}
    for key in CASES:
        files,profile=materials(args.archive,args.folder/key,key)
        if args.run:
            token=digest("".join(digest(p.read_bytes()) for p in files).encode())
            cases[key]=submit("合成演练 · "+CASES[key][0],files,"approval-clock-"+token,profile)
        print(key,cases.get(key) or args.folder/key,flush=True)
    if args.check_fields:
        for key,cid in cases.items():
            check_originals(args.archive,key,cid,args.folder/key)
