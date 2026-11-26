"""Rebuild the expired guarantee-period R2 assets. Pass its saved bundle to run offline.

The fixed PDFs were generated with Arial Unicode.ttf (AUDIT_CJK_FONT) and ReportLab 4.4.9.
The archived page images use the server's PDFium renderer.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

from advance_guarantees import BANK, BASE, CONTRACT, GUARANTEE, PROJECT, RECEIPT, digest, require
from guarantee_periods import FORMAT, SCRATCH, SEED, generate, period_findings, title
from publish_batch_version import publish
from rule_replay import replay_from_git
from verify import verify

CASE_ID = "dcda3682a4994b1f94b35b29fd22dbe5"
REVISION = 2
RULE = "2026.11.27.06"
REPORT_SHA256 = "22d4b33dabdab9443f0a8b741402c685cb0c4576fea089e2bb816782b62a4947"
RELEASE_COMMIT = "1902bfe7f47835f382401b4bb50ea2bedeccc8b5"
INDEX = "assets/guarantee-period-sample.json"
SHEETS = {
    "contract": (CONTRACT, (("receipt_clause", "clause", "clause"), ("clause", "clause", "period_clause"))),
    "guarantee": (GUARANTEE, (("start", "guarantee", "valid_from"), ("end", "guarantee", "valid_until_inclusive"))),
    "receipt": (RECEIPT, (("received", "receipt", "received_on"),)),
    "bank": (BANK, (("paid", "payment", "paid_on"),)),
}


def static_line(row, physical, key, graph, finding):
    reference = row["id"]
    number = row["line"]
    require(type(number) is int and 1 <= number <= len(physical["lines"]), reference + " 未定位")
    source = physical["lines"][number - 1]
    page_id = row["doc"] + "/p1"
    require(reference == f"advance-guarantee/{page_id}/l{number}" and row["unit"] == row["doc"] and row["page"] == 1
            and row["original_sha256"] == physical["original_sha256"] and row["page_sha256"] == physical["page_sha256"]
            and source["text"] == row["quote"] and source["rects"] == row["rects"] and source["rects"], reference + " 原行或矩形不符")
    node, = [n for n in graph["nodes"] if n["id"] == reference]
    require(node["type"] == "advance_guarantee_line" and node["line"] == number and node["label"] == row["quote"]
            and any(e["type"] == "advance_guarantee_source" and e["from"] == page_id and e["to"] == reference
                    and e["evidence"] == [page_id, *row["facts"]] for e in graph["edges"])
            and reference in finding["evidence"] and any(e["type"] == "supports_result" and e["from"] == reference
                    and e["to"] == "finding/" + finding["id"] and e["evidence"] == [reference] for e in graph["edges"]),
            reference + " 与首期实际付款之间缺少出具时的证据边")
    label, value = row["quote"].split("：", 1)
    left, top, right, bottom = zip(*row["rects"])
    return dict(key=key, ref=reference, line=number, label=label, value=value, quote=row["quote"], rects=row["rects"],
                rect=[min(left), min(top), max(right), max(bottom)])


def build(archive=None):
    if archive is None:
        with urlopen(f"{BASE}/api/cases/{CASE_ID}/reports/{REVISION}/bundle", timeout=60) as response:
            archive = BytesIO(response.read())
    files, docs = {}, {}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as bundle, tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
        raw = bundle.read("report.json")
        manifest = json.loads(bundle.read("manifest.json"))
        require(digest(raw) == manifest["report_sha256"] == REPORT_SHA256 and manifest["revision"] == REVISION
                and manifest["case_id"] == CASE_ID, "不是已固定的 expired R2 水印证据包")
        report, journal = json.loads(raw), json.loads(bundle.read("journal.json"))
        require(report["case_id"] == journal["id"] == CASE_ID and journal["title"] == title("expired")
                and any(v["rev"] == REVISION and v["hash"] == REPORT_SHA256 for v in journal["revisions"])
                and report["policy"]["version"] == RULE and report["policy"]["advance_guarantee"] == FORMAT,
                "案件题名、固定版或方法不符")
        for module in ("advance_guarantee.py", "guarantee_period.py"):
            require(digest(bundle.read("methods/" + module)) == report["policy"]["code_sha256"][module], module + " 方法摘要不符")
        folder, sources = generate(SEED, "expired", folder=Path(temp))
        graph = report["graph"]
        inventory = {d["name"]: d for d in graph["documents"]}
        require(set(sources) == set(inventory) and len(inventory) == 4, "四份种子原件不符")
        period_findings(report, "expired", sources)
        finding, = [f for f in report["findings"] if f["rule"] == "H05"]
        period = finding["advance_guarantee"]["period"]
        require(finding["stage"]["name"] == "第一期" and finding["status"] == period["status"] == "risk"
                and period["state"] == "expired", "不是已出具的首期付款有效期风险")
        for slug, (heading, selections) in SHEETS.items():
            name = heading + ".pdf"
            source, doc = sources[name], inventory[name]
            original = bundle.read("originals/" + doc["id"] + ".pdf")
            image = bundle.read(f"pages/{doc['id']}/1.jpg")
            text = bundle.read(f"pages/{doc['id']}/1.txt")
            require(doc["pages"] == 1 and original == (folder / name).read_bytes()
                    and digest(original) == doc["sha256"] == source["original_sha256"] and digest(image) == source["page_sha256"]
                    and digest(text) == source["text_sha256"] and text.decode().splitlines() == [r["text"] for r in source["lines"]],
                    name + " 原件、页图或文字层不符")
            lines = []
            for key, role, field in selections:
                row, = [r for r in period["sources"] if r["doc"] == doc["id"] and r["role"] == role and r["field"] == field]
                lines.append(static_line(row, source, key, graph, finding))
            pdf = "showcase/guarantee-period-" + slug + ".pdf"
            jpg = "assets/guarantee-period-" + slug + ".jpg"
            files[pdf], files[jpg] = original, image
            docs[slug] = dict(title=heading, version="合成采购 · R2", page=1, pdf="/" + pdf, image="/" + jpg,
                              source_sha256=source["original_sha256"], page_sha256=source["page_sha256"], lines=lines)
    cid, rev, _ = verify(archive, render_addenda=True)
    require((cid, rev) == (CASE_ID, REVISION), "固定版核验失败")
    replay = replay_from_git(report, ref=RELEASE_COMMIT, repo=PROJECT, pinned=RELEASE_COMMIT)
    require(replay["state"] == "verified" and replay["commit"] == RELEASE_COMMIT, "指定发布版本规则复算不符")
    index = dict(case_id=CASE_ID, rev=REVISION, report_sha256=REPORT_SHA256, rule_version=RULE, finding=finding["id"],
                 stage=finding["stage"]["name"], state=period["state"], documents=docs)
    files[INDEX] = (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode()
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, help="指定的固定 R2 证据包，可离线运行")
    parser.add_argument("--check", action="store_true", help="重建并逐字节核对所有公开资产")
    args = parser.parse_args()
    files = build(args.archive)
    publish(files, PROJECT / "frontend", args.check)
    print(f"{'已核验' if args.check else '已导出'} {len(files)} 个静态文件 · /{INDEX}")
