"""Prepare watermarked copies of the same supplement with a synthetic PDF signature."""

import argparse
from pathlib import Path
from zipfile import ZipFile

from pdf_signing import later_copy, signed_copy
from publish_batch_version import digest, physical_pages, read_report, require
from pdf_execution import inspect_original
from run import submit


NAMES = {"current": "签名覆盖本版补充协议", "earlier": "补充协议在签署后追加修订"}


def prepare(archive, folder):
    with ZipFile(archive) as bundle:
        report = read_report(bundle, 15)
        pages = physical_pages(bundle, report)
    unit, = report["graph"]["documents_by_kind"]["contract_addendum"]
    require(unit == "d05", "固定版本的补充协议")
    plain = pages[unit]["original"]
    signature = folder / "current" / pages[unit]["doc"]["name"]
    signed = signature.read_bytes() if signature.exists() else signed_copy(plain)
    require(signed.startswith(plain) and inspect_original(signed)[0] == "current", "同一水印原件的演练签名")
    files = {}
    for edition in NAMES:
        paths = []
        dest = folder / edition
        dest.mkdir(parents=True, exist_ok=True)
        for key, page in pages.items():
            name = page["doc"]["name"]
            require(Path(name).name == name, "单份原件名称")
            path = dest / name
            data = page["original"]
            if key == unit:
                data = signed
                if edition == "earlier":
                    data = path.read_bytes() if path.exists() else later_copy(signed)
                    require(data.startswith(signed), "签后追加的同一份补充协议")
                require(inspect_original(data)[0] == edition, "演练签名覆盖范围")
            if path.exists():
                require(path.read_bytes() == data, "已保存的水印演练原件")
            else:
                path.write_bytes(data)
            paths.append(path)
        files[edition] = paths
    return files, signature.name, report["policy"]["profile"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="收紧柜温上限水印案 R15 的证据包")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--submit", action="store_true", help="将两组水印材料分别提交本机审计")
    args = parser.parse_args()
    files, name, profile = prepare(args.archive, args.output)
    for edition, paths in files.items():
        print(edition, len(paths), "份水印资料", flush=True)
        if args.submit:
            sha = digest((args.output / edition / name).read_bytes())
            case = submit("合成演练 · " + NAMES[edition], paths, "addendum-pdf-" + edition + "-" + sha[:22], profile)
            print(edition, case, flush=True)
