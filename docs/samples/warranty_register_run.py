"""Replay the three fixed editions from local bundles or the local service."""

import argparse
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

import publish_warranty_register as sample
from advance_guarantees import model_record, rerun_event, save_json
from protocol import canonical
from publish_batch_version import PROJECT, digest, require
from rule_replay import replay_from_git
from run import BASE, get, post, wait
from verify import verify

SCRATCH = Path("/tmp/fish-warranty-register-27")
CASE_PATH = "/api/cases/" + sample.CASE
HISTORY = {
    9: ("cc3da6f26bb9eef3122ff360b46e50fecb6904c1d39e8db26c32e5f0076bbc3f",
        "894d14795f607e75110b7c4234f6bc395365b425"),
    10: ("e42cb88c44650cf65360ad4b25ef58ae0dd3a96fc333e6583794b7723faaa90c",
         "1902bfe7f47835f382401b4bb50ea2bedeccc8b5"),
}


def archived(folder, rev, expected_hash):
    archive = folder / f"R{rev}.zip"
    if not archive.exists():
        with urlopen(f"{BASE}{CASE_PATH}/reports/{rev}/bundle", timeout=60) as response:
            raw = response.read()
        with ZipFile(BytesIO(raw)) as bundle:
            sample.fixed_report(bundle, rev, expected_hash)
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as staged:
            staged.write(raw)
        Path(staged.name).replace(archive)
    return archive


def inspect(folder, rev, expected_hash, commit):
    archive = archived(folder, rev, expected_hash)
    with ZipFile(archive) as bundle:
        report, journal = sample.fixed_report(bundle, rev, expected_hash)
        pages = sample.fixed_pages(bundle, report)
        phase, bank = sample.issued_findings(report)
        docs, _ = sample.select_documents(report["graph"], pages, phase, bank, rev)
        warranty = phase["warranty_check"]
        sample.ticket_bindings(warranty, docs)
        calls = report["calls"]
        steps = {}
        for call in calls["pages"]:
            unit = call["doc"]
            require(call["page"] == 1 and unit not in steps, "六页原始调用")
            image = pages[unit]["image"]
            steps[unit] = {action: model_record(trace, calls["instructions"], image)
                           for action, trace in (("read", call), ("check", call["check"]))}
        require(set(steps) == set(pages), "六份原件的初读及复核")
    cid, verified, entries = verify(archive, render_addenda=True)
    require((cid, verified) == (sample.CASE, rev), f"R{rev} 固定证据包")
    replay = replay_from_git(report, ref=commit, repo=PROJECT, pinned=commit)
    require(replay["state"] == "verified" and replay["commit"] == commit, f"R{rev} 已提交源码复算")
    humans = {k: {"count": len(journal[k]), "sha256": digest(canonical(journal[k]).encode())}
              for k in ("amendments", "attestations", "decisions", "referrals")}
    receipt = dict(case_id=cid, rev=rev, rule_version=report["policy"]["version"], report_sha256=expected_hash,
                   bundle_sha256=digest(archive.read_bytes()), entries=entries, git=replay, human=humans,
                   page_calls=steps, expert=model_record(calls["expert"], calls["instructions"]),
                   selected_lines={role: doc["lines"] for role, doc in docs.items()},
                   phase={"id": phase["id"], "status": phase["status"], "accepted_on": warranty["accepted_on"],
                          "calendar_end": warranty["calendar_end"]},
                   tickets=[{k: ticket[k] for k in ("unit", "number", "fault", "printed_state", "state", "status")}
                            for ticket in warranty["tickets"]],
                   payment={"id": bank["id"], "status": bank["status"], "paid_on": bank["warranty_payment"]["paid_on"]},
                   verdict=report["result"]["verdict"])
    if rev == sample.REV:
        receipt["comparison"] = sample.issued_comparison(report, warranty, docs)
    save_json(folder / f"R{rev}-verification.json", receipt)
    return receipt


def compare(folder, before, after):
    require(before["page_calls"] == after["page_calls"] and len(before["page_calls"]) == 6
            and before["selected_lines"] == after["selected_lines"], "六页模型记录或选定实页行框变化")
    require(before["human"] == after["human"] and after["human"]["decisions"]["count"] == 0,
            "历史补录、核图、转介或人工决定变化")
    require(all(before["expert"][k] != after["expert"][k] for k in ("request_id", "response_id")),
            "专家须有本版的新请求和响应")
    receipt = dict(before=before["rev"], after=after["rev"], read_reused=6, check_reused=6,
                   expert_before=before["expert"], expert_after=after["expert"], manual_delta=0,
                   before_sha256=before["report_sha256"], after_sha256=after["report_sha256"])
    save_json(folder / f"R{before['rev']}-R{after['rev']}.json", receipt)
    print(f"R{before['rev']} → R{after['rev']}：六页初读与六页复检复用，一次新的专家响应，人工记录增量为零。")


def fetch_r11(folder):
    path = CASE_PATH + "/reports/11"
    issued = get(path)
    sha = issued["sha256"]
    require(issued["rev"] == 11 and digest(canonical(issued["report"]).encode()) == sha
            and issued["report"]["policy"]["version"] == sample.RULE, "线上 R11 的固定摘要和规则")
    with ZipFile(archived(folder, 11, sha)) as bundle:
        sample.fixed_report(bundle, 11, sha)
        require(bundle.read("report.json") == canonical(issued["report"]).encode(), "证据包的线上固定版")
    return sha


def reissue(folder, commit):
    actual = subprocess.check_output(["git", "-C", str(PROJECT), "rev-parse", "--verify", "--end-of-options",
                                      commit + "^{commit}"], text=True).strip()
    require(actual == commit and get("/api/controls")["version"] == sample.RULE
            and get("/api/ready")["status"] == "ready", "已发布的完整 .07 提交与就绪的本机服务")
    case = get(CASE_PATH)
    require(case["id"] == sample.CASE and case["title"] == sample.TITLE and not (case["decisions"] or case["referrals"])
            and all(any(v["rev"] == rev and v["hash"] == sha for v in case["revisions"]) for rev, (sha, _) in HISTORY.items()),
            "指定案件和两份冻结的历史版本")
    with ZipFile(archived(folder, 10, HISTORY[10][0])) as old:
        report, _ = sample.fixed_report(old, 10, HISTORY[10][0])
    require({d["id"]: d["sha256"] for d in case["documents"]} == {d["id"]: d["sha256"] for d in report["graph"]["documents"]},
            "线上六份原件与 R10 不符")
    count = rerun_event(case, 10)
    if count == 0:
        require(case["status"] == "ready" and case["rev"] == 10
                and all(case["page_progress"]["counts"][k] == 6 for k in ("prepared", "read", "checked")), "R10 准入及逐页检查点")
        save_json(folder / "reissue-request.json", dict(case_id=sample.CASE, rev=10, report_sha256=HISTORY[10][0],
                                                        commit=commit, checkpoints=case["page_progress"]["counts"]))
        require(post(CASE_PATH + "/rerun", {"rev": 10})["id"] == sample.CASE, "本案 R10 重审回执")
    else:
        require(count == 1 and case["rev"] in (10, 11), "R10 重审事件数")
    if case["rev"] < 11:
        wait(sample.CASE)
    case = get(CASE_PATH)
    require(case["rev"] == 11 and case["status"] == "ready" and rerun_event(case, 10) == 1, "R11 唯一重审及待验收状态")
    return fetch_r11(folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=SCRATCH, help="保存归档和复算结果的目录，缺少的固定版本从本机服务读取")
    parser.add_argument("--reissue", metavar="COMMIT", help="部署后从该案固定 R10 发起一次正常重审，可从已发出的请求恢复")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    before = inspect(args.output, 9, *HISTORY[9])
    baseline = inspect(args.output, 10, *HISTORY[10])
    compare(args.output, before, baseline)
    target = (sample.REPORT_SHA256, sample.RELEASE_COMMIT)
    if args.reissue:
        target = (reissue(args.output, args.reissue), args.reissue)
        print("R11", target[0], flush=True)
    compare(args.output, baseline, inspect(args.output, 11, *target))
