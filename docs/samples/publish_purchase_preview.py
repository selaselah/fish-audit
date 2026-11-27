"""Export the three watermarked source pages used by the public procurement demo."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

from PIL import Image
from generate import WATERMARK

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "server"))
from documents import render

REPORT = "b0100d48118210a67d504c09dfad461ce4daaa5b5e3fc8aad1c78a1321ed15f5"
PAGES = {
    "contract": ("d02", "H01", "missing", ("effect_clause", "buyer_signature", "seller_signature")),
    "acceptance": ("d04", "H02", "issue", ("measured_result", "acceptance_result", "inspection_basis")),
    "transfer": ("d03", "H05", "missing", ("payment_designation", "transfer_status", "paid_on")),
}
ASSETS = PROJECT / "frontend" / "assets"


def webp(image):
    output = BytesIO()
    image.save(output, "WEBP", lossless=True)
    return output.getvalue()


def verify(match, source, detail):
    if not match:
        raise ValueError(f"{source} 校验失败，{detail}")


def publish(archive, check):
    output = {}
    with ZipFile(archive) as bundle:
        raw = bundle.read("report.json")
        manifest = json.loads(bundle.read("manifest.json"))
        if sha256(raw).hexdigest() != REPORT or manifest["report_sha256"] != REPORT or manifest["revision"] != 8:
            raise ValueError("请选择已公开的冷藏柜采购水印演练 R8 证据包")
        report = json.loads(raw)
        graph = report["graph"]
        edges = {(e["type"], e["from"], e["to"], tuple(e["evidence"])) for e in graph["edges"]}
        index = {}
        for slug, (unit, rule, status, fields) in PAGES.items():
            document, = [d for d in graph["documents"] if d["id"] == unit]
            finding, = [f for f in report["findings"] if f["rule"] == rule]
            source = PROJECT / "frontend" / "showcase" / (slug + ".pdf")
            original = bundle.read(f"originals/{unit}.pdf")
            page_id = unit + "/p1"
            page, = [n for n in graph["nodes"] if n["id"] == page_id]
            image = bundle.read(f"pages/{unit}/1.jpg")
            lines = bundle.read(f"pages/{unit}/1.txt").decode().splitlines()
            verify(original == source.read_bytes() and sha256(original).hexdigest() == document["sha256"], slug, "原件不符")
            verify(lines and lines[0] == WATERMARK and sha256(image).hexdigest() == page["sha256"], slug, "水印或页图不符")
            with tempfile.TemporaryDirectory() as temp:
                render(source, Path(temp), 1)
                stored, = json.loads((Path(temp) / "manifest.json").read_text())
            verify(stored["sha256"] == page["sha256"] and stored["text"].splitlines() == lines, slug, "重绘页或文字层不符")
            verify(finding["status"] == status, rule, "发现状态不符")
            public_page = "showcase-" + slug + "-page." + ("png" if slug == "acceptance" else "jpg")
            with Image.open(BytesIO(image)) as original_page:
                if slug == "transfer":
                    output[public_page] = image
                else:
                    verify((ASSETS / public_page).read_bytes() == image, slug, "公开整页与归档字节不同")
                thumb = original_page.copy()
                thumb.thumbnail((420, 600), Image.Resampling.LANCZOS)
                thumb_name = "purchase-" + slug + "-thumb.webp"
                output[thumb_name] = webp(thumb)
                for width in (112, 168):
                    small = original_page.copy()
                    small.thumbnail((width, original_page.height), Image.Resampling.LANCZOS)
                    verify(small.width == width, slug, "窄屏原页缩略尺寸")
                    output[f"purchase-{slug}-thumb-{width}.webp"] = webp(small)
                entry = {"title":Path(document["name"]).stem,"version":"合成采购 · R8","page":1,"pdf":"/showcase/"+source.name,
                         "image":"/assets/"+public_page,"thumb":"/assets/"+thumb_name,"size":list(original_page.size),
                         "source_sha256":document["sha256"],"page_sha256":page["sha256"],"finding":finding["id"],"lines":[]}
                for field in fields:
                    fact, = [f for f in graph["facts"] if f["doc"] == unit and f["page"] == 1 and f["field"] == field]
                    ref, row = fact["id"], fact["source_line"]
                    verify(fact["source_sha256"] == document["sha256"] and fact["page_sha256"] == page["sha256"], ref, "字段摘要不符")
                    verify(fact["status"] in ("anchored","confirmed") and 1 <= row["number"] <= len(lines)
                           and row["text"] == lines[row["number"] - 1], ref, "原行不符")
                    verify(ref in finding["evidence"] and ("supports_result",ref,"finding/"+finding["id"],(ref,)) in edges,
                           ref, "缺少通往该项发现的证据边")
                    verify(("records",page_id,ref,(ref,)) in edges and len(row["rects"]) == 1, ref, "缺少原页位置")
                    rect, = row["rects"]
                    x,y,right,bottom = rect
                    verify(0 <= x < right <= 1 and 0 <= y < bottom <= 1, ref, "裁片超出原页")
                    label,value = row["text"].split("：",1)
                    width,height = original_page.size
                    pixels = [max(0,int(x*width)-4),max(0,int(y*height)-3),
                              min(width,int(right*width)+5),min(height,int(bottom*height)+4)]
                    crop = f"purchase-{slug}-line-{row['number']}.webp"
                    output[crop] = webp(original_page.crop(pixels))
                    entry["lines"].append({"ref":ref,"label":label,"value":value,"line":row["number"],"rects":[rect],
                                           "pixels":pixels,"crop":"/assets/"+crop})
                index[slug] = entry
        output["purchase-preview.json"] = (json.dumps({"revision":8,"report_sha256":REPORT,"documents":index},
                                                      ensure_ascii=False,indent=2)+"\n").encode()
    for name, data in output.items():
        target = ASSETS / name
        if check:
            if target.read_bytes() != data:
                raise ValueError(f"公开采购样张与归档不符 {name}")
        else:
            target.write_bytes(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    publish(args.archive, args.check)
