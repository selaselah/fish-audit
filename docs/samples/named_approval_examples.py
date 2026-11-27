"""Compare the names printed in the contract and on the approval against a marked installment."""
import argparse
from pathlib import Path

from approval_times import append_printed_rows
from publish_batch_version import digest
from release_originals_demo import check_fields
from run import submit


MASTER = "941671bc7af7c83d08ca39716e0f3b40ab466daec0ad090386910bffccea21cb"
CASES = {
    "listed":("第二期合同点名与签批栏相符","林知行签批","林知行"),
    "different":("第二期审批单列了另一名签批人","林知行签批","顾明远"),
    "partial":("第二期共同签批只列一人","林知行与顾明远共同签批","林知行"),
    "unnamed":("第二期签批栏只写指定人","林知行签批","指定人"),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,help="第二期签批早于实际扣款的水印 R7 证据包")
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--check-fields",action="store_true")
    args=parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run")
    cases={}
    for key,(title,term,signer) in CASES.items():
        additions={"采购合同.pdf":("付款签批约定","第二期验收款须由"+term+"。"),"付款审批单.pdf":("签批人姓名",signer)}
        folder=args.folder/key
        files,profile=append_printed_rows(args.archive,folder,additions,MASTER,"ApprovalNamesCJK")
        if args.run:
            token=digest("".join(digest(p.read_bytes()) for p in files).encode())
            case=submit("合成演练 · "+title,files,"payment-names-"+token,profile)
            cases[key]=(case,additions)
            print(key,case,flush=True)
        else:
            print(key,folder)
    if args.check_fields:
        fields=("seller","repaired_on","defect_number","repair_number","acceptance_scope","defect_closure")
        for key,(cid,additions) in cases.items():
            check_fields(args.archive,key,cid,args.folder/key,case_title=CASES[key][0],master_hash=MASTER,kind="bank_receipt",
                         reviewer="具名签批水印核字",additions=[(name,None,label,value,None) for name,(label,value) in additions.items()],
                         visual_fields=fields,missing_fields=fields)


if __name__=="__main__":
    main()
