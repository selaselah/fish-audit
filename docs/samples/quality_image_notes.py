"""Exercise a separately printed defect-number qualification on a JPEG page and an image-only PDF."""

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

from reportlab.pdfgen import canvas

from contract_milestones import PROFILE, normalize
from quality_reinspection import materials
from run import BASE, get, post, submit, wait

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from documents import prepare


NUMBER = "缺陷编号：0042"
NOTE = "缺陷编号展示说明：本单仅列尾号"


def image_files(seed):
    folder, _ = materials(seed, "noted")
    target = folder / "影像"
    target.mkdir(exist_ok=True)
    jpeg = target / "复验报告页图.jpg"
    scan = target / "复验报告扫描件.pdf"
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "sample.pdf"
        source.write_bytes((folder / "复验报告.pdf").read_bytes())
        page, = prepare(source, 1)
        lines = set(page["text"].splitlines())
        if not {NUMBER, NOTE} <= lines or "无交易效力" not in page["text"]:
            raise ValueError("生成件的编号、水印或另行印刷的展示说明不符")
        jpeg.write_bytes(source.with_name("1.jpg").read_bytes())
    output = canvas.Canvas(str(scan), pagesize=(595, 842), invariant=1)
    output.drawImage(str(jpeg), 0, 0, width=595, height=842)
    output.showPage()
    output.save()
    return jpeg, scan


def check_image(case_id, source):
    path = "/api/cases/" + case_id
    case = get(path)
    doc, = case["documents"]
    if doc["name"] != source.name or doc["sha256"] != hashlib.sha256(source.read_bytes()).hexdigest():
        raise ValueError("上传的影像与生成件摘要不符")
    report = wait(case_id)
    page, = [n for n in report["graph"]["nodes"] if n["type"] == "page"]
    assert page["layer"] in ("image", "image_overlay") and page["text_sha256"] == hashlib.sha256(b"").hexdigest()
    for field, value, quote in (("other", "本单仅列尾号", NOTE), ("defect_number", "0042", NUMBER)):
        same = [f for f in report["graph"]["facts"] if normalize(f["quote"]) == normalize(quote)]
        if quote == NOTE and same:
            continue
        target = next((f for f in same if f["field"] == field and normalize(f["value"]) == normalize(value)), None)
        body = {"rev": get(path)["rev"], "reviewer": "水印影像演练",
                "note": "对照生成的水印原页与影像摘要，核准所见数字及其展示说明。"}
        if target and target["status"] != "confirmed":
            post(path + "/attest", {**body, "decision": "confirm", "facts": [target["id"]]})
        elif not target:
            if len(same) > 1:
                raise ValueError("同一句印刷原文有多个待核候选")
            post(path + "/amend", {**body, "doc": doc["id"], "page": 1, "field": field, "value": value,
                                   "quote": quote, "region": "bottom", "target": same[0]["id"] if same else None})
        report = wait(case_id)
    hold, = report["graph"]["quality_references"]["holds"]
    assert (hold["value"], hold["field"], hold["lines"]) == ("0042", "defect_number", [])
    assert any(normalize(o["quote"]) == normalize(NOTE) for o in hold["observations"])
    assert any(e["type"] == "incomplete_defect_number" and e["to"] == hold["fact"] for e in report["graph"]["edges"])
    print(source.name, BASE+"/workpaper/"+case_id+f"?rev={get(path)['rev']}&fact="+hold["fact"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="synthetic-quality-image-note-v1")
    args = parser.parse_args()
    queue = []
    for source in image_files(args.run_id):
        if args.run:
            key = args.run_id + "-" + source.suffix[1:]
            cid = submit("合成演练 · 缺陷尾号说明 · "+source.name, [source], key, PROFILE)
            queue.append((cid, source))
        else:
            print(source)
    for cid, source in queue:
        check_image(cid, source)
