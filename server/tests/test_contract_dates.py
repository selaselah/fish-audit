import copy
import unittest

from controls import VERSION, execute
from performance import FORMAT, SIGNATORY_FORMAT, RULES, compute, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_reinspection import OLD, FIX, FINAL


def findings(*, effect="2026-09-01", until=None, accepted="2026-09-20", paid="2026-09-21",
             designation="第二期", receipt=RECEIPT, extra=()):
    c=[*CONTRACT,("valid_until","合同有效期至",until)] if until else CONTRACT
    replacements={"effect_on":effect,"accepted_on":accepted,"paid_on":paid,"payment_designation":designation}
    g=material([c,receipt,*extra,WARRANTY,BANK_DOC],lambda i,f,l,v:replacements.get(f,v))
    return g,compute(g)


def pick(fs,rule):
    return next(f for f in fs if f["rule"]==rule)


class ContractDateTests(unittest.TestCase):
    def test_reported_effect_after_expiry_holds_all_phases_and_cites_both_fields(self):
        g,fs=findings(effect="2026-09-16",until="2026-09-12")
        h=pick(fs,"H01")
        self.assertEqual(h["status"],"risk")
        check,=h["date_checks"]
        self.assertEqual(check["event"],"contract_period")
        self.assertEqual({f["field"] for f in g["facts"] if f["id"] in check["evidence"]},{"effect_on","valid_until"})
        self.assertEqual([f["status"] for f in fs if f["rule"]=="H04"],["missing"]*3)
        self.assertEqual(pick(compute(g,SIGNATORY_FORMAT),"H01")["status"],"ok")

    def test_acceptance_before_or_same_day_and_independent_advance(self):
        for day,status in (("2026-09-15","risk"),("2026-09-16","missing"),("2026-09-17","ok")):
            g,fs=findings(effect="2026-09-16",accepted=day)
            self.assertEqual(pick(fs,"H01")["status"],"ok")
            h=pick(fs,"H02")
            self.assertEqual(h["status"],status)
            self.assertEqual([f["status"] for f in fs if f["rule"]=="H04"],["ok",status,status])
            if status!="ok":
                check,=h["date_checks"]
                self.assertIn(day,check["detail"])
                self.assertTrue(set(check["evidence"])<=set(h["evidence"]))
            self.assertEqual(pick(fs,"H05")["status"],"ok" if status=="ok" else "missing")
        _,fs=findings(until="2026-09-30")
        self.assertTrue(all(f["status"]=="ok" for f in fs))

    def test_same_day_preconditions_by_payment_phase(self):
        for label,day,event in (("第一期","2026-09-01","合同生效"),("第二期","2026-09-20","验收"),("第三期","2026-11-20","质保期满确认")):
            _,fs=findings(paid=day,designation=label)
            h=pick(fs,"H05")
            self.assertEqual(h["status"],"missing")
            self.assertIn(event,h["date_checks"][0]["detail"])
            self.assertEqual([f["status"] for f in fs if f["rule"]=="H04"],["ok"]*3)

    def test_ambiguous_date_field_and_spaced_digits_require_review(self):
        for label,value in (("预计交付日期","2026-09-20"),("验收日期","202 6-09-20")):
            r=[(f,label,value) if f=="accepted_on" else (f,l,v) for f,l,v in RECEIPT]
            g=material([CONTRACT,r,WARRANTY,BANK_DOC])
            h=pick(compute(g),"H02")
            self.assertEqual(h["status"],"missing")
            self.assertTrue(h["date_checks"])

    def test_reopening_preserves_original_unsatisfactory_result(self):
        g=material([CONTRACT,OLD,FIX,FINAL,WARRANTY,BANK_DOC],lambda i,f,l,v:"2026-09-21" if f=="effect_on" else v)
        old=pick(compute(g,SIGNATORY_FORMAT),"H02")
        self.assertEqual(old["reinspection"]["state"],"closed")
        new=pick(compute(g),"H02")
        self.assertEqual((new["status"],new["reinspection"]["state"]),("issue","open"))
        self.assertIn("不合格",new["detail"])

    def test_replay_and_legacy_signoff_cover_only_affected_dates(self):
        for paid,flagged in (("2026-09-20",True),("2026-09-21",False)):
            g,_=findings(paid=paid)
            for version in (FORMAT,SIGNATORY_FORMAT):
                fs=execute(g,g["profile"])
                if version==SIGNATORY_FORMAT:
                    old=iter(compute(g,SIGNATORY_FORMAT))
                    for i,f in enumerate(fs):
                        if f["rule"] in RULES:
                            fs[i]={**{k:f[k] for k in ("id","title","basis","version")},**next(old)}
                report={"policy":{**VERSION,"profile":g["profile"],"performance_checks":version},"graph":g,"findings":fs}
                verify_findings(report)
                if flagged and version==SIGNATORY_FORMAT:
                    with self.assertRaisesRegex(ValueError,"重审"):
                        verify_findings(report,signing=True)
                else:
                    verify_findings(report,signing=True)
                if version==FORMAT and flagged:
                    forged=copy.deepcopy(report)
                    pick(forged["findings"],"H05")["date_checks"][0]["evidence"]=[]
                    with self.assertRaises(ValueError):
                        verify_findings(forged)
