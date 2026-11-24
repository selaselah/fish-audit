"""Reconstruct the evidence and findings that a signed payment comparison must carry."""

from datetime import datetime

from installments import LIMIT as INSTALLMENT_LIMIT, calculate
from payment_history import LIMIT, check_history


FORMAT = "payment-findings-v1"
RULES = {"B06","B07","B08"}


def comparison_refs(current, archived, kind, match, decision, as_of, *, marked=None):
    signed = datetime.fromisoformat(decision["time"])
    if (match["decision"]!=decision["decision"] or match["signed_at"]!=decision["time"] or
            match["title"]!=decision["title"] or decision["decision"] not in {"approve","return","escalate"} or
            signed.tzinfo is None or signed>as_of):
        raise ValueError("历史人工决定或时点不符")
    if marked is not None:
        if marked and kind!="installment":
            raise ValueError("历史回单的部分流水号进入了完整流水比对")
        if match.get("incomplete_references",[])!=marked:
            raise ValueError("历史回单遮盖提示与签收原页不符")
    if kind=="same":
        if not current["reference"] or (archived["payer"],archived["reference"])!=(current["payer"],current["reference"]):
            raise ValueError("已签收回单流水或付款户名不符")
        return archived["same_refs"]
    if kind=="full":
        if (decision["decision"]!="approve" or not current["settlement"] or archived["settlement"]!=current["settlement"]
                or archived["reference"]==current["reference"]):
            raise ValueError("历史全额付款口径或成功流水不符")
        return archived["full_refs"]
    if kind=="installment":
        source = archived["installment"]
        if (decision["decision"]!="approve" or not current["installment"]["key"] or
                source["key"]!=current["installment"]["key"] or source["entry"]!=match["entry"]):
            raise ValueError("历史分期付款主体、原件或金额与已签收底稿不符")
        return source["refs"]
    raise ValueError("历史付款核查的命中类型不符")


def verify_findings(signature, history, findings, policy, *, issued_at=None):
    if history is None:
        if policy.get("payment_checks")==FORMAT:
            raise ValueError("本版付款底稿缺少出具时的跨案检索记录")
        return None,[]
    as_of = datetime.fromisoformat(history["as_of"])
    if as_of.tzinfo is None or set(history["counts"])!={"same","full"}:
        raise ValueError("付款检索时点或范围无效")
    if issued_at is not None and as_of>datetime.fromisoformat(issued_at):
        raise ValueError("付款检索时点晚于所据底稿的出具时间")
    matches = [(m["kind"],m) for m in history["matches"]]
    if any(kind not in {"same","full"} for kind,_ in matches):
        raise ValueError("历史流水核查的命中类型不符")
    for kind,key in (("same","reference"),("full","settlement")):
        count = history["counts"][kind]
        listed = sum(k==kind for k,_ in matches)
        if type(count) is not int or count<0 or listed!=min(count,LIMIT) or (count and not signature[key]):
            raise ValueError("历史付款命中数量或本案依据不符")
    window = history.get("installments")
    if "installments.py" in policy.get("code_sha256",{}) and (window is not None)!=signature["installment"]["requested"]:
        raise ValueError("分期累计检查范围不符")
    if window is not None:
        count = window["count"]
        if (type(count) is not int or count<0 or len(window["matches"])!=min(count,INSTALLMENT_LIMIT)
                or (count and not signature["installment"]["key"])):
            raise ValueError("历史分期底稿的范围或数量不符")
        if calculate(signature["installment"],window)!=window["calculation"]:
            raise ValueError("逐笔流水去重、累计或合同差额与原始取数不符")
        matches.extend(("installment",m) for m in window["matches"])
    seen = set()
    for kind,match in matches:
        prior,rev = match["case_id"],match["rev"]
        address = (kind=="installment",prior)
        if not isinstance(prior,str) or not prior or type(rev) is not int or rev<1 or address in seen:
            raise ValueError("历史付款归属重复或范围无效")
        seen.add(address)
    expected = {}
    def collect(rule,status,detail,refs,scope):
        expected[rule] = status,detail,list(dict.fromkeys(refs))
    check_history(signature,history,collect,[])
    issued = [f for f in findings if f["rule"] in RULES]
    if len(issued)!=len(expected) or {f["rule"] for f in issued}!=expected.keys():
        raise ValueError("跨案付款发现缺失或重复")
    for finding in issued:
        rule = finding["rule"]
        status,detail,refs = expected[rule]
        if finding["status"]!=status or finding["evidence"]!=refs:
            raise ValueError(f"{rule} 付款结论或所引证据不符")
        if (policy.get("payment_checks")==FORMAT or rule=="B08") and finding["detail"]!=detail:
            raise ValueError(f"{rule} 付款发现的逐笔金额、范围或说明与当版计算不符")
    return as_of,matches
