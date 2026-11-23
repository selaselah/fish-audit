import ctypes
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pypdfium2 as pdfium
from pypdfium2 import raw
from PIL import Image, ImageOps

from config import CaseError, MAX_PAGES, SERVER


Image.MAX_IMAGE_PIXELS = 45_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
MAX_EDGE = 2200
IMAGE_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
                 ".tif": "TIFF", ".tiff": "TIFF"}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_word(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 2000 or sum(member.file_size for member in members) > 80 * 1024**2:
            raise CaseError("Word 解压后的资料超出限制。")
        names = set(archive.namelist())
        if not {"[Content_Types].xml", "word/document.xml"} <= names:
            raise CaseError("资料与 DOCX 格式不符。")
        if any("vbaproject" in name.lower() or "/embeddings/" in name.lower() for name in names):
            raise CaseError("请将含宏或嵌入对象的 Word 另存为 PDF。")
        for name in names:
            if not name.endswith(".rels"):
                continue
            for rel in ElementTree.fromstring(archive.read(name)):
                if rel.get("TargetMode") == "External" and not rel.get("Type", "").endswith("/hyperlink"):
                    raise CaseError("Word 含外部资源，请将资料导出为自包含 PDF。")


def word_pdf(source, target):
    if source.suffix == ".docx":
        check_word(source)
    elif not source.read_bytes().startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise CaseError("资料与 DOC 格式不符。")
    binary = os.getenv("SOFFICE_BIN") or shutil.which("soffice")
    if not binary:
        raise CaseError("Word 转换需要本机 LibreOffice。可安装后重试，或提交 PDF。")
    profile = target / "office-profile"
    profile.mkdir()
    settings = profile / "user"
    settings.mkdir()
    font_file = Path(os.getenv("AUDIT_CJK_FONT", "/System/Library/Fonts/Supplemental/Songti.ttc"))
    if font_file.is_file():
        fonts = settings / "fonts"
        fonts.mkdir()
        (fonts / font_file.name).symlink_to(font_file.resolve())
    (settings / "registrymodifications.xcu").write_text(
        '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '</item></oor:items>', encoding="utf-8")
    subprocess.run([binary, "-env:UserInstallation=" + profile.as_uri(), "--headless",
                    "--nologo", "--norestore", "--convert-to", "pdf:writer_pdf_Export",
                    "--outdir", str(target), str(source)], timeout=75, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = target / (source.stem + ".pdf")
    if not output.is_file() or output.stat().st_size > 80 * 1024**2:
        raise CaseError("Word 转换失败，或生成的 PDF 过大。")
    return output


def check_word_text(source, pages):
    if source.suffix != ".docx":
        return
    with zipfile.ZipFile(source) as archive:
        xml = ElementTree.fromstring(archive.read("word/document.xml"))
        original = "".join(node.text or "" for node in xml.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
    cjk = {char for char in original if "\u3400" <= char <= "\u9fff"}
    converted = set("".join(page["text"] for page in pages))
    if len(cjk) >= 8 and len(cjk & converted) < 0.6 * len(cjk):
        raise CaseError("Word 转页后大量中文缺失，请检查本机中文字体或导出带字体的 PDF。")


def save_page(image, text, number, target):
    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    if image.mode != "RGB":
        flattened = Image.new("RGB", image.size, "white")
        if "A" in image.getbands() or "transparency" in image.info:
            rgba = image.convert("RGBA")
            flattened.paste(rgba, mask=rgba.getchannel("A"))
        else:
            flattened.paste(image.convert("RGB"))
        image = flattened
    path = target / f"{number}.jpg"
    image.save(path, format="JPEG", quality=92, optimize=True)
    return {"number": number, "sha256": digest(path.read_bytes()), "width": image.width,
            "height": image.height, "text": text, "layer": {"type": "image", "lines": {}}}


def layer_type(page):
    left, bottom, right, top = page.get_bbox()
    area = max(1, (right - left) * (top - bottom))
    for obj in page.get_objects():
        if obj.type == raw.FPDF_PAGEOBJ_IMAGE:
            x_min, y_min, x_max, y_max = obj.get_bounds()
            if (x_max - x_min) * (y_max - y_min) >= 0.45 * area:
                return "image_overlay"
        if obj.type != raw.FPDF_PAGEOBJ_TEXT:
            continue
        mode = raw.FPDFTextObj_GetTextRenderMode(obj)
        if mode in (raw.FPDF_TEXTRENDERMODE_INVISIBLE, raw.FPDF_TEXTRENDERMODE_CLIP):
            return "image_overlay"
        if mode == raw.FPDF_TEXTRENDERMODE_FILL:
            colors = [ctypes.c_uint() for channel in range(4)]
            if raw.FPDFPageObj_GetFillColor(obj, *(ctypes.byref(color) for color in colors)):
                red, green, blue, alpha = (color.value for color in colors)
                if alpha < 64 or min(red, green, blue) > 245:
                    return "image_overlay"
    return "text"


def text_geometry(text_page, text, picture, page):
    pos = picture.get_posconv(page)
    lines = {}
    for index, line in enumerate(text.splitlines(), 1):
        if not line.strip() or len(line) > 1000 or index > 600:
            continue
        search = text_page.search(line, match_case=True)
        try:
            match = search.get_next()
            if not match or search.get_next():
                continue
            count = text_page.count_rects(*match)
            if not 1 <= count <= 12:
                continue
            rects = []
            for rect_index in range(count):
                left, bottom, right, top = text_page.get_rect(rect_index)
                first = pos.to_bitmap(left, top)
                last = pos.to_bitmap(right, bottom)
                coords = [min(first[0], last[0]) / picture.width, min(first[1], last[1]) / picture.height,
                          max(first[0], last[0]) / picture.width, max(first[1], last[1]) / picture.height]
                rects.append([round(max(0, min(1, coord)), 5) for coord in coords])
            lines[str(index)] = rects
        finally:
            search.close()
    return lines


def render(source, target, limit):
    pages = []
    if source.suffix in (".heic", ".heif"):
        with source.open("rb") as stream:
            header = stream.read(64)
        if header[4:8] != b"ftyp" or not any(brand in header[8:] for brand in HEIF_BRANDS):
            raise CaseError("资料与 HEIC/HEIF 照片格式不符。")
        sips = shutil.which("sips")
        if not sips:
            raise CaseError("本机缺少 HEIC 转换组件，请导出为 JPEG 或 PDF。")
        if header[8:12] in (b"msf1", b"hevc", b"hevx"):
            raise CaseError("请将照片序列逐张导出为图片后上传。")
        photo = target / "photo.png"
        subprocess.run([sips, "-s", "format", "png", "-Z", str(MAX_EDGE), str(source), "--out", str(photo)],
                       check=True, capture_output=True, timeout=45)
        source = photo
    if source.suffix in IMAGE_FORMATS:
        with Image.open(source) as image:
            if image.format != IMAGE_FORMATS[source.suffix]:
                raise CaseError("图片格式与文件后缀不一致。")
            frames = getattr(image, "n_frames", 1)
            if frames > limit:
                raise CaseError(f"本案资料超过 {MAX_PAGES} 页上限。")
            for index in range(frames):
                image.seek(index)
                pages.append(save_page(ImageOps.exif_transpose(image), "", index + 1, target))
    else:
        pdf_path = word_pdf(source, target) if source.suffix in {".doc", ".docx"} else source
        with pdfium.PdfDocument(pdf_path) as document:
            if not 1 <= len(document) <= limit:
                raise CaseError(f"PDF 为空或本案资料超过 {MAX_PAGES} 页上限。")
            for index in range(len(document)):
                page = document[index]
                width, height = page.get_size()
                if not all(math.isfinite(size) and size >= 1 for size in (width, height)):
                    raise CaseError("PDF 页面尺寸无效。")
                picture = page.render(scale=min(2.6, MAX_EDGE / max(width, height)))
                text_page = page.get_textpage()
                text = text_page.get_text_bounded()
                if len(text) > 160_000:
                    raise CaseError("单页文字层过长，请拆分资料。")
                meta = save_page(picture.to_pil(), text, index + 1, target)
                kind = layer_type(page)
                meta["layer"] = {"type": kind, "lines": text_geometry(text_page, text, picture, page) if kind == "text" else {}}
                pages.append(meta)
                text_page.close()
                picture.close()
                page.close()
    check_word_text(source, pages)
    (target / "manifest.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")


def prepare(source, limit, save_images=True):
    with tempfile.TemporaryDirectory(dir=source.parent) as temp:
        target = Path(temp)
        command = [sys.executable, str(SERVER / "documents.py"), str(source), str(target), str(limit)]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=150)
        except subprocess.TimeoutExpired as error:
            raise CaseError("资料转换超时，可拆分页数后重试。") from error
        if completed.returncode:
            error_file = target / "error.txt"
            message = error_file.read_text() if error_file.exists() else "无法读取资料，请检查文件格式、密码或文件完整性。"
            raise CaseError(message)
        pages = json.loads((target / "manifest.json").read_text())
        if save_images:
            for page in pages:
                name = f"{page['number']}.jpg"
                (target / name).replace(source.parent / name)
        return pages


if __name__ == "__main__":
    try:
        render(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
    except CaseError as error:
        (Path(sys.argv[2]) / "error.txt").write_text(str(error))
        sys.exit(1)
