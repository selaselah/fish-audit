"""Exercise the same watermarked procurement mandate as plain Word, commented Word and a scan."""

import argparse
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

import pypdfium2 as pdfium
from docx import Document
from docx.oxml.ns import qn
from PIL import Image, ImageOps

from contract_milestones import PROFILE, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from mandates import FIELDS, generate
from quality_reinspection import LABELS, TITLES
from run import BASE, get, post, submit, wait
from word_percentage import save_document, word_file


NAME = "授权委托书"
COMMENT = "签署前请另经采购总监书面批准"
AUTHOR = "合成演练采购复核员"
SCOPE = "代表委托单位签署本采购合同"
CASES = {"word_text": "原生 Word 委托书排印签章", "word_review": "原生 Word 委托书授权行附拟议复核",
         "photo": "委托书水印扫描照片"}
OLD_VERSION = "2026.11.27.03"
FORMAT = "mandate-original-execution-v1"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def workspace(seed):
    return ROOT / "委托书原始载体" / sha256(seed.encode()).hexdigest()[:16]


def save_json(path, value):
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def scan_bytes(master, rows):
    with pdfium.PdfDocument(master) as source_pdf:
        page = source_pdf[0]
        assert page.get_textpage().get_text_bounded().splitlines() == [
            WATERMARK, NAME, *(k + "：" + v for k, v in rows)]
        sheet = page.render(scale=2.5).to_pil().convert("L")
    sheet = ImageOps.expand(ImageOps.colorize(sheet, "#252527", "#fffdf7"), border=18, fill="#c9c7c0")
    out = BytesIO()
    sheet.rotate(0.55, Image.Resampling.BICUBIC, expand=True, fillcolor="#c9c7c0").save(out, "JPEG", quality=94)
    return out.getvalue()


def visible_regions(path, rows):
    # Read ink bands on this actual JPEG. Amendments accept only a coarse page third.
    with Image.open(path) as photo:
        width, height = photo.size
        ink = photo.convert("L").crop((width // 20, 0, width * 19 // 20, height)).point(lambda v: 255 if v < 128 else 0)
        density = ink.resize((1, height), Image.Resampling.BOX).tobytes()
    bands = []
    for y, dark in enumerate(density):
        if dark > 1:
            if bands and y - bands[-1][1] <= 9:
                bands[-1][1] = y
            else:
                bands.append([y, y])
    content = [WATERMARK, NAME, None, *(k + "：" + v for k, v in rows)]
    return {line: third((top + bottom) / (2 * height)) for line, (top, bottom) in zip(content, bands, strict=True) if line}


def third(y):
    return "top" if y < 1/3 else "bottom" if y >= 2/3 else "middle"


def materials(seed):
    base = workspace(seed)
    manifest = base / "inputs.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for mode, hashes in data["originals"].items():
            assert {n: digest(base / mode / n) for n in hashes} == hashes
        return base, data
    source, records = generate(seed, "valid")
    rows = records[NAME]
    rows.insert(-1, ("附加限制", "无"))
    originals = {}
    for mode in CASES:
        folder = base / mode
        folder.mkdir(exist_ok=True, parents=True)
        files = [folder / (title + ".pdf") for title in records if title != NAME]
        for path in files:
            shutil.copyfile(source / path.name, path)
        target = folder / (NAME + (".jpg" if mode == "photo" else ".docx"))
        if mode == "word_text":
            word_file(target, rows, NAME)
            document = Document(target)
            anchor, = [p for p in document.paragraphs if p.text == "授权权限：" + SCOPE]
            anchor.runs[0].text = "授权权限："
            anchor.add_run(SCOPE)
            save_document(document, target)
        elif mode == "word_review":
            document = Document(base / "word_text" / target.name)
            anchor, = [p for p in document.paragraphs if p.text == "授权权限：" + SCOPE]
            note = document.add_comment(anchor.runs[-1], text=COMMENT, author=AUTHOR, initials="YL")
            note._element.set(qn("w:date"), "2026-07-25T03:00:00Z")
            save_document(document, target)
        else:
            master = base / "扫描母版.pdf"
            pdf(master, NAME, rows, font=embedded_font("MandateOriginalScan"))
            target.write_bytes(scan_bytes(master, rows))
        originals[mode] = {p.name: digest(p) for p in [target, *files]}
    data = {"seed": seed, "records": records, "originals": originals}
    save_json(manifest, data)
    return base, data


def upload(base, data):
    receipt = base / "cases.json"
    assigned = json.loads(receipt.read_text()) if receipt.exists() else {}
    for mode, hashes in data["originals"].items():
        if mode not in assigned:
            key = "mandate-original-" + sha256((data["seed"] + mode + "".join(hashes.values())).encode()).hexdigest()
            assigned[mode] = submit("合成演练 · " + CASES[mode], [base / mode / n for n in hashes], key, PROFILE)
            save_json(receipt, assigned)
        print(mode, assigned[mode], flush=True)
    return assigned


def scoped_case(cid, mode, hashes):
    case = get("/api/cases/" + cid)
    if (case["id"] != cid or case["title"] != "合成演练 · " + CASES[mode] or case["profile"] != PROFILE
            or {d["name"]: d["sha256"] for d in case["documents"]} != hashes):
        raise ValueError("演练案件题名、范围或原件清单不符")
    return case


def local_page(base, data, mode, name):
    from reinspection_register import prepare

    path = base / mode / name
    assert digest(path) == data["originals"][mode][name]
    page, = prepare(path, 1, save_images=False)
    rows = data["records"][path.stem]
    if path.suffix == ".jpg":
        assert page["layer"] == {"type": "image", "lines": {}} and not page["text"]
        assert path.read_bytes() == scan_bytes(base / "扫描母版.pdf", rows)
        page["visible_regions"] = visible_regions(path, rows)
    else:
        lines = [normalize(line) for line in page["text"].splitlines()]
        assert lines == [normalize(WATERMARK), normalize(path.stem), *(normalize(k + "：" + v) for k, v in rows)]
        assert COMMENT not in page["text"]
    if path.suffix == ".docx":
        document = Document(path)
        assert [(n.text, n.author) for n in document.comments] == ([(COMMENT, AUTHOR)] if mode == "word_review" else [])
        if mode == "word_review":
            para, = [p for p in document.paragraphs if p.text == "授权权限：" + SCOPE]
            start, = para._p.findall(qn("w:commentRangeStart"))
            end, = para._p.findall(qn("w:commentRangeEnd"))
            ref, = para._p.iter(qn("w:commentReference"))
            note, = document.comments
            assert start.get(qn("w:id")) == end.get(qn("w:id")) == ref.get(qn("w:id")) == str(note.comment_id)
            assert start.getnext().find(qn("w:t")).text == SCOPE and start.getnext().getnext() is end
    return page


def inspect_inputs(base, data):
    hashes = data["originals"]
    common = {n: h for n, h in hashes["word_text"].items() if Path(n).stem != NAME}
    assert len(common) == 4 and all({n: h for n, h in files.items() if Path(n).stem != NAME} == common
                                    for files in hashes.values())
    native = NAME + ".docx"
    assert hashes["word_text"][native] != hashes["word_review"][native]
    pages = {(mode, n): local_page(base, data, mode, n) for mode, files in hashes.items() for n in files}
    assert pages["word_text", native]["sha256"] == pages["word_review", native]["sha256"]
    return pages


def checked_pages(base, data, mode, cid, *, prepared=None, save_preview=False):
    case = scoped_case(cid, mode, data["originals"][mode])
    pages = {}
    for doc in case["documents"]:
        name = doc["name"]
        assert doc["pages"] == 1
        url = f"{BASE}/api/cases/{cid}/documents/{doc['id']}"
        with urlopen(url + "/original", timeout=20) as response:
            assert sha256(response.read()).hexdigest() == doc["sha256"]
        page = prepared[mode, name] if prepared is not None else local_page(base, data, mode, name)
        with urlopen(url + "/pages/1", timeout=20) as response:
            image = response.read()
        assert sha256(image).hexdigest() == page["sha256"]
        pages[doc["id"]] = page
        if save_preview and Path(name).stem == NAME:
            (base / mode / "正式打印页.jpg").write_bytes(image)
    return pages


def checked_report(cid, rev, hashes, pages):
    version = get(f"/api/cases/{cid}/reports/{rev}")
    report = version["report"]
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert rev == version["rev"] and report["case_id"] == cid and sha256(canonical.encode()).hexdigest() == version["sha256"]
    graph = report["graph"]
    assert {d["name"]: d["sha256"] for d in graph["documents"]} == hashes
    assert {n["id"]: n["sha256"] for n in graph["nodes"] if n["type"] == "page"} == {
        doc + "/p1": p["sha256"] for doc, p in pages.items()}
    calls = report["calls"]
    assert len(calls["pages"]) == len(pages) and all(
        c["page"] == 1 and c["page_sha256"] == pages[c["doc"]]["sha256"] for c in calls["pages"])
    for call in [*calls["pages"], *(c["check"] for c in calls["pages"] if c.get("check")), calls["expert"]]:
        assert call["request_format"] == "responses-json-v1" and call["model"] and call["response_id"]
    return version


SIGNATURES = {"buyer_agent_signature", "seller_signature", "grant_signature", "acceptance_signer"}
CORE = {
    "采购合同": {"合同编号", "采购方", "供应方", "采购标的", "签约日期", "实际生效日期", "生效条款", "甲方委托书编号",
               "甲方代理人签字", "乙方签章", "付款条款", "第一期", "第二期", "第三期"},
    "验收报告": {"验收签认"}, "质保期满确认单": {"验收签认"}, "银行付款回单": {"款项用途", "交易状态", "付款日期"},
}


def field_actions(report, pages, records):
    graph = report["graph"]
    labels = {**LABELS, **FIELDS}
    types = {**TITLES, NAME: "power_of_attorney"}
    confirm, corrections = [], []
    for doc in graph["documents"]:
        title = Path(doc["name"]).stem
        page = pages[doc["id"]]
        photo = doc["ext"] == ".jpg"
        lines = page["text"].splitlines()
        rows = [(types[title], title, title)]
        rows.extend((labels[k], v, k + "：" + v) for k, v in records[title] if title == NAME or k in CORE[title])
        facts = [f for f in graph["facts"] if f["doc"] == doc["id"] and f["page"] == 1]
        for field, value, quote in rows:
            matches = [f for f in facts if normalize(f["quote"]) == normalize(quote)
                       or normalize((f.get("source_line") or {}).get("text", "")) == normalize(quote)]
            correct = [f for f in matches if f["field"] == field and normalize(f["value"]) == normalize(value)]
            if correct:
                fact, = correct
                assert fact["source_sha256"] == doc["sha256"] and fact["page_sha256"] == page["sha256"]
                if photo:
                    assert not fact.get("source_line")
                else:
                    loc = fact.get("source_line") or {}
                    if not (loc.get("rects") and normalize(loc["text"]) == normalize(quote)):
                        correct = []
                if correct and fact["status"] in ("anchored", "confirmed", "visual"):
                    if fact["status"] != "confirmed" and (photo or field in SIGNATURES or fact["status"] == "visual"):
                        confirm.append(fact["id"])
                    continue
            if photo:
                assert all(not f.get("source_line") for f in matches)
                region = page["visible_regions"][quote]
                if not matches and sum(k == field for k, _, _ in rows) == 1:
                    matches = [f for f in facts if f["field"] == field and not f.get("source_line")]
            else:
                number, = [i for i, line in enumerate(lines, 1) if normalize(line) == normalize(quote)]
                quote = lines[number - 1]
                rects = page["layer"]["lines"][str(number)]
                y = (min(r[1] for r in rects) + max(r[3] for r in rects)) / 2
                region = third(y)
                if not matches:
                    matches = [f for f in facts if f["field"] == field and not f.get("source_line")
                               and (normalize(f["value"]) == normalize(value) or sum(k == field for k, _, _ in rows) == 1)]
            if len(matches) > 1 or any(f.get("amendment") for f in matches):
                raise ValueError(f"{doc['name']} 的 {quote} 有多个候选或已有补正")
            corrections.append({"doc": doc["id"], "page": 1, "field": field, "value": value, "quote": quote,
                                "region": region, "target": matches[0]["id"] if matches else None})
    return confirm, corrections


def observation(version):
    report = version["report"]
    signed, = [f for f in report["findings"] if f["rule"] == "H01"]
    grant, = [e for e in signed["delegations"] if e["side"] == "buyer"]
    return {"case": report["case_id"], "rev": version["rev"], "report_sha256": version["sha256"],
            "version": report["policy"]["version"], "h01": signed["status"], "delegation": grant["status"],
            "reason": grant["detail"], "h04": [f["status"] for f in report["findings"] if f["rule"] == "H04"],
            "h05": [f["status"] for f in report["findings"] if f["rule"] == "H05"]}


def rule_family(report):
    policy = report["policy"]
    if policy["version"] == OLD_VERSION and "mandate_originals" not in policy:
        return "baseline"
    if tuple(map(int, policy["version"].split("."))) >= (2026, 11, 27, 4) and policy.get("mandate_originals") == FORMAT:
        return "originals"
    raise ValueError("该报告的规则版本与委托书原件程序标记不匹配")


def verify_result(mode, version):
    report = version["report"]
    graph = report["graph"]
    result = observation(version)
    signed, = [f for f in report["findings"] if f["rule"] == "H01"]
    grant, = [e for e in signed["delegations"] if e["side"] == "buyer"]
    seal, = [f for f in graph["facts"] if f["field"] == "grant_signature" and f["status"] == "confirmed"]
    receipt = seal["attestation"]["source_check"]
    assert (receipt["original_sha256"], receipt["page_sha256"]) == (seal["source_sha256"], seal["page_sha256"])
    assert grant["agent"] == "演练林岚" and grant["issued_on"] == "2026-07-25"
    assert (grant["valid_from"], grant["signed_on"], grant["valid_until"]) == ("2026-08-01", "2026-09-01", "2026-09-30")
    phases = [f for f in report["findings"] if f["rule"] == "H04"]
    payment, = [f for f in report["findings"] if f["rule"] == "H05"]
    assert [f["stage"]["share"] for f in phases] == ["30", "60", "10"] and payment["stage"]["name"] == "第二期"
    if mode == "photo":
        assert not seal.get("source_line") and not next(p for p in graph["delegation_coverage"]["pages"] if p["unit"] in grant["units"])["native"]
    assert all(COMMENT not in f["quote"] for f in graph["facts"])
    if rule_family(report) == "baseline":
        assert grant["status"] == ("missing" if mode == "photo" else "ok"), result
    else:
        ledger = graph["mandate_original_sources"]
        assert ledger["format"] == FORMAT
        record, = ledger["records"]
        unit, = grant["units"]
        ident = "mandate-original/" + unit
        assert (record["id"], record["unit"], record["doc"], record["state"]) == (ident, unit, seal["doc"], mode)
        assert record["original_sha256"] == seal["source_sha256"] and seal["id"] in record["fields"]
        page, = record["pages"]
        assert (page["ref"], page["sha256"]) == (seal["doc"] + "/p1", seal["page_sha256"])
        assert grant["status"] == "missing" and grant["mandate_originals"] == [ident]
        assert all(ident in f["evidence"] for f in [grant, signed, *phases, payment])
        assert all(f["status"] != "ok" for f in [signed, *phases, payment])
        notes = [n for d in ledger["documents"] for n in d["notes"]]
        result.update(state=record["state"], proof=ident, original_sha256=record["original_sha256"],
                      page_sha256=page["sha256"], signature_fact=seal["id"])
        if mode == "word_review":
            note, = notes
            assert (note["text"], note["author"]) == (COMMENT, AUTHOR) and note["anchor"]["selected"] == SCOPE
            assert record["notes"] == [note["id"]] and note["id"] in grant["evidence"]
            written, = [f for f in graph["facts"] if f["doc"] == seal["doc"] and f["field"] == "grant_conditions"]
            assert written["value"] == "无" and [(l["field_ref"], l["status"]) for l in grant["limits"]] == [(written["id"], "ok")]
            location = note["location"]
            scope, = [f for f in graph["facts"] if f["doc"] == seal["doc"] and f["field"] == "grant_scope"]
            assert (location["unit"], location["page"], location["line"]) == (unit, 1, 10)
            assert location["line"] == scope["source_line"]["number"] and scope["id"] in location["facts"]
            assert location["page_sha256"] == page["sha256"] and normalize(note["anchor"]["quote"]) == normalize("授权权限：" + SCOPE)
            assert any(e["from"] == ident and e["to"] == note["id"] and e["type"] == "mandate_original_comment"
                       for e in graph["edges"])
            result.update(comment=note["text"], comment_ref=note["id"], line=location["line"], selection=SCOPE)
        else:
            assert not notes and not record["notes"]
    return result


def review_case(base, data, mode, cid, prepared):
    api = "/api/cases/" + cid
    hashes = data["originals"][mode]
    wait(cid)
    pages = checked_pages(base, data, mode, cid, prepared=prepared, save_preview=True)
    while True:
        case = scoped_case(cid, mode, hashes)
        version = checked_report(cid, case["rev"], hashes, pages)
        family = rule_family(version["report"])
        rule = version["report"]["policy"]["version"]
        pin = base / mode / ("baseline.json" if family == "baseline" else f"verified-{rule}.json")
        if pin.exists():
            saved = json.loads(pin.read_text())
            current = verify_result(mode, checked_report(cid, saved["rev"], hashes, pages))
            assert current == saved
            return current
        if case["status"] != "ready" or case["decisions"]:
            raise ValueError("字段核图仅限本次待复核的水印案件")
        confirm, corrections = field_actions(version["report"], pages, data["records"])
        note = {"rev": case["rev"], "reviewer": "水印委托书核图演练",
                "note": "已对照本次合成原件摘要及实际页图，仅确认该栏可见文字。签发人身份和实际用印另待核实。"}
        if confirm:
            post(api + "/attest", {**note, "decision": "confirm", "facts": confirm})
        elif corrections:
            post(api + "/amend", {**note, **corrections[0]})
        else:
            result = verify_result(mode, version)
            save_json(pin, result)
            print(mode, "fixed", json.dumps(result, ensure_ascii=False), flush=True)
            return result
        wait(cid)


def compare(base, data, mode, cid, new_rev):
    hashes = data["originals"][mode]
    pages = checked_pages(base, data, mode, cid)
    saved = json.loads((base / mode / "baseline.json").read_text())
    old = checked_report(cid, saved["rev"], hashes, pages)
    new = checked_report(cid, new_rev, hashes, pages)
    if rule_family(old["report"]) != "baseline" or rule_family(new["report"]) != "originals":
        raise ValueError(mode + " 的新版重审底稿尚未出具")
    assert verify_result(mode, old) == saved
    current = verify_result(mode, new)
    receipts = [next(f["attestation"]["source_check"] for f in v["report"]["graph"]["facts"]
                     if f["field"] == "grant_signature") for v in (old, new)]
    assert receipts[0] == receipts[1]
    return {"mode": mode, "before": saved, "after": current,
            "signature_checked_at_rev": receipts[0]["rev"],
            "url": f"{BASE}/workpaper/{cid}?rev={current['rev']}"}


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("本演练需要启用 Python 断言以验证原件与水印。")
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seed", default="watermarked-mandate-originals-20261127-local-baseline")
    action = cli.add_mutually_exclusive_group()
    action.add_argument("--run", action="store_true", help="上传三组、按可见文字核图并验证服务器当前出具的 .03 或 .04+ 版本")
    action.add_argument("--check", "--verify", nargs=2, metavar=("MODE", "REV"), help="只读复查已有演练案件的指定版本")
    action.add_argument("--compare", nargs=3, type=int, metavar=("WORD_TEXT_REV", "WORD_REVIEW_REV", "PHOTO_REV"),
                        help="只读对照本 seed 已固定的 .03 和三份指定的 .04+ 重审版")
    args = cli.parse_args()
    if args.check or args.compare:
        base = workspace(args.seed)
        data = json.loads((base / "inputs.json").read_text())
        cases = json.loads((base / "cases.json").read_text())
    if args.compare:
        print(json.dumps([compare(base, data, mode, cases[mode], rev) for mode, rev in zip(CASES, args.compare, strict=True)],
                         ensure_ascii=False, indent=2))
    elif args.check:
        mode, rev = args.check
        if mode not in CASES or not rev.isdigit() or int(rev) < 1:
            cli.error("请指定 word_text、word_review 或 photo 及正整数版本")
        cid = cases[mode]
        pages = checked_pages(base, data, mode, cid)
        package = checked_report(cid, int(rev), data["originals"][mode], pages)
        print(json.dumps(verify_result(mode, package), ensure_ascii=False))
    else:
        base, data = materials(args.seed)
        prepared = inspect_inputs(base, data)
        print(base, flush=True)
        if args.run:
            cases = upload(base, data)
            with ThreadPoolExecutor(max_workers=len(cases)) as executor:
                runs = [executor.submit(review_case, base, data, mode, cid, prepared) for mode, cid in cases.items()]
                for run in runs:
                    run.result()
