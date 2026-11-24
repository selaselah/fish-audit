"""Upload the marked sample files, wait for real jobs, and check their findings."""

import argparse
import json
import subprocess
import time
from urllib.request import Request, urlopen

from generate import ROOT, generate_packet, generate_resubmission, main as generate


BASE = "http://127.0.0.1:8000"


def get(path):
    with urlopen(BASE + path, timeout=20) as response:
        return json.load(response)


def post(path, body):
    request = Request(BASE+path,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    with urlopen(request,timeout=30) as response:
        return json.load(response)


def submit(title, files, key, profile=None):
    command = ["curl", "--fail-with-body", "--silent", "--show-error", "-H", "Idempotency-Key: " + key,
               "--form-string", "title=" + title]
    if profile:
        command += ["--form-string", "profile=" + profile]
    for source in files:
        command += ["-F", "files=@" + str(source)]
    body = subprocess.check_output(command + [BASE + "/api/cases"])
    return json.loads(body)["id"]


def wait(case_id):
    until = time.monotonic() + 1800
    while time.monotonic() < until:
        case = get("/api/cases/" + case_id)
        if case["status"] in ("ready", "in_review", "closed"):
            return get(f"/api/cases/{case_id}/reports/{case['rev']}")["report"]
        if case["status"] == "failed":
            raise RuntimeError(case["error"])
        time.sleep(3)
    raise RuntimeError("工作台中仍可查看任务状态。")


def verify(index, report):
    result = report["result"]
    statuses = {(item["rule"], item["status"]) for item in report["findings"]}
    basic_verdict = "review" if report["policy"].get("performance_checks") else "pass"
    if index == 0:
        assert result["verdict"] == basic_verdict and ("M02","ok") in statuses, statuses
    elif index == 1:
        assert result["verdict"] == "reject" and {("I01", "risk"), ("M01", "issue")} <= statuses
        assert any("-2,000.00" in item["detail"] for item in report["findings"])
    elif index == 2:
        assert result["verdict"] == "review" and ("E01", "missing") in statuses
        assert all(fact["status"] in ("visual", "unsupported") for fact in report["graph"]["facts"])
    elif index == 3:
        assert result["verdict"] == "review" and ("M02", "risk") in statuses
        assert any("2 张不同号码发票合计 11,300.00 元" in item["detail"] for item in report["findings"])
    elif index == 4:
        assert result["verdict"] == "reject" and {("T03","issue"), ("T04","risk")} <= statuses
        assert any("差额 150.00 元" in item["detail"] for item in report["findings"])
    elif index == 5:
        assert result["verdict"] == "review" and ("I02", "risk") in statuses
        assert any(row["decision"] == "return" and "YL-FP-038" in row["quote"]
                   for row in report["graph"]["prior_invoices"]), "需先归档已核图的原演练票号"
    elif index == 6:
        graph = report["graph"]
        assert result["verdict"] == basic_verdict and len(graph["documents"]) == 1
        assert [unit["page"] for unit in graph["audit_documents"]] == [1,2,3]
        assert len({fact["page"] for fact in graph["facts"] if fact["field"] == "total" and fact.get("unit")}) == 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="synthetic-procurement-v2")
    parser.add_argument("--include-resubmission", action="store_true", help="加验同票重提；需先归档退回的照片案例")
    parser.add_argument("--include-packet", action="store_true", help="加验三页采购合订 PDF")
    args = parser.parse_args()
    if not ROOT.is_dir():
        generate()
    cases = []
    folders = sorted(folder for folder in ROOT.iterdir() if folder.is_dir() and folder.name[:3] in ("01-", "02-", "03-", "04-", "05-"))
    if args.include_resubmission:
        folders.append(generate_resubmission())
    if args.include_packet:
        folders.append(generate_packet())
    for folder in folders:
        index = int(folder.name[:2]) - 1
        files = sorted(folder.iterdir())
        if index == 2:
            files = [source for source in files if source.suffix == ".pdf"]
        title = "合成演练 · " + folder.name[3:]
        profile = "cn-travel-reimbursement/v1" if index == 4 else None
        case_id = submit(title, files, args.run_id + "-" + str(index), profile)
        cases.append((index, case_id))
        print(title, BASE + "/#case/" + case_id, flush=True)
    for index, case_id in cases:
        report = wait(case_id)
        print(case_id, report["result"], flush=True)
        verify(index, report)
