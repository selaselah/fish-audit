"""Check a named device's signed, contiguous operating intervals against its contract."""

import re
import unicodedata
from datetime import datetime

from equipment_models import valid_code

LOG_HEADINGS = {
    "试运行设备": "run_equipment",
    "日志口径": "run_clock",
    "日志签认范围": "run_attestation",
    "运行记录": "run_segment",
}
LOG_KINDS = set(LOG_HEADINGS.values())
CLOCK = "北京时间,区间含起不含止,边界为整分"
ATTESTATION = "本页复验签认涵盖全部试运行记录"
SUBJECT = re.compile(r"[\w\u3400-\u9fff -]{1,60}\(序列号\s*([A-Za-z0-9._-]+)\)")
MINUTE = r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}"
SEGMENT = re.compile(rf"({MINUTE})\s+至\s+({MINUTE})\s*\|\s*(连续无异常|故障停机)")
SCOPE_HINT = re.compile(r"序列号|设备编号|试运行|运行日志|运行记录|日志口径|日志签认")


def same_printed_subject(fact, raw):
    if fact["field"] != "subject" or fact["status"] not in ("anchored", "confirmed"):
        return False

    def spacing(value):
        return re.sub(r"(\(序列号)\s*(?=[A-Za-z0-9])", r"\1", unicodedata.normalize("NFKC", value))

    return spacing(raw) == spacing(fact["quote"])


def read_segment(body):
    match = SEGMENT.fullmatch(body)
    if not match:
        return None
    try:
        start, end = (datetime.fromisoformat(value) for value in match.groups()[:2])
    except ValueError:
        return None
    if end <= start:
        return None
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "seconds": int((end - start).total_seconds()),
        "state": "normal" if match[3] == "连续无异常" else "fault",
    }


def classify(role, label, body):
    from graph import LABELS

    if label in LABELS["subject"]:
        match = SUBJECT.fullmatch(body)
        code = match[1] if match and valid_code(match[1]) else None
        return {"kind": "run_subject", "serial": code}
    field = "quantity_agreed" if role == "contract" else "quantity_accepted"
    if role in ("contract", "original", "reinspection") and label in LABELS[field]:
        return {"kind": "run_quantity", "single": bool(re.fullmatch(r"1\s*台", body))}
    if role == "reinspection":
        if label in LABELS["acceptance_signer"]:
            return {"kind": "run_signer"}
        kind = LOG_HEADINGS.get(label)
        if kind == "run_equipment":
            return {"kind": kind, "serial": body if valid_code(body) else None}
        if kind == "run_clock":
            return {"kind": kind, "exact": body == CLOCK}
        if kind == "run_attestation":
            return {"kind": kind, "exact": body == ATTESTATION}
        if kind == "run_segment":
            return {"kind": kind, "interval": read_segment(body)}
    if SCOPE_HINT.search(label + ":" + body):
        return {"kind": "run_qualification"}
    return None


def log_positions(ledger, units):
    return {
        (r["doc"], r["page"], r["line"], r["quote"])
        for r in ledger.get("lines", [])
        if r["unit"] in units and r["supported"] and r["kind"] in LOG_KINDS
    }


def coverage(intervals):
    gaps = []
    longest = streak = 0
    previous = None
    for segment in intervals:
        if previous and segment["start"] > previous["end"]:
            start, end = previous["end"], segment["start"]
            seconds = int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
            gaps.append(
                {
                    "start": start,
                    "end": end,
                    "seconds": seconds,
                    "before_ref": previous["ref"],
                    "after_ref": segment["ref"],
                }
            )
            streak = 0
        streak = streak + segment["seconds"] if segment["state"] == "normal" else 0
        longest = max(longest, streak)
        previous = segment
    return longest, gaps


def assess(rows, steps, contract, graph, fix, start, required_hours):
    records = [r for r in rows if r["kind"].startswith("run_")]
    if not any(r["kind"] in LOG_KINDS for r in records):
        return None
    op = {
        "sources": [r["id"] for r in records],
        "serial": None,
        "log_serial": None,
        "intervals": [],
        "gaps": [],
        "longest_seconds": None,
    }

    def outcome(state, status, detail):
        return {"operation": op, "state": state, "status": status, "detail": detail}

    def one(unit, kind):
        selected = [r for r in records if r["unit"] == unit and r["kind"] == kind]
        return selected[0] if len(selected) == 1 and selected[0]["supported"] else {}

    units = {s["role"]: s["unit"] for s in steps}
    final = units["final"]
    scoped_pages = [
        p for p in graph["reinspection_wait_sources"]["pages"] if p["unit"] in {contract, *units.values()}
    ]
    subject = one(contract, "run_subject")
    header = one(final, "run_equipment")
    serial = op["serial"] = subject.get("serial")
    op["log_serial"] = header.get("serial")
    if (
        not serial
        or op["log_serial"] != serial
        or set(units) != {"original", "repair", "final"}
        or any(not (p["native"] and p["text_only"]) for p in scoped_pages)
        or any(one(unit, "run_subject").get("serial") != serial for unit in units.values())
        or any(not one(unit, "run_quantity").get("single") for unit in (contract, units["original"], final))
        or any(r["kind"] == "run_qualification" for r in records)
    ):
        return outcome("run_device", "missing", "请核对合同、初验、整改、复验和日志的设备序列号与单台范围。")

    clock, signature, signer = (one(final, kind) for kind in ("run_clock", "run_attestation", "run_signer"))
    entries = [r for r in records if r["kind"] == "run_segment"]
    confirmed = [
        f
        for f in graph["facts"]
        if f["id"] in signer.get("facts", ())
        and f["field"] == "acceptance_signer"
        and f["status"] == "confirmed"
        and (f.get("source_line") or {}).get("text") == signer["quote"]
        and f["source_line"]["number"] == signer["line"]
    ]
    if (
        not clock.get("exact")
        or not signature.get("exact")
        or len(confirmed) != 1
        or not entries
        or not all(r["supported"] and r.get("interval") for r in entries)
        or any(
            (r["doc"], r["page"]) != (signer["doc"], signer["page"])
            for r in (header, clock, signature, *entries)
        )
    ):
        return outcome("run_record", "missing", "运行区间、时钟口径或涵盖全部记录的同页签认待核。")

    intervals = sorted(
        ({"ref": r["id"], **r["interval"]} for r in entries), key=lambda s: (s["start"], s["end"], s["ref"])
    )
    op["intervals"] = intervals
    if any(left["end"] > right["start"] for left, right in zip(intervals, intervals[1:])):
        return outcome("run_overlap", "missing", "同台设备的运行区间存在重叠或重复，须核对原行。")
    if (
        not start
        or intervals[0]["start"] < fix["stamp"]["before"]
        or intervals[-1]["end"] > start["stamp"]["from"]
    ):
        return outcome("run_window", "missing", "须确认各段记录都在整改完成之后、实际复验开始之前。")

    longest, gaps = coverage(intervals)
    op.update(longest_seconds=longest, gaps=gaps)
    if any(s["state"] == "fault" for s in intervals):
        return outcome("run_fault", "risk", "签认的运行日志载明设备曾故障停机，须核查故障处置及后续试运行。")
    if longest >= required_hours * 3600:
        return outcome("run_met", "ok", "同台设备的签认日志连续覆盖了合同约定的无异常试运行时长。")
    if gaps:
        return outcome("run_gap", "missing", "两段运行记录之间缺少覆盖，最长连续无异常时段未达约定。")
    return outcome("run_short", "missing", "签认日志覆盖的连续无异常运行时长短于合同约定，须补查记录。")
