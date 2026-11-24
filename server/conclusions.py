"""Summarize the issued findings for the reviewer and check the saved summary offline."""


STATUS = {"ok": "相符", "issue": "发现问题", "risk": "风险待核", "missing": "证据不足"}


def conclusion(findings):
    statuses = {finding["status"] for finding in findings}
    verdict = "reject" if "issue" in statuses else ("review" if statuses - {"ok"} or not statuses else "pass")
    return {"verdict":verdict,"human_required":verdict!="pass","signoff_required":True,
            "counts":{key:sum(f["status"]==key for f in findings) for key in STATUS}}


def verify_result(report):
    findings = report["findings"]
    if any(f.get("status") not in STATUS for f in findings) or report["result"]!=conclusion(findings):
        raise ValueError("底稿的通过建议、人工核验要求或风险数量与逐项发现不符")
