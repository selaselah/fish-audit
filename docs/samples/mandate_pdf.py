"""Compare three watermarked written mandates with identical powers and different PDF execution evidence."""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp

from contract_milestones import PROFILE, confirm_printed_records
from generate import WATERMARK, embedded_font, pdf
from mandates import FIELDS, generate
from pdf_signing import later_copy, signed_copy
from quality_reinspection import reconcile_training_pages
from reinspection_register import prepare
from run import get, submit, wait


SCENARIOS = {"typeset": "委托书仅列排印签章", "current": "委托书由自签测试证书签发", "earlier": "签发后另存了一版委托书"}


def verify_case(report, state, digest):
    proof, = report["graph"]["mandate_pdf_sources"]["records"]
    assert (proof["state"], proof["original_sha256"]) == (state, digest)
    if state == "typeset":
        assert proof["signatures"] == []
    else:
        signature, = proof["signatures"]
        coverage = {"current": "ENTIRE_FILE", "earlier": "ENTIRE_REVISION"}[state]
        assert (signature["state"], signature["coverage"]) == (state, coverage)
    finding, = [f for f in report["findings"] if f["rule"] == "H01"]
    entry, = finding["delegations"]
    assert finding["status"] == entry["status"] == "missing"
    assert entry["mandate_execution"] == [proof["id"]]
    refs = {proof["id"], proof["doc"], *proof["fields"], *(p["ref"] for p in proof["pages"])}
    assert refs <= set(entry["evidence"]) <= set(finding["evidence"])
    phases = [f for f in report["findings"] if f["rule"] == "H04"]
    payment, = [f for f in report["findings"] if f["rule"] == "H05"]
    assert [f["stage"]["share"] for f in phases] == ["30", "60", "10"]
    assert all(f["status"] == "missing" and proof["id"] in f["evidence"] for f in [*phases, payment])
    assert report["result"]["verdict"] == "review"


def run(seed, upload):
    generated, records = generate(seed, "valid")
    base = Path(mkdtemp(prefix="签章凭证-", dir=generated))
    name = "授权委托书"
    records[name].insert(-1, ("附加限制", "无"))
    original = base / (name + ".pdf")
    pdf(original, name, records[name], font=embedded_font("SyntheticMandateExecution"))
    raw = original.read_bytes()
    signed = signed_copy(raw, "SyntheticMandateIssuer", reason="Watermarked procurement test only")
    work = []
    print(base, flush=True)
    for state, content in (("typeset", raw), ("current", signed), ("earlier", later_copy(signed))):
        folder = base / state
        folder.mkdir()
        for title, rows in records.items():
            target = folder / (title + ".pdf")
            target.write_bytes(content if title == name else (generated / target.name).read_bytes())
            page, = prepare(target, 1, save_images=False)
            lines = page["text"].splitlines()
            assert lines[0] == WATERMARK and all(key + "：" + value in lines for key, value in rows)
        if upload:
            title = "合成演练 · " + SCENARIOS[state]
            key = "mandate-pdf-" + state + "-" + sha256(seed.encode() + b"\0" + content).hexdigest()
            cid = submit(title, sorted(folder.glob("*.pdf")), key, PROFILE)
            work.append((state, folder, cid, sha256(content).hexdigest()))
            print(state, cid, flush=True)
    for state, folder, cid, digest in work:
        wait(cid)
        reconcile_training_pages(cid, folder, records, case_titles=SCENARIOS.values(), field_labels=FIELDS,
                                 document_types={name: "power_of_attorney"})
        report = confirm_printed_records(cid, folder, records)
        verify_case(report, state, digest)
        print(state, cid, "R" + str(get("/api/cases/" + cid)["rev"]), report["result"]["verdict"], flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seed", required=True)
    cli.add_argument("--run", action="store_true")
    args = cli.parse_args()
    run(args.seed, args.run)
