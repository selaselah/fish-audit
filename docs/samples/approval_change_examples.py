"""Add a dated change of payment approver to an already issued watermarked procurement packet."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from generate import WATERMARK, embedded_font, pdf
from publish_batch_version import digest, require
from release_originals_demo import check_fields
from run import submit


MASTER = "c0e9d5a0ed7c6fc319bc3400026b469040aba166bc629ae226ab4cf964bb1e57"
TITLE = "采购合同补充协议"
CASES = {"before":("签批前一日所记的签批人变更",20), "same":("签批当日所记的签批人变更",21),
         "after":("签批后一日所记的签批人变更",22)}


def materials(archive,folder,key):
    folder.mkdir(parents=True,exist_ok=True)
    with ZipFile(archive) as bundle:
        raw=bundle.read("report.json")
        require(digest(raw)==MASTER,"水印母本与已核 R8 相符")
        report=json.loads(raw);files=[]
        for doc in report["graph"]["documents"]:
            data=bundle.read("originals/"+doc["id"]+".pdf")
            lines=bundle.read(f"pages/{doc['id']}/1.txt").decode().splitlines()
            require(doc["pages"]==1 and digest(data)==doc["sha256"] and lines[0]==WATERMARK,"水印、单页及提交原件")
            path=folder/doc["name"];path.write_bytes(data);files.append(path)
            if doc["name"]=="采购合同.pdf":
                contract=dict(line.split("：",1) for line in lines[2:])
    rows=[("补充协议编号","BC-SP-92B34462"),("原合同编号",contract["合同编号"]),
          *((k,contract[k]) for k in ("采购方","供应方","采购标的")),
          ("变更范围","仅变更第二期验收款签批人，其余条款不变"),("原签批约定",contract["付款签批约定"]),
          ("变更后签批约定","第二期验收款须由顾明远签批。"),("变更适用时点","仅适用于本协议生效后签发的付款审批单"),
          ("协议生效条款","本协议自双方盖章之日起生效"),("甲方签章",contract["甲方签章"]),("乙方签章",contract["乙方签章"]),
          ("甲方盖章日期","2026年9月18日"),("乙方盖章日期",f"2026年9月{CASES[key][1]}日")]
    path=folder/(TITLE+".pdf");pdf(path,TITLE,rows,font=embedded_font("ApproverChangeCJK"),spacing=34)
    return [*files,path],report["policy"]["profile"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,help="第二期审批单列了另一名签批人的水印 R8 证据包")
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--check-fields",action="store_true")
    args=parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run")
    cases={}
    for key,(title,_) in CASES.items():
        folder=args.folder/key
        files,profile=materials(args.archive,folder,key)
        if args.run:
            token=digest("".join(digest(p.read_bytes()) for p in files).encode())
            cases[key]=submit("合成演练 · "+title,files,"approval-change-"+token,profile)
        print(key,cases.get(key) or folder,flush=True)
    if args.check_fields:
        fields=("seller","repaired_on","defect_number","repair_number","acceptance_scope","defect_closure")
        for key,cid in cases.items():
            check_fields(args.archive,key,cid,args.folder/key,case_title=CASES[key][0],master_hash=MASTER,kind="bank_receipt",
                         reviewer="签批变更水印核字",visual_fields=fields,missing_fields=fields)
