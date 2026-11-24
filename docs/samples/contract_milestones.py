"""Watermarked procurement cases with identical amounts and different performance evidence."""

import argparse
import hashlib
import unicodedata

from generate import BUYER, ROOT, SELLER, embedded_font, pdf
from run import BASE, get, post, submit, wait


CASES = {"early":"终验前支付验收款", "failed":"金额相符但终验不合格", "complete":"三期履约资料齐备",
         "approved":"合同约定董事会批准且已有决议", "denied":"双方已盖章但董事会退回补议"}
PROFILE = "cn-contract-performance/v1"


def documents(code, mode):
    common = [("合同编号","YL-LY-"+code),("采购方",BUYER),("供应方",SELLER),("采购标的","四门冷藏柜")]
    contract = [*common,("含税总额","100,000.00"),("签约日期","2026年9月1日"),("实际生效日期","2026年9月1日"),
                ("生效条款","本合同自双方盖章之日起生效"),("甲方签章",BUYER+"（已盖章）"),("乙方签章",SELLER+"（已盖章）"),
                ("约定交付数量","4台"),("约定验收标准","柜温不高于4℃"),("付款条款","分三期付款"),
                ("第一期","合同生效后支付30%"),("第二期","最终验收合格后支付60%"),("第三期","质保期满后支付10%")]
    acceptance = [*common,("验收日期","2026年9月20日"),("验收范围","全部交付终验"),("验收结论","合格"),
                  ("实际验收数量","4台"),("检验依据","柜温不高于4℃"),("实测结果","柜温8℃" if mode=="failed" else "柜温3℃"),
                  ("遗留事项","两台温控失灵待整改" if mode=="failed" else "无"),
                  ("验收签认","演练许澄（已签字）")]
    bank = [common[0],("付款户名",BUYER),("收款户名",SELLER),("付款金额","60,000.00"),("款项用途","第二期"),
            ("交易状态","交易成功"),("付款日期","2026年9月15日" if mode=="early" else "2026年9月21日")]
    records = {"采购合同":contract,"验收报告":acceptance,"银行付款回单":bank}
    if mode in ("approved","denied"):
        contract[:] = [(k,"本合同自双方盖章并经甲方董事会批准后生效" if k=="生效条款" else v) for k,v in contract
                       if k!="实际生效日期" or mode=="approved"]
        records["合同审批单"] = [*common[:3],("审批机构",BUYER+"董事会"),("审批日期","2026年9月1日"),
                              ("审批决定","批准" if mode=="approved" else "退回补议"),("审批签认","演练孙宁（已签字）")]
    if mode in ("complete","approved","denied"):
        records["质保期满确认单"] = [*common,("质保期满确认","2026年11月20日双方确认质保期已满"),("验收签认","演练许澄（已签字）")]
    return records


def generate(run_id, mode):
    code = hashlib.sha256((run_id+"-"+mode).encode()).hexdigest()[:8].upper()
    folder = ROOT / "24-合同履约与分期" / code
    folder.mkdir(parents=True,exist_ok=True)
    font = embedded_font("MilestoneSampleCJK")
    records = documents(code, mode)
    for title, rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder, records


def normalize(value):
    return "".join(unicodedata.normalize("NFKC",value).split())


def confirm_printed_records(cid, folder, records):
    path = "/api/cases/"+cid
    detail = get(path)
    assert {d["name"]:d["sha256"] for d in detail["documents"]} == {
        title+".pdf":hashlib.sha256((folder/(title+".pdf")).read_bytes()).hexdigest() for title in records}
    expected = {"甲方签章":"buyer_signature","乙方签章":"seller_signature","验收签认":"acceptance_signer","审批签认":"approval_signer"}
    report = wait(cid)
    if get(path)["rev"] > 1:
        return report
    selected = []
    for title, rows in records.items():
        for label,value in rows:
            if label not in expected:
                continue
            matches = [f for f in report["graph"]["facts"] if f["name"]==title+".pdf" and f["field"]==expected[label]
                       and normalize(f["quote"])==normalize(label+"："+value) and f.get("source_line")
                       and normalize(f["source_line"]["text"])==normalize(f["quote"])]
            assert len(matches)==1, (title,label,"水印原文与提取结果尚待人工核图")
            selected.append(matches[0]["id"])
    post(path+"/attest",{"rev":1,"reviewer":"水印演练校验","decision":"confirm","facts":selected,
                        "note":"按生成件摘要与原页逐字核对本次合成签章、验收签认栏；此记录仅用于虚构资料的功能验收。"})
    return wait(cid)


def correct_label_assignments(cid, report, records):
    """Correct only known semantic swaps whose entire printed row matches this generated source."""
    expected = {}
    for title, rows in records.items():
        for label,value in rows:
            if title=="验收报告" and label=="检验依据":
                expected[(title+".pdf",normalize(label+"："+value))] = ("acceptance_criteria","inspection_basis",value)
        if title=="质保期满确认单":
            expected[(title+".pdf",title)] = ("warranty_release","warranty",title)
    for (name,line),(old,new,value) in expected.items():
        matches = [f for f in report["graph"]["facts"] if f["name"]==name and f["field"]==old and
                   normalize(f["quote"])==line and f.get("source_line") and normalize(f["source_line"]["text"])==line]
        if not matches:
            continue
        assert len(matches)==1 and not matches[0].get("amendment")
        fact = matches[0]
        path = "/api/cases/"+cid
        rev = get(path)["rev"]
        post(path+"/amend",{"rev":rev,"reviewer":"水印演练校验","doc":fact["doc"],"page":fact["page"],
                            "target":fact["id"],"field":new,"value":value,"quote":fact["source_line"]["text"],"region":fact["region"],
                            "note":"逐字核对水印原件和本页文字。此处初次提取的字段类别与标签不符，保留原版并按所印标签补正。"})
        report = wait(cid)
    return report


def check(report, mode):
    findings = report["findings"]
    def results(rule):
        return [r["status"] for r in findings if r["rule"]==rule]
    assert results("H01")==["risk" if mode=="denied" else "ok"] and results("H03")==["ok"], [(r["rule"],r["detail"]) for r in findings if r["status"]!="ok"]
    assert results("H02")==["issue" if mode=="failed" else "ok"]
    phases = [r for r in findings if r["rule"]=="H04"]
    assert [p["stage"]["share"] for p in phases]==["30","60","10"]
    expected = {"early":["ok","ok","missing"],"failed":["ok","risk","risk"],"denied":["missing"]*3}
    assert results("H04")==expected.get(mode,["ok"]*3)
    assert results("H05")==[{"early":"risk","failed":"missing","denied":"missing"}.get(mode,"ok")]
    assert report["result"]["verdict"]=={"early":"review","failed":"reject","denied":"review"}.get(mode,"pass"), report["result"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-contract-milestones-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args = parser.parse_args()
    queued = []
    for mode in args.cases:
        name = CASES[mode]
        folder, records = generate(args.run_id,mode)
        if args.run:
            cid = submit("合成演练 · "+name,sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            queued.append((cid,folder,records,mode))
            print(mode,BASE+"/workpaper/"+cid,flush=True)
        else:
            print(folder)
    for cid,folder,records,mode in queued:
        paper = confirm_printed_records(cid,folder,records)
        paper = correct_label_assignments(cid,paper,records)
        check(paper,mode)
        print(mode,paper["result"]["verdict"],flush=True)
