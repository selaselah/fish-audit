"""Compare complete native contract lines with independently supported transcriptions."""

import re
import unicodedata
from datetime import date
from decimal import Decimal


FIELDS = {
    "signed_on": "date",
    "effect_on": "date",
    "valid_until": "date",
    "quantity_agreed": "quantity",
    "acceptance_criteria": "temperature",
    "payment_stage": "installment",
    "payment_term": "installment",
}
LABELLED = re.compile(r"([^:：\s]+[:：]) *(.*)")
# Only ASCII layout spaces at the written token boundaries. Captures must agree
# verbatim, including leading zeroes, the condition, sign, and fractional digits.
BODIES = {
    "date": re.compile(r"([0-9]{4}) *年 *([0-9]{1,2}) *月 *([0-9]{1,2}) *日"),
    "quantity": re.compile(r"([0-9]{1,9}) *(台|套|件)"),
    "temperature": re.compile(r"(柜温不高于|柜温不低于) *(-?[0-9]{1,3}(?:\.[0-9]{1,3})?) *(?:℃|°C)"),
    "installment": re.compile(r"(合同生效后支付|最终验收合格后支付|质保期满后支付) *([0-9]{1,3}(?:\.[0-9]{1,2})?) *%"),
}
SPLIT_NUMBER = re.compile(r"[0-9]\s+[0-9.]|[0-9]\.\s+[0-9]|[-+]\s+[0-9]")


def ambiguous_number(body):
    return bool(SPLIT_NUMBER.search(body)) or any(
        not char.isascii() and (char.isdecimal() or re.fullmatch(r"[0-9]+", unicodedata.normalize("NFKC", char)))
        for char in body
    )


def ambiguous_stage(raw):
    from performance import STAGE_PREFIX

    parts = re.split(r"[:：、]", raw.strip(), maxsplit=1)
    if len(parts) == 2 and STAGE_PREFIX.fullmatch(parts[0] + ":") and ambiguous_number(parts[1]):
        return parts[1]
    return None


def compare(raw, fact):
    from graph import LABELS
    from performance import STAGE_PREFIX

    field = fact["field"]
    form = FIELDS.get(field)
    if not form or not (
        fact["status"] == "anchored" and fact.get("visual_check") == "clear"
        or fact["status"] == "confirmed" and (fact.get("attestation") or {}).get("decision") == "confirm"
    ):
        return None
    native = LABELLED.fullmatch(raw)
    transcribed = LABELLED.fullmatch(fact["quote"])
    if not native or not transcribed or native[1] != transcribed[1]:
        return None
    label = native[1][:-1]
    if form == "installment":
        if ambiguous_number(label) or not STAGE_PREFIX.fullmatch(label + ":"):
            return None
    elif label not in LABELS[field]:
        return None
    if raw == fact["quote"] and native[2] == fact["value"]:
        return None
    tokens = BODIES[form].fullmatch(native[2])
    if not tokens:
        return None
    for value in (transcribed[2], fact["value"]):
        match = BODIES[form].fullmatch(value)
        if not match or match.groups() != tokens.groups():
            return None
    if form == "date":
        try:
            date(*map(int, tokens.groups()))
        except ValueError:
            return None
    if form == "installment" and not 0 < Decimal(tokens[2]) <= 100:
        return None
    return {"ref": fact["id"], "form": form, "quote": fact["quote"], "value": fact["value"]}


def witness(fact, call):
    """Bind the accepted text to either its field receipt or both model calls."""
    if fact["status"] == "confirmed":
        decision = fact.get("attestation") or {}
        receipt = decision.get("source_check") or {}
        if (decision.get("fact") == fact["id"] and decision.get("decision") == "confirm"
                and receipt.get("format") == "field-source-v1" and receipt.get("operation") in ("confirm", "add", "correct")
                and receipt.get("rev") == decision.get("rev") and receipt.get("report_hash")
                and (receipt.get("doc"), receipt.get("page"), receipt.get("original_sha256"), receipt.get("page_sha256")) ==
                    (fact["doc"], fact["page"], fact["source_sha256"], fact["page_sha256"])):
            return "field_receipt"
        return None
    check = call.get("check") or {}
    ref = re.fullmatch(r"d[0-9]+/p[1-9][0-9]*/f([1-9][0-9]*)", fact["id"])
    output = call.get("output", {}).get("facts", [])
    if (not ref or int(ref[1]) > len(output) or fact.get("amendment")
            or not call.get("response_id") or not check.get("response_id")
            or fact.get("response_id") != call["response_id"] or fact.get("check_response_id") != check["response_id"]
            or call["response_id"] == check["response_id"]):
        return None
    original = output[int(ref[1]) - 1]
    inputs = [row for row in check.get("input", []) if row.get("index") == ref[1]]
    votes = [row.get("support") for row in check.get("output", {}).get("checks", []) if row.get("index") == ref[1]]
    if (len(inputs) == 1 and votes == ["clear"] and original.get("field") == fact["field"]
            and inputs[0].get("field") == fact["label"]
            and all(original.get(k, "").strip() == inputs[0].get(k, "").strip() == fact[k] for k in ("value", "quote"))):
        return "visual_check"
    return None
