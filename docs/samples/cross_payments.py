"""Generate and exercise three watermarked payment tasks against the local demo service."""

import argparse
import hashlib
import json
from urllib.request import Request, urlopen

from bank import write_bank_pair
from generate import ROOT
from run import BASE, get, submit, wait


PROFILE = "cn-bank-contract-payment/v1"
ACCOUNT = "0123456789123456"


def check_status(report, expected):
    status = {f["rule"]: f["status"] for f in report["findings"] if f["rule"] in {"B06", "B07"}}
    if status != expected:
        raise AssertionError([(f["rule"], f["status"], f["detail"]) for f in report["findings"] if f["status"] != "ok"])


def exercise(run_id, run):
    namespace = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    folder = ROOT / "10-跨案付款流水" / namespace
    contract, first_ref = "YL-C-"+namespace, "YL-"+namespace+"-A"
    first, second = folder / "首次付款", folder / "另一流水"
    write_bank_pair(first, contract, ACCOUNT, first_ref)
    write_bank_pair(second, contract, ACCOUNT, "YL-"+namespace+"-B", paid_on="2026年10月20日")
    if not run:
        return
    cases = {}
    for kind, label, source in (("base", "首次付款", first), ("same", "同一回单再次提交", first), ("full", "同合同另一笔全额付款", second)):
        title = "合成演练 · "+label+" · "+namespace
        cid = submit(title, sorted(source.glob("*.pdf")), run_id+"-"+kind, PROFILE)
        cases[kind] = cid
        print(label, BASE+"/workpaper/"+cid, flush=True)
        report = wait(cid)
        expected = {"B06": "risk" if kind == "same" else "ok", "B07": "risk" if kind == "full" else "ok"}
        check_status(report, expected)
        if kind != "base":
            matches = report["graph"]["payment_history"]["matches"]
            assert any(m["case_id"] == cases["base"] and m["kind"] == kind and m["decision"] == "approve" for m in matches)
            assert report["result"]["verdict"] == "review"
            continue
        detail = get("/api/cases/"+cid)
        archived = {d["name"]: d["sha256"] for d in detail["documents"]}
        generated = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in first.glob("*.pdf")}
        expected_verdict = "review" if report["policy"].get("performance_checks") else "pass"
        assert detail["title"] == title and archived == generated and report["result"]["verdict"] == expected_verdict
        printed = {f["field"]: f["value"] for f in report["graph"]["facts"] if f["status"] in {"anchored", "confirmed"}}
        assert printed["contract_id"] == contract and printed["transfer_ref"] == first_ref
        assert printed["contract_account"] == printed["payee_account"] == ACCOUNT
        if detail["status"] == "ready":
            payload = {"rev": detail["rev"], "decision": "approve", "reviewer": "合成演练验收",
                       "note": "仅签收本脚本生成的水印回归样本。已比对原文件摘要、合同号、完整账户、流水号及全额结算结果。"}
            req = Request(BASE+"/api/cases/"+cid+"/signoff", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
            with urlopen(req, timeout=20) as response:
                assert response.status == 200
        assert get("/api/cases/"+cid)["decisions"][-1]["decision"] == "approve"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="synthetic-payment-history-v1")
    parser.add_argument("--run", action="store_true", help="上传到本地演示库并签收已通过的合成基线")
    args = parser.parse_args()
    exercise(args.run_id, args.run)
