"""Compare a specifically required first-payment date with the interval printed on its original guarantee."""

import re


FORMAT = "advance-payment-guarantee-v2"
SINCE = "2026.11.27.06"
CLAUSE = re.compile(r"保函有效期要求[:：]\s*(?:第[一1]期|首期)预付款的付款日须在本合同项下(?:的)?预付款保函的有效期内。?")
PERIOD_HINT = re.compile(r"(?:保函|原函).*(?:有效期|担保期间|保证期间|起日|止日)|(?:有效期|担保期间|保证期间).*(?:保函|原函)")
EXTENSION = re.compile(r"展期|延期|续期|延长.{0,12}(?:保函|有效期|期间)|(?:换发|替换|补充|变更|修改|修订).{0,10}保函|保函.{0,8}(?:变更|补充|修订|批单)|有效期.{0,5}(?:调整|变更)")
SUPPLEMENT = re.compile(r"补充协议|补充件|变更协议|修订书|批单")
APPLICATION = re.compile(r"(?:展期|延期|续期)说明[:：]\s*(?:展期|延期|续期)申请已提交[，,]\s*尚待开立机构确认。?")
FIELDS = {"保函有效期自":"valid_from", "保函有效期至":"valid_until",
          "保函有效期至（含当日）":"valid_until_inclusive", "保函有效期至(含当日)":"valid_until_inclusive"}
END_FIELDS = {"valid_until","valid_until_inclusive"}


def clause_field(quote):
    return "period_clause" if PERIOD_HINT.search(quote) else "clause"


def compare(proof, *, payment, scoped):
    from advance_guarantee import literal_day, value

    sources = proof["sources"]
    clauses = [r for r in sources if r["field"]=="period_clause"]
    if not clauses:
        return None
    dates = [r for r in sources if r["role"]=="guarantee" and r["field"] in END_FIELDS|{"valid_from"}]
    starts = [r for r in dates if r["field"]=="valid_from"]
    ends = [r for r in dates if r["field"] in END_FIELDS]
    def read_day(rows):
        return literal_day(value(rows[0])) if len(rows)==1 and rows[0]["line"] else None
    bound = scoped and (proof["state"] in ("recorded","after_receipt","before_receipt","same_day") or
                        proof["state"]=="review" and proof["received_on"] is not None)
    start = read_day(starts) if bound else None
    end = read_day(ends) if bound else None
    inclusive = True if end and ends[0]["field"]=="valid_until_inclusive" else None
    paid = proof["paid_on"] if bound else None
    out = {"valid_from":start,"valid_until":end,"end_inclusive":inclusive,"paid_on":paid,
           "sources":sources,"evidence":proof["evidence"],"units":proof["units"]}
    def result(state,detail,status="missing"):
        return {**out,"state":state,"status":status,"detail":detail}
    if not scoped or len(clauses)!=1 or not clauses[0]["line"] or not CLAUSE.fullmatch(clauses[0]["quote"].strip()):
        return result("review","请核对首期付款与保函有效期的完整合同原行。")
    if not bound:
        return result("review","请先核对本合同、保函原件和采购方签收单的归属。")
    if any(r["field"]=="extension_note" for r in sources):
        return result("extension_review","材料有展期记载。请核对其归属、开立机构的确认和适用期间。")
    if any(r["role"]=="extension" or r["field"]=="period_note" for r in sources):
        return result("review","另有附件、附注或未辨原页，请核对适用的保函版本及期间。")
    if not start or not end or end<start or end<proof["issued_on"]:
        return result("review","请核对原函上分别载明的起止日期及其先后。")
    if not payment:
        return result("stated",f"原函载明期间自 {start} 至 {end}。")
    if not paid:
        return result("review","待取得可独立归属于本期的成功付款日原行。")
    if paid<start:
        return result("before_start",f"付款日 {paid} 早于原函载明的起日 {start}，请核查合同要求的期间覆盖。","risk")
    if paid>end:
        return result("expired",f"付款日 {paid} 晚于原函载明的止日 {end}，请核查合同要求的期间覆盖。","risk")
    if paid==end and not inclusive:
        return result("end_unspecified",f"付款与原函止日同为 {paid}，请核实止日是否包含当日。")
    if paid==start and paid!=end:
        return result("review",f"付款与原函起日同为 {paid}，请核实起效时点。")
    return result("covered",f"按原函载明的期间，付款日 {paid} 在覆盖范围内。保函真实性、效力及付款授权仍待核验。")
