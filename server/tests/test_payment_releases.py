import copy
import unittest

from config import PERFORMANCE
from controls import VERSION,execute
from payment_releases import verify
from performance import compute,verify_findings
from test_performance import BANK_DOC,CONTRACT,RECEIPT,WARRANTY,material


MANDATE=("other","放行约定","第二期暂缓自验收日起执行，须经甲方演练林岚签字放行")
HOLD=("other","付款意见","第二期验收款暂缓支付")
NUMBER=("acceptance_number","验收单编号","YS-12345678")
RELEASE=[("payment_release","","付款放行单"),*CONTRACT[1:5],("original_acceptance","原验收单编号",NUMBER[2]),
         ("other","放行决定","解除第二期验收款暂缓，自签字日起恢复支付"),("release_signed_on","放行签字日期","2026-09-23"),
         ("approval_signer","审批签认","演练林岚（已签字）")]
BANK=[(f,l,"2026-09-24" if f=="paid_on" else v) for f,l,v in BANK_DOC]


def fixture(*,release=RELEASE,authority=MANDATE,notes=(HOLD,),edit=None,extra=(),omissions=(),attestations=None):
    groups=[[*CONTRACT,*([authority] if authority else [])],[*RECEIPT,NUMBER,*notes],WARRANTY,BANK]
    if release:
        groups.append(release)
    groups.extend(extra)
    graph=material(groups,edit=edit,omissions=omissions,attestations=attestations)
    graph["payment_release_as_of"]="2026-11-25"
    texts={d["id"]:"\n".join(f["quote"] for f in graph["facts"] if f["doc"]==d["id"]) for d in graph["documents"]}
    for i,s in omissions:
        texts[f"d{i:02d}"]+="\n"+s
    return graph,lambda doc,n:texts[doc]


def findings(graph):
    fs=compute(graph)
    return [f for f in fs if f["rule"]=="H04"],[f for f in fs if f["rule"]=="H05"]


class SignedPaymentReleaseTests(unittest.TestCase):
    def test_current_conditions_and_each_bank_date(self):
        for signed,expected,when in [("23","missing","after"),("24","missing","same_day"),("25","risk","before")]:
            with self.subTest(signed=signed):
                g,_=fixture(edit=lambda i,k,l,v:"2026-09-"+signed if k=="release_signed_on" else v)
                fs=compute(g)
                self.assertEqual([f["status"] for f in fs[:6]],["ok","ok","ok","ok","missing","ok"])
                stage=fs[4]["payment_opinion"];pay=fs[-1]
                self.assertEqual((stage["state"],stage["release"]["state"]),("hold","signature_pending"))
                self.assertEqual((pay["status"],pay["payment_opinion"]["release"]["written_timing"]),(expected,when))
                self.assertEqual(pay["payment_opinion"]["release"]["timing"],"unknown")
                self.assertFalse(any("payment_opinion" in fs[i] for i in (3,5)))
                r=stage["release"]
                for key in ("signature_ref","date_ref","original_ref","receipt_ref"):
                    self.assertIn(r[key],fs[4]["evidence"])
                self.assertNotIn("paid_on",r)

    def test_each_slip_and_quality_keep_their_own_facts(self):
        earlier=[(k,l,"2026-09-22" if k=="paid_on" else v) for k,l,v in BANK]
        g,_=fixture(extra=[earlier]);_,payments=findings(g)
        self.assertEqual([p["payment_opinion"]["release"]["written_timing"] for p in payments],["after","before"])
        self.assertEqual([p["status"] for p in payments],["missing","risk"])
        g,_=fixture(edit=lambda i,k,l,v:"柜温8℃" if k=="measured_result" else v)
        self.assertEqual([f["status"] for f in compute(g)],["ok","issue","ok","ok","risk","risk","missing"])

    def test_unsigned_and_different_signer_or_receipt(self):
        cases=[("approval_signer","演练何平（已签字）","signer_mismatch"),("approval_signer","演练林岚（待签）","pending"),
               ("original_acceptance","YS-12345679","reference_mismatch"),("original_acceptance","YS-12 345678","pending"),
               ("contract_id","YL-122","pending"),("release_signed_on","2026-09-20","pending"),
               ("release_signed_on","2026-09-2 3","pending"),("release_signed_on","2027-09-23","future"),("subject","其他标的","pending")]
        for field,value,state in cases:
            with self.subTest(field=field,value=value):
                g,_=fixture(edit=lambda i,k,l,v:value if i==5 and k==field else v)
                stages,bank=findings(g)
                self.assertEqual(stages[1]["payment_opinion"]["release"]["state"],state)
                expected="risk" if state in ("reference_mismatch","signer_mismatch") else "missing"
                self.assertEqual([f["status"] for f in [*stages,*bank]],["ok",expected,"ok",expected])
        g,_=fixture(attestations={"d05/p1/f9":{"decision":"dispute"}})
        self.assertNotEqual(findings(g)[0][1]["status"],"ok")
        g,_=fixture(release=[*RELEASE[:-2],("approved_on","审批日期","2026-09-23"),RELEASE[-1]])
        self.assertEqual(findings(g)[0][1]["payment_opinion"]["release"]["state"],"pending")

    def test_qualifications_conflicts_and_scope(self):
        for opts in [dict(extra=[RELEASE]),dict(authority=None),dict(release=None),dict(omissions=[(5,"放行备注：尚须另行审批")]),
                     dict(omissions=[(3,"特别说明：此前付款放行已撤回")]),dict(omissions=[(1,"付款说明：暂缓放行须另经董事会批准")]),
                     dict(notes=[HOLD,("other","付款备注","同意支付第二期验收款")]),
                     dict(notes=[("other","付款意见","本合同项下全部付款暂缓")]),
                     dict(edit=lambda i,k,l,v:v.replace("第二期","第一期") if l=="放行决定" else v)]:
            with self.subTest(opts=list(opts)):
                g,_=fixture(**opts);stages,bank=findings(g)
                self.assertNotEqual(stages[1]["status"],"ok");self.assertNotEqual(bank[0]["status"],"ok")

    def test_raw_mandate_and_decision_with_no_model_observation(self):
        release=[r for r in RELEASE if r[1]!="放行决定"]
        g,_=fixture(authority=None,release=release,omissions=[(1,MANDATE[1]+"："+MANDATE[2]),(5,RELEASE[6][1]+"："+RELEASE[6][2])])
        stages,bank=findings(g)
        self.assertEqual((stages[1]["status"],bank[0]["status"]),("missing","missing"))
        rows=stages[1]["payment_opinion"]["release"]["sources"]
        self.assertTrue(all(r["line"] and not r["facts"] for r in rows if r["role"] in ("authority","decision")))
        g,read=fixture()
        from payment_releases import sources
        next(n for n in g["nodes"] if n["id"]=="d05/p1")["clause_text_only"]=False
        g["payment_release_sources"]=sources(g,read)
        self.assertNotEqual(findings(g)[0][1]["status"],"ok")

    def test_ledger_edges_and_issued_recomputation(self):
        g,read=fixture()
        paper={"policy":{**VERSION,"profile":PERFORMANCE},"graph":g,"findings":execute(g,PERFORMANCE)}
        verify(paper,read);verify_findings(paper)
        verify(paper,read,submitted="2026-11-24T16:01:00+00:00")
        with self.assertRaises(ValueError):
            verify(paper,read,submitted="2026-11-24T15:59:00+00:00")
        for key in ("line","edge","decision","method"):
            with self.subTest(key=key):
                changed=copy.deepcopy(paper)
                if key=="line":changed["graph"]["payment_release_sources"]["lines"][0]["quote"]+=" 已修改"
                if key=="edge":next(e for e in changed["graph"]["edges"] if e["type"]=="payment_release_basis")["line"]+=1
                if key=="decision":next(f for f in changed["findings"] if f["rule"]=="H05")["payment_opinion"]["release"]["timing"]="before"
                if key=="method":del changed["policy"]["payment_releases"]
                with self.assertRaises(ValueError):
                    verify_findings(changed) if key=="decision" else verify(changed,read)
