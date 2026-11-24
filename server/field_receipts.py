"""Inspect source checks in archived workpapers using only the Python standard library."""

import json
from datetime import datetime


def field_actions(report, revision, journal=None, selected=None):
    result = []
    recorded = {}
    if journal is not None:
        for key, column in (("attestations","fact"),("amendments","target")):
            for row in journal[key]:
                identity = (column,row[column],row["rev"],row["time"])
                recorded[identity] = row
                if row["rev"] == revision and "source_check" in row:
                    result.append((row[column],row))
    for fact in report["graph"]["facts"]:
        if selected is not None and fact["id"] not in selected:
            continue
        for key,column in (("attestation","fact"),("amendment","target")):
            action = fact.get(key)
            if not action:
                continue
            receipt = action.get("source_check")
            saved = recorded.get((column,fact["id"],action.get("rev"),action.get("time")))
            if journal is not None and (receipt or (saved and saved.get("source_check"))):
                if not saved or any(saved.get(k) != v for k,v in action.items()) or receipt != saved.get("source_check"):
                    raise ValueError("字段的核图依据与对应的人工操作日志不符")
            if receipt is None:
                continue
            if (action[column] != fact["id"] or (receipt["doc"],receipt["page"]) != (fact["doc"],fact["page"])
                    or (receipt["original_sha256"],receipt["page_sha256"]) != (fact["source_sha256"],fact["page_sha256"])):
                raise ValueError("字段核图依据与该字段的原件或页图不符")
            result.append((fact["id"],action))
    return result


def validate_field_actions(report, revision, actions, load_version):
    versions, validated = {}, []
    for target,action in actions:
        rec = action["source_check"]
        rev = rec["rev"]
        if (type(rev) is not int or not 1 <= rev <= revision or rev != action["rev"] or rec["case_id"] != report["case_id"]
                or rec["format"] != "field-source-v1" or rec["operation"] not in {"confirm","correct","add"}):
            raise ValueError("核图记录的所属底稿、操作或版本错误")
        if rev not in versions:
            checksum,source = load_version(rev)
            if source["case_id"] != report["case_id"]:
                raise ValueError("核图时的底稿归属错误")
            graph = source["graph"]
            versions[rev] = (checksum,{d["id"]:d for d in graph["documents"]},
                             {n["id"]:n for n in graph["nodes"]},{f["id"]:f for f in graph["facts"]})
        source_hash, docs, nodes, facts = versions[rev]
        doc,page = rec["doc"],rec["page"]
        if (type(page) is not int or page < 1 or source_hash != rec["report_hash"]
                or not docs[doc]["sha256"] == nodes[doc]["sha256"] == rec["original_sha256"]
                or nodes[f"{doc}/p{page}"]["sha256"] != rec["page_sha256"]):
            raise ValueError("核图时的原始底稿、原件或页图摘要不符")
        printed = facts.get(target)
        if rec["operation"] == "add":
            if printed or not target.startswith(f"{doc}/p{page}/h"):
                raise ValueError("补录目标与核图时的原版不符")
        elif not printed or (printed["doc"],printed["page"],printed["source_sha256"],printed["page_sha256"]) != (
                doc,page,rec["original_sha256"],rec["page_sha256"]):
            raise ValueError("核图目标在所引原版中的位置或摘要不符")
        checked, signed = (datetime.fromisoformat(t) for t in (rec["checked_at"],action["time"]))
        if checked.tzinfo is None or signed.tzinfo is None or checked > signed:
            raise ValueError("核图时间与人工签收时间不符")
        if "target" in action:
            if rec["operation"] == "confirm" or (action["doc"],action["page"],action["page_hash"]) != (doc,page,rec["page_sha256"]):
                raise ValueError("字段更正与核图原页不符")
        elif action.get("decision") != "confirm":
            raise ValueError("核图字节确认记录对应了不同的人工操作")
        validated.append((rec,docs[doc]["ext"]))
    return validated


def verify_field_sources(bundle, hashes, report, revision, *, folder="", pages="pages/", originals=None, journal=None, selected=None):
    def load_version(rev):
        path = folder+("report.json" if rev == revision else f"field-checks/r{rev}/report.json")
        return hashes[path], report if rev == revision else json.loads(bundle.read(path))
    actions = field_actions(report,revision,journal,selected)
    history = {r["rev"]:r for r in journal["revisions"]} if journal is not None else None
    for receipt,ext in validate_field_actions(report,revision,actions,load_version):
        doc,page = receipt["doc"],receipt["page"]
        original = originals[doc] if originals is not None else folder+"originals/"+doc+ext
        if hashes[original] != receipt["original_sha256"] or hashes[pages+doc+"/"+str(page)+".jpg"] != receipt["page_sha256"]:
            raise ValueError("导出的原件或页图与核图时的实测摘要不符")
        if history is not None:
            version = history.get(receipt["rev"])
            if not version or version["hash"] != receipt["report_hash"] or datetime.fromisoformat(version["created"]) > datetime.fromisoformat(receipt["checked_at"]):
                raise ValueError("核图时的底稿摘要或时间与版本历史不符")
