"""Rebuild the watermarked cold-cabinet purchase with independently checkable acceptance limits."""
import argparse
from pathlib import Path

from quality_payments import MASTER, check_fields, digest, replace_printed_fields
from run import submit


CASES = {
    "relaxed": ("终验放宽柜温上限，实测仅符合验收单", "验收报告.pdf", "检验依据", "柜温不高于8℃"),
    "stricter": ("终验收紧柜温上限，实测仅符合合同", "采购合同.pdf", "约定验收标准", "柜温不高于8℃"),
    "unit": ("验收单与合同的检验单位不同", "验收报告.pdf", "检验依据", "柜温不高于8mm"),
}
STRICT = {
    "contract_open": ("合同柜温须低于八度，终验实测恰为八度", "柜温低于8℃", "柜温不高于8℃"),
    "receipt_open": ("验收单要求柜温严格低于八度，实测落在合同上限", "柜温不高于8℃", "柜温＜8℃"),
    "inside": ("合同及终验均要求柜温大于七点九九度，实测八度", "柜温大于7.99℃", "柜温大于7.99℃"),
    "rounded": ("柜温严格上限遇到取整读数，原始检测记录待补", "柜温低于8℃", "柜温不高于8℃"),
}
ROUNDING = ("验收报告.pdf","测量精度说明","柜温读数已取整，判定须核对未取整的原始记录")


def scenarios(strict):
    if strict:
        return {key:(title,[("采购合同.pdf","约定验收标准",clause),("验收报告.pdf","检验依据",basis)])
                for key,(title,clause,basis) in STRICT.items()}
    return {key:(title,[(name,field,value)]) for key,(title,name,field,value) in CASES.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("folder",type=Path)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--check-fields",action="store_true")
    parser.add_argument("--strict",action="store_true",help="生成含严格上限、下限或读数取整说明的原件")
    parser.add_argument("--case",help="只生成指定的一组")
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run 提交水印演练")
    ids = {}
    samples = scenarios(args.strict)
    if args.case:
        if args.case not in samples:
            parser.error("该组案例不存在")
        samples={args.case:samples[args.case]}
    for key,(title,edits) in samples.items():
        paths,profile = replace_printed_fields(args.archive,args.folder/key,edits,extra_row=ROUNDING if key=="rounded" else None)
        if args.run:
            token = digest("".join(digest(f.read_bytes()) for f in paths).encode())
            ids[key] = submit("合成演练 · "+title,paths,"inspection-limits-"+token,profile)
        print(key,ids.get(key) or args.folder/key,flush=True)
    if args.check_fields:
        for key,(title,edits) in samples.items():
            check_fields(args.archive,key,ids[key],args.folder/key,case_title=title,master_hash=MASTER,
                         reviewer="检验限值水印核字",replacements=edits,
                         addition=(ROUNDING[0],None,*ROUNDING[1:],"bottom") if key=="rounded" else None,
                         missing_fields=("inspection_basis","acceptance_criteria","measured_result"))
            print(key,"水印原行已核",flush=True)
