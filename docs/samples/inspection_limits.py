"""Rebuild three watermarked, one-line changes to the same cold-cabinet purchase."""
import argparse
from pathlib import Path

from quality_payments import MASTER, check_fields, digest, replace_printed_field
from run import submit


CASES = {
    "relaxed": ("终验放宽柜温上限，实测仅符合验收单", "验收报告.pdf", "检验依据", "柜温不高于8℃"),
    "stricter": ("终验收紧柜温上限，实测仅符合合同", "采购合同.pdf", "约定验收标准", "柜温不高于8℃"),
    "unit": ("验收单与合同的检验单位不同", "验收报告.pdf", "检验依据", "柜温不高于8mm"),
}


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
    for key,(title,name,field,value) in CASES.items():
        paths,profile = replace_printed_field(args.archive,args.folder/key,name,field,value)
        if args.run:
            token = digest("".join(digest(f.read_bytes()) for f in paths).encode())
            ids[key] = submit("合成演练 · "+title,paths,"inspection-limits-"+token,profile)
        print(key,ids.get(key) or args.folder/key,flush=True)
    if args.check_fields:
        for key,(title,name,field,value) in CASES.items():
            check_fields(args.archive,key,ids[key],args.folder/key,case_title=title,master_hash=MASTER,
                         reviewer="检验限值水印核字",replacement=(name,field,value),
                         missing_fields=("inspection_basis","acceptance_criteria","measured_result"))
            print(key,"水印原行已核",flush=True)
