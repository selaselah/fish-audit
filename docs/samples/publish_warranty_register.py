"""Publish the five watermarked originals and source comparison from the fixed R11.

Use --check to compare every static file. A local copy of R11.zip can be supplied
in place of the fixed localhost download.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from publish_batch_version import PROJECT, digest, physical_pages, public_line, publish, require, supports
from protocol import canonical
from rule_replay import replay_from_git
from verify import verify

CASE = "920ea04963ef4f68905ff87533133fd4"
TITLE = "合成演练 · 两张质保工单中仍有一张待维修"
REV = 11
RULE = "2026.11.27.07"
REPORT_SHA256 = "c36e9da397ef9f131fbc9feb5c7fdf191dbfd48ba8ff4f478b7b5e5402bdefb0"
RELEASE_COMMIT = "9da7b6dde6543953dd3c8003796117f91bfd2c07"
INDEX = "assets/warranty-register-sample.json"
# Ordered (document ID, filename, original SHA-256, page SHA-256) from R9 and R10.
INVENTORY_SHA256 = "079e181a91c1e1700b657ffee9c0e1ad523a924c8d5df3cc666a4c7d8474a172"
TICKET_FIELDS = ("contract_id", "warranty_ticket_id", "warranty_reported_on", "warranty_fault", "warranty_ticket_state")
SHEETS = {
    "contract": ("d04", "采购合同", ("contract_id", "payment_stage", "warranty_period", "warranty_condition")),
    "certificate": ("d02", "质保期满确认单", ("contract_id", "warranty_release", "warranty_defects")),
    "open": ("d01", "质保报修工单", TICKET_FIELDS),
    "closed": ("d03", "质保维修工单", (*TICKET_FIELDS, "warranty_closed_on", "warranty_closed_by")),
    "bank": ("d05", "银行付款回单", ("transfer_amount", "payment_designation", "transfer_status", "paid_on")),
}


def fixed_report(bundle, revision, expected_hash):
    raw = bundle.read("report.json")
    manifest = json.loads(bundle.read("manifest.json"))
    require(manifest["case_id"] == CASE and manifest["revision"] == revision
            and digest(raw) == manifest["report_sha256"] == expected_hash, f"水印演练 R{revision} 底稿")
    report, journal = json.loads(raw), json.loads(bundle.read("journal.json"))
    require(report["case_id"] == journal["id"] == CASE and journal["title"] == TITLE
            and [v["hash"] for v in journal["revisions"] if v["rev"] == revision] == [expected_hash],
            f"R{revision} 案号、标题或版本记录")
    return report, journal


def fixed_pages(bundle, report):
    pages = physical_pages(bundle, report)
    inventory = [[unit, page["doc"]["name"], digest(page["original"]), digest(page["image"])]
                 for unit, page in sorted(pages.items())]
    require(digest(canonical(inventory).encode()) == INVENTORY_SHA256, "六份演练原件及各自归档页")
    return pages


def issued_findings(report):
    phase, = [f for f in report["findings"] if f["rule"] == "H04" and "warranty_check" in f]
    payment, = [f for f in report["findings"] if f["rule"] == "H05" and "warranty_payment" in f]
    require(phase["stage"] == payment["stage"] and phase["stage"]["name"] == "第三期" and phase["stage"]["share"] == "10"
            and phase["warranty_check"] == payment["warranty_check"], "第三期及实际付款的质保依据")
    return phase, payment


def result_links(graph):
    return {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "supports_result" and e["evidence"] == [e["from"]]}


def select_documents(graph, pages, phase, payment, revision):
    records = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "records" and e["evidence"] == [e["to"]]}
    links = result_links(graph)
    files, documents = {}, {}
    for role, (unit, title, fields) in SHEETS.items():
        page = pages[unit]
        require(page["doc"]["name"] == title + ".pdf" and page["lines"][1] == title, unit + " 实页题名")
        lines = []
        for field in fields:
            fact, = [f for f in graph["facts"] if f["doc"] == unit and f["field"] == field
                     and (field != "payment_stage" or f["id"] == phase["stage"]["clause_ref"])]
            line = public_line(fact, page, records)
            if role != "bank":
                supports(phase, [line["ref"]], links)
            # The amount is shown on the bank original. H05 uses its designation, status and date.
            if field != "transfer_amount":
                supports(payment, [line["ref"]], links)
            lines.append(line)
        slug = "warranty-register-" + role
        pdf, image = "showcase/" + slug + ".pdf", "assets/" + slug + ".jpg"
        files[pdf], files[image] = page["original"], page["image"]
        documents[role] = dict(title=title, version=f"合成采购 · R{revision}", page=1, pdf="/" + pdf, image="/" + image,
                               source_sha256=page["doc"]["sha256"], page_sha256=page["page"]["sha256"], lines=lines)
    return documents, files


def ticket_bindings(check, documents):
    by_unit = {ticket["unit"]: ticket for ticket in check["tickets"]}
    require(set(by_unit) == {"d01", "d03"} and len(check["tickets"]) == 2, "两张独立工单")
    bindings = {}
    for role in ("open", "closed"):
        unit = SHEETS[role][0]
        ticket = by_unit[unit]
        rows = {row["field"]: row for row in documents[role]["lines"]}
        refs = {field: row["ref"] for field, row in rows.items()}
        require(ticket["linked"] and not ticket["identity_conflicts"] and all(ticket["refs"][k] == v for k, v in refs.items())
                and ticket["number"] == rows["warranty_ticket_id"]["value"] and ticket["fault"] == rows["warranty_fault"]["value"]
                and ticket["printed_state"] == rows["warranty_ticket_state"]["value"], role + " 工单绑定及书面记载")
        bindings[role] = dict(unit=unit, refs=refs)
    return bindings


def issued_comparison(report, check, documents):
    graph = report["graph"]
    require(report["policy"]["warranty_checks"] == graph["warranty_sources"]["format"] == "contract-warranty-release-v5",
            "书面记载差异的规则与图谱格式")
    finding, = [f for f in report["findings"] if f["rule"] == "H07"]
    difference = finding["warranty_difference"]
    bindings = ticket_bindings(check, documents)
    open_refs = bindings["open"]["refs"]
    certificate = {row["field"]: row["ref"] for row in documents["certificate"]["lines"]}
    contract = {row["field"]: row["ref"] for row in documents["contract"]["lines"]}
    refs = dict(condition=contract["warranty_condition"], confirmation=certificate["warranty_release"],
                defects=certificate["warranty_defects"], ticket_id=open_refs["warranty_ticket_id"],
                reported_on=open_refs["warranty_reported_on"], fault=open_refs["warranty_fault"],
                ticket_state=open_refs["warranty_ticket_state"])
    open_ticket, = [t for t in check["tickets"] if t["unit"] == bindings["open"]["unit"]]
    require(finding["status"] == "risk" and difference["state"] == "record_difference"
            and difference["ticket_unit"] == bindings["open"]["unit"] and difference["release_unit"] == SHEETS["certificate"][0]
            and all(difference[k] == open_ticket[k] for k in ("number", "reported_on", "printed_state"))
            and difference["confirmed_on"] == check["confirmed_on"]
            and difference["refs"] == refs and check["defect_ref"] == refs["defects"], "差异发现与两份原件的绑定")
    supports(finding, [contract["payment_stage"], *refs.values()], result_links(graph))
    edge, = [e for e in graph["edges"] if e["type"] == "warranty_record_difference"]
    require((edge["from"], edge["to"], edge["evidence"]) == (refs["defects"], refs["ticket_state"], finding["evidence"]),
            "确认单原行至待维修工单的差异证据边")
    return dict(id=finding["id"], status=finding["status"], state=difference["state"], ticket_unit=difference["ticket_unit"],
                release_unit=difference["release_unit"], refs=difference["refs"], tickets=bindings)


def build(archive=None):
    if archive is None:
        url = f"http://127.0.0.1:8000/api/cases/{CASE}/reports/{REV}/bundle"
        with build_opener(ProxyHandler({})).open(url, timeout=60) as response:
            archive = BytesIO(response.read())
    with ZipFile(archive) as bundle:
        report, _ = fixed_report(bundle, REV, REPORT_SHA256)
        require(report["policy"]["version"] == RULE and digest(bundle.read("methods/warranty_register.py"))
                == report["policy"]["code_sha256"]["warranty_register.py"], "指定 .07 版本及记载对照程序")
        pages = fixed_pages(bundle, report)
        phase, payment = issued_findings(report)
        documents, files = select_documents(report["graph"], pages, phase, payment, REV)
    require(verify(archive, render_addenda=True)[:2] == (CASE, REV), "R11 物理证据、方法及发现")
    replay = replay_from_git(report, ref=RELEASE_COMMIT, repo=PROJECT, pinned=RELEASE_COMMIT)
    require(replay["state"] == "verified" and replay["commit"] == RELEASE_COMMIT, ".07 Git 复算")
    check = phase["warranty_check"]
    comparison = issued_comparison(report, check, documents)
    by_unit = {ticket["unit"]: ticket for ticket in check["tickets"]}
    period_tickets = {role: {k: by_unit[t["unit"]][k] for k in ("state", "status")}
                      for role, t in comparison["tickets"].items()}
    sample = dict(case_id=CASE, rev=REV, report_sha256=REPORT_SHA256, rule_version=RULE,
                  phase=dict(id=phase["id"], stage=phase["stage"]["name"], status=phase["status"],
                             accepted_on=check["accepted_on"], calendar_end=check["calendar_end"], tickets=period_tickets),
                  payment=dict(id=payment["id"], stage=payment["stage"]["name"], status=payment["status"],
                               paid_on=payment["warranty_payment"]["paid_on"]),
                  comparison=comparison, documents=documents)
    files[INDEX] = (json.dumps(sample, ensure_ascii=False, indent=2) + "\n").encode()
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, help="指定水印案 R11 证据包")
    parser.add_argument("--check", action="store_true", help="重建并逐字节核验十一份公开文件")
    args = parser.parse_args()
    files = build(args.archive)
    publish(files, PROJECT / "frontend", args.check)
    print(f"{'已核验' if args.check else '已导出'} {len(files)} 个静态文件 · /{INDEX}")
