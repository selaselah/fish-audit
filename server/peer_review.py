"""Bind a second human decision to the exact workpaper and referral the reviewer saw."""

import hashlib
import json
import unicodedata
from datetime import datetime

from payment_history import canonical


def different_reviewers(first, second):
    if first["workspace"] != "local":
        return bool(first["actor"] and second["actor"] and first["actor"] != second["actor"])
    def name(entry):
        return "".join(unicodedata.normalize("NFKC", entry["reviewer"]).casefold().split())
    return bool(name(first) and name(second) and name(first) != name(second))


def valid_findings(report, selected):
    available = {f["id"] for f in report["findings"]}
    return (isinstance(selected, list) and bool(selected) and all(isinstance(item, str) for item in selected)
            and len(selected) == len(set(selected)) and set(selected) <= available)


def review_record(source_bytes, first, second, findings):
    original = json.loads(source_bytes)
    if (original["case_id"] != first["case_id"] or "peer_review" in original
            or any(second[key] != first[key] for key in ("case_id", "workspace", "title"))
            or first["decision"] != "escalate" or second["decision"] not in {"approve", "return"}
            or type(first["rev"]) is not int or first["rev"] < 1 or type(second["rev"]) is not int
            or second["rev"] != first["rev"] + 1):
        raise ValueError("复核底稿的归属、版本或签收决定不符")
    if not different_reviewers(first, second):
        raise ValueError("复核需由另一位审计人员签收")
    before, after = (datetime.fromisoformat(entry["time"]) for entry in (first, second))
    if before.tzinfo is None or after.tzinfo is None or after < before or not second["note"].strip():
        raise ValueError("复核签收时间或意见无效")
    if not valid_findings(original, findings):
        raise ValueError("请从原底稿选择复核所依据的审计发现")
    return {"format": "peer-review-v1", "source_rev": first["rev"],
            "source_hash": hashlib.sha256(source_bytes).hexdigest(),
            "referral_hash": hashlib.sha256(canonical(first)).hexdigest(),
            "referral": first, "resolution": second, "findings": findings}


def verify_review(report, source_bytes, first, second):
    saved = report["peer_review"]
    if (canonical(review_record(source_bytes, first, second, saved["findings"])) != canonical(saved)
            or canonical(json.loads(source_bytes)) != canonical({key: value for key, value in report.items() if key != "peer_review"})):
        raise ValueError("复核签收、引用的发现或原版审计证据不符")


def journal_decision(journal, revision):
    rows = [row for row in journal["decisions"] if row["rev"] == revision]
    if len(rows) != 1:
        raise ValueError("日志缺少该版本的唯一签收记录")
    return {**rows[0], "case_id":journal["id"], "title":journal["title"], "workspace":journal["workspace"]}


def verify_referrals(journal):
    if "referrals" not in journal:
        return
    pins = journal["referrals"]
    expected = {d["rev"] for d in journal["decisions"] if d["decision"] == "escalate"}
    if {p["rev"] for p in pins} != expected or len(pins) != len(expected):
        raise ValueError("提交复核与版本存证的数量不符")
    hashes = {r["rev"]:r["hash"] for r in journal["revisions"]}
    for pin in pins:
        revision = pin["rev"]
        first = journal_decision(journal, revision)
        if (pin["report_hash"] != hashes.get(revision) or pin["signoff_hash"] != hashlib.sha256(canonical(first)).hexdigest()
                or pin["origin"] not in {"signoff","migration"}):
            raise ValueError("提交复核时留存的底稿或签收意见摘要不符")
        resolved = pin["resolved_rev"]
        if resolved is not None:
            second = journal_decision(journal,resolved)
            if (resolved != revision + 1 or second["decision"] not in {"approve","return"}
                    or not different_reviewers(first,second)):
                raise ValueError("日志中的复核版或复核签收身份不符")
