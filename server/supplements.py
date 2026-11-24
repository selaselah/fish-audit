"""Freeze and independently reconstruct the comparison with a returned workpaper."""

import hashlib
import json


def checksum(value):
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def compare_return(current, previous, signoff, report_hash, retained, note):
    parent = previous["case_id"]
    if (parent == current["case_id"] or signoff["case_id"] != parent or signoff["decision"] != "return"
            or current["policy"]["profile"] != previous["policy"]["profile"]):
        raise ValueError("前案签收决定或审计范围不符合补件关系")
    old_docs = {d["id"]: d for d in previous["graph"]["documents"]}
    new_docs = {d["id"]: d for d in current["graph"]["documents"]}
    old_ids, new_ids = set(), set()
    for pair in retained:
        old_id, new_id = pair["parent_doc"], pair["doc"]
        before, after = old_docs.get(old_id), new_docs.get(new_id)
        if (not before or not after or old_id in old_ids or new_id in new_ids or
                any(before[k] != after[k] for k in ("name", "ext", "size", "sha256"))):
            raise ValueError("沿用原件与前案签收版本不符")
        old_ids.add(old_id)
        new_ids.add(new_id)
    comparisons = {}
    for finding in previous["findings"]:
        if finding["status"] == "ok":
            continue
        rule = finding["rule"]
        group = comparisons.setdefault(rule, {"rule": rule, "title": finding["title"], "before": [], "after": []})
        group["before"].append({k: finding[k] for k in ("id", "status", "detail")})
    for finding in current["findings"]:
        if finding["rule"] in comparisons:
            comparisons[finding["rule"]]["after"].append({k: finding[k] for k in ("id", "status")})
    return {"format": "returned-workpaper-v1", "parent": parent, "rev": signoff["rev"], "title": signoff["title"], "report_hash": report_hash,
            "signoff_hash": checksum(signoff), "returned_by": signoff["reviewer"], "returned_at": signoff["time"],
            "reason": signoff["note"], "note": note, "retained": retained, "parent_rule_version": previous["policy"]["version"],
            "comparisons": list(comparisons.values())}
