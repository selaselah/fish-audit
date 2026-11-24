import copy
import unittest
from datetime import date

from controls import VERSION, execute
from performance import compute, verify_findings
from performance_versions import EFFECT_FORMAT
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from warranty_terms import calendar_end, edges, parse_period, sources, verify


TERM="自终验合格之日起2个月，届满日不顺延"
CONDITION="质保期满且无未关闭缺陷"
DEFECT="温控探头故障尚未修复"


def audit(term=TERM,*,condition=CONDITION,defect="无未关闭缺陷",edit=None,omissions=(),inline=False):
    contract=CONTRACT.copy()
    if term:
        contract.append(("warranty_period","质保期限",term))
    if inline:
        contract=[(k,l,CONDITION+"后支付10%" if l=="第三期" else v) for k,l,v in contract]
    elif condition:
        contract.append(("warranty_condition","质保金返还条件",condition))
    release=WARRANTY+([("warranty_defects","质保遗留事项",defect)] if defect is not None else [])
    def values(i,k,label,original):
        defaults={"warranty_release":"2026-11-21双方确认质保期已满","payment_designation":"第三期","paid_on":"2026-11-22"}
        value=defaults.get(k,original)
        return edit(i,k,label,value) if edit else value
    return material([contract,RECEIPT,release,BANK_DOC],values,omissions=omissions)


def decisions(graph):
    checks=compute(graph)
    stages=[f for f in checks if f["rule"]=="H04"]
    return stages,checks[-1]


def texts(graph):
    return {d["id"]:"\n".join(f["quote"] for f in graph["facts"] if f["doc"]==d["id"]) for d in graph["documents"]}


class WarrantyTermsTests(unittest.TestCase):
    def test_period_and_conditions_reconcile_to_distinct_originals(self):
        for inline in (False,True):
            graph=audit(inline=inline)
            stages,bank=decisions(graph)
            self.assertEqual([s["status"] for s in stages]+[bank["status"]],["ok"]*4)
            entry=stages[-1]["warranty_check"]
            self.assertEqual((entry["accepted_on"],entry["calendar_end"],entry["confirmed_on"]),
                             ("2026-09-20","2026-11-20","2026-11-21"))
            self.assertEqual(bank["warranty_check"],entry)
            self.assertEqual(entry["condition_ref"]==stages[-1]["stage"]["clause_ref"],inline)
            self.assertTrue(entry["requires_defect_clearance"])
            for name in ("term_ref","condition_ref","confirmation_ref","defect_ref"):
                self.assertIn(entry[name],stages[-1]["evidence"])
            self.assertEqual(len(edges(stages)),1)

    def test_early_certificate_and_early_bank_remain_independent(self):
        stages,bank=decisions(audit(TERM.replace("2个","12个")))
        self.assertEqual([s["status"] for s in stages],["ok","ok","risk"])
        self.assertEqual((bank["status"],bank["warranty_check"]["calendar_end"]),("risk","2027-09-20"))
        self.assertIn("2027-09-20",bank["detail"])
        self.assertFalse(edges(stages))
        stages,bank=decisions(audit(edit=lambda i,k,l,v:"2026-11-20" if k=="paid_on" else v))
        self.assertEqual((stages[-1]["status"],bank["status"]),("ok","risk"))
        self.assertIn("2026-11-21",bank["detail"])

    def test_requires_closed_defects_and_consistent_parties(self):
        for graph,status in ((audit(defect=DEFECT),"risk"),(audit(defect=None),"missing"),
                             (audit(edit=lambda i,k,l,v:"别家演练公司" if i==3 and k=="seller" else v),"missing"),
                             (audit(edit=lambda i,k,l,v:"其他人代签" if i==3 and k=="acceptance_signer" else v),"missing"),
                             (audit(omissions=[(3,"备注：尚待取得第三方检测报告")]),"missing")):
            stages,bank=decisions(graph)
            self.assertEqual([s["status"] for s in stages],["ok","ok",status])
            self.assertEqual(bank["status"],status)
        wrong=decisions(audit(edit=lambda i,k,l,v:"别家演练公司" if i==2 and k=="seller" else v))[0][-1]
        self.assertEqual((wrong["status"],wrong["warranty_check"]["status"],wrong["warranty_check"]["calendar_end"]),("risk","missing",None))

    def test_missing_raw_term_and_mixed_page_cannot_become_a_clean_release(self):
        graph=audit(term=None,omissions=[(1,"质保期限："+TERM)])
        entry=decisions(graph)[0][-1]["warranty_check"]
        self.assertEqual((entry["status"],entry["term_ref"],entry["calendar_end"]),("missing",None,None))
        graph=audit()
        original=texts(graph)
        page=next(n for n in graph["nodes"] if n["id"]=="d03/p1")
        page["clause_text_only"]=False
        graph["warranty_sources"]=sources(graph,lambda doc,num:original[doc])
        stages,bank=decisions(graph)
        self.assertEqual([s["status"] for s in stages]+[bank["status"]],["ok","ok","missing","missing"])
        graph=audit(omissions=[(1,"备注：质保期以另行签署的补充文件为准")])
        entry=decisions(graph)[0][-1]["warranty_check"]
        self.assertIsNone(entry["calendar_end"])
        graph=audit(omissions=[(2,"验收备注：质保期限按另附维修承诺延长")])
        self.assertIsNone(decisions(graph)[0][-1]["warranty_check"]["calendar_end"])
        graph=audit(edit=lambda i,k,l,v:"终验不合格" if k=="acceptance_result" else v)
        self.assertIsNone(decisions(graph)[0][-1]["warranty_check"]["accepted_on"])

    def test_unreadable_percentage_and_two_warranty_phases_need_separate_evidence(self):
        graphs=(audit(edit=lambda i,k,l,v:"质保期满后支付1 0%" if l=="第三期" else v),
                audit(edit=lambda i,k,l,v:"质保期满后支付60%" if l=="第二期" else v))
        for graph in graphs:
            stages,bank=decisions(graph)
            self.assertEqual(stages[0]["status"],"ok")
            self.assertTrue(all(f["status"]=="missing" for f in stages if f.get("warranty_check")))
            self.assertEqual(bank["status"],"missing")
            self.assertFalse(edges(stages))

    def test_receipt_claims_payment_and_issuer_evidence_have_different_roles(self):
        stages,bank=decisions(audit(edit=lambda i,k,l,v:"演练 甲" if k=="payer" else v))
        self.assertEqual(stages[-1]["status"],"ok")
        self.assertEqual(bank["status"],"missing")
        self.assertNotIn("warranty_check",bank)
        stages,bank=decisions(audit(edit=lambda i,k,l,v:"错列供应方" if i==3 and k=="seller" else v))
        pair,=stages[-1]["warranty_check"]["identity_conflicts"]
        self.assertEqual(pair["field"],"seller")
        self.assertIn(pair["contract_ref"],bank["evidence"])
        self.assertIn(pair["release_ref"],bank["evidence"])

    def test_month_end_leap_year_same_day_and_holiday_convention(self):
        for year,month,day,period,expected in ((2024,2,29,"1年","2025-02-28"),(2026,1,31,"1个月","2026-02-28"),
                     (2024,1,31,"1个月","2024-02-29"),(2026,9,20,"六十个自然日","2026-11-19")):
            term=parse_period("质保期限","自终验合格之日起"+period)
            self.assertEqual(calendar_end(date(year,month,day),term).isoformat(),expected)
        self.assertEqual(calendar_end(date(2026,9,20),parse_period("质保截止日","2026年11月20日")).isoformat(),"2026-11-20")
        self.assertIsNone(parse_period("质保期限","自终验合格之日起1 2个月"))
        stages,bank=decisions(audit(TERM.split("，")[0]))
        self.assertEqual((stages[-1]["status"],bank["status"]),("missing","missing"))
        self.assertIn("顺延",stages[-1]["detail"])
        stages,bank=decisions(audit(edit=lambda i,k,l,v:v.replace("11-21","11-20").replace("11-22","11-20")))
        self.assertEqual((stages[-1]["status"],bank["status"]),("missing","missing"))
        self.assertIn("时分",bank["date_checks"][0]["detail"])

    def test_archive_and_old_signoff(self):
        graph=audit()
        original=texts(graph)
        read=lambda doc,num:original[doc]
        report={"policy":{**VERSION,"profile":graph["profile"]},"graph":graph,"findings":execute(graph,graph["profile"])}
        graph["edges"]+=edges(report["findings"])
        verify(report,read)
        verify_findings(report)
        for field in ("source","graph","edge","policy","finding"):
            altered=copy.deepcopy(report)
            if field=="source": altered["graph"]["warranty_sources"]["lines"].pop()
            if field=="graph": next(e for e in altered["graph"]["edges"] if e["type"]=="warranty_defects")["from"]="d01"
            if field=="edge": altered["graph"]["edges"].pop()
            if field=="policy": del altered["policy"]["warranty_checks"]
            if field=="finding": altered["findings"][-1]["warranty_check"]["calendar_end"]="2099-01-01"
            with self.assertRaises(ValueError):
                verify_findings(altered) if field=="finding" else verify(altered,read)
        graph=audit(term=None,condition=None,defect=None,omissions=[(1,"质保期限："+TERM.replace("2个","12个"))])
        original=texts(graph)
        original["d01"]+="\n质保期限："+TERM.replace("2个","12个")
        del graph["warranty_sources"]
        old={"policy":{"performance_checks":EFFECT_FORMAT},"graph":graph,"findings":compute(graph,EFFECT_FORMAT)}
        self.assertTrue(all(f["status"]=="ok" for f in old["findings"]))
        verify(old,read)
        with self.assertRaisesRegex(ValueError,"旧版质保"):
            verify(old,read,signing=True)
