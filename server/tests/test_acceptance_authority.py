import copy
import unittest

from acceptance_authority import CLAUSE, SIGNER, verify_sources, witness_edges
from controls import VERSION, execute
from graph import build_graph
from performance import ADDENDUM_FORMAT, compute, verify_findings
from test_performance import CONTRACT, RECEIPT, WARRANTY, BANK_DOC, SIGN_FIELDS, material
from test_reinspection import OLD, FIX, FINAL


JOINT = "终验须由周宁、林岚共同签字确认"
BOTH = "终验及整改复验均须由周宁、林岚共同签字确认"


def contract(clause):
    return [*CONTRACT,(CLAUSE,"验收签认约定",clause)] if clause else CONTRACT


def sign(template, *names):
    label="复验签认" if template[0][0]=="reinspection" else "验收签认"
    return [r for r in template if r[0]!=SIGNER]+[(SIGNER,label,n+"（已签字）") for n in names]


def sample(clause=JOINT, names=("周宁","林岚"), *, extra=(), edit=None, omissions=()):
    return material([contract(clause),sign(RECEIPT,*names),WARRANTY,BANK_DOC,*extra],edit,omissions=omissions)


def checks(graph):
    findings=compute(graph)
    return next(f for f in findings if f["rule"]=="H02"),[f["status"] for f in findings if f["rule"]=="H04"]


class AcceptanceAuthorityTests(unittest.TestCase):
    def test_explicit_joint_roster_keeps_each_name_and_compares_the_last_required_date(self):
        from acceptance_authority import instruction
        from model import audit_graph
        from unittest.mock import patch
        names=("周宁","林岚","陈和平")
        dates=[(2,n+"签认日期：2026年9月"+str(d)+"日") for n,d in zip(names,(20,25,27))]
        for span in ("周宁、林岚、陈和平","周宁、林岚与陈和平","周宁、林岚和陈和平"):
            clause="终验须由"+span+"共同签字确认"
            graph=sample(clause,names,omissions=dates,edit=lambda i,k,l,v:"2026年9月25日" if k=="paid_on" else v)
            findings=execute(graph,graph["profile"])
            acceptance=next(f for f in findings if f["rule"]=="H02")["acceptance_authority"]
            paid=next(f for f in findings if f["rule"]=="H05")
            self.assertEqual(acceptance["required"],list(names))
            self.assertEqual((paid["status"],paid["signer_timing"]["days"]),("risk",-2))
            with patch("model.structured",return_value=({"followups":[]},{})):
                _,expert=audit_graph(graph,findings)
            basis=next(p["joint_acceptance_timing"] for p in expert["input"]["procedures"] if p["rule"]=="H05")
            self.assertEqual([r["quote"] for r in basis["dates"]],[raw for _,raw in dates])
            self.assertEqual(basis["clause"][0]["quote"],"验收签认约定："+clause)
        for bad in ("周宁、林岚或陈和平","周宁、林岚、林岚","周宁、林岚、采购部","周宁、林岚等","周宁、林岚、项目负责人"):
            self.assertIsNone(instruction("验收签认约定：终验须由"+bad+"共同签字确认",listed=True))
        for people,days in ((names[:2],dates),(names,dates[:2]),(names,[*dates,(2,dates[-1][1])])):
            graph=sample("终验须由周宁、林岚、陈和平共同签字确认",people,omissions=days)
            paid=next(f for f in compute(graph) if f["rule"]=="H05")
            self.assertEqual((paid["signer_timing"]["state"],paid["signer_timing"]["days"]),("incomplete",None))

    def test_combined_model_dates_only_bind_to_one_contiguous_verbatim_run(self):
        from signer_timing import bind_date_transcriptions, dated_line, source_graph
        lines=[p+"签认日期：2026年9月"+str(d)+"日" for p,d in zip(("周宁","林岚","陈和平"),(20,25,27))]
        def source(text,rows=(1,2,3),text_only=True,disputed=False):
            native=[dated_line("d02","d02",1,i,line,[]) for i,line in zip(rows,lines*2)]
            term=dated_line("d02","d02",1,None,text,[{"id":"d02/p1/f9","status":"disputed" if disputed else "visual"}])
            observations=[*native,term]
            bind_date_transcriptions(observations,{"d02/p1":{"clause_text_only":text_only}})
            return term,[e for e in source_graph(observations)[1] if e["type"]=="transcribed_signer_date"]
        joined="".join(lines)
        observation,edges=source(joined)
        self.assertEqual(observation["printed_rows"],[f"signer-date/d02/p1/l{i}" for i in (1,2,3)])
        self.assertEqual([e["to"] for e in edges],observation["printed_rows"])
        for text,options in ((joined.replace("27日","28日"),{}),(joined,{"rows":(1,2,4)}),
                (joined,{"rows":(1,2,3,4,5,6)}),(joined,{"text_only":False}),(joined,{"disputed":True}),
                (joined+"待核",{}),(lines[1]+lines[0],{})):
            term,edges=source(text,**options)
            self.assertNotIn("printed_rows",term)
            self.assertFalse(edges)

    def test_single_and_joint_require_exact_persons_on_independent_rows(self):
        for clause,names,mode in (("终验由周宁签字确认",("周宁",),"single"),(JOINT,("林岚","周宁"),"joint")):
            graph=sample(clause,names)
            f,phases=checks(graph)
            entry=f["acceptance_authority"]
            self.assertEqual((entry["mode"],entry["status"],f["status"],phases),(mode,"ok","ok",["ok"]*3))
            record,=entry["records"]
            self.assertEqual([r["name"] for r in record["signed"]],list(names))
            self.assertEqual(len(witness_edges([f])),len(names))
            for edge in witness_edges([f]):
                self.assertTrue(set(edge["evidence"])<=set(f["evidence"]))
            self.assertTrue(all(e["to"]==e["evidence"][0] for e in graph["edges"] if e["type"] in (SIGNER,CLAUSE)))

    def test_missing_confirmations_wrong_signers_combined_names_and_role_only(self):
        for names,expected,due in ((("周宁",),"missing",["林岚"]),(("周宁","李开"),"risk",["林岚"]),
                                   (("周宁","周宁"),"missing",["周宁","林岚"]),(("周宁","林岚","李开"),"risk",[]),
                                   (("周宁、林岚",),"missing",["周宁","林岚"]),(("周宁 林岚",),"missing",["周宁","林岚"]),
                                   (("项目负责人",),"missing",["周宁","林岚"])):
            with self.subTest(names=names):
                f,phases=checks(sample(names=names))
                entry=f["acceptance_authority"]
                self.assertEqual((f["status"],entry["records"][0]["missing_names"],phases),(expected,due,["ok",expected,expected]))
                self.assertFalse(witness_edges([f]))
        g=sample()
        facts=[f for f in g["facts"] if f["field"]==SIGNER and f["doc"]=="d02"]
        self.assertEqual(len(facts),2)
        # Rebuild through the normal input path with only the first person's attestation.
        f,_=checks(reconstruct(g,lambda x:x[0]!="d02" or "林岚" not in x[1]["quote"]))
        self.assertEqual(f["acceptance_authority"]["records"][0]["missing_names"],["林岚"])
        self.assertEqual(checks(sample(None,("仓管员",)))[0]["status"],"missing")

    def test_supplemental_clauses_omissions_bad_link_and_condition_qualifiers(self):
        for clause in ("终验由周宁或林岚任选一人签字确认","终验须由项目经理签字确认","终验须由周宁、林岚共同签字确认并取得总监审批"):
            self.assertEqual(checks(sample(clause))[0]["acceptance_authority"]["mode"],"unresolved")
        for g in (sample(omissions=[(1,"备注：验收另须质量总监批准")]),sample(omissions=[(2,"附记：由仓库代办")]),
                  sample(extra=[[("other","","待辨附件")]]),sample(edit=lambda i,f,l,v:"YL-773" if i==2 and f=="contract_id" else v)):
            f,phases=checks(g)
            self.assertNotEqual(f["status"],"ok")
            self.assertFalse(witness_edges([f]))
            self.assertNotEqual(phases[1],"ok")
        g=material([CONTRACT,sign(RECEIPT,"周宁"),WARRANTY,BANK_DOC],omissions=[(1,"终验须由周宁签字确认")])
        f,_=checks(g)
        self.assertEqual(f["acceptance_authority"]["status"],"missing")
        self.assertTrue(any(r["line"] and not r["fact"] for r in g["acceptance_authority_sources"]["clauses"]))

    def test_receipt_day_and_quantity_defects_take_precedence(self):
        bad=sample(names=("周宁",),edit=lambda i,f,l,v:"柜温8℃" if f=="measured_result" else v)
        f,phases=checks(bad)
        self.assertEqual((f["status"],f["acceptance_authority"]["status"],phases),("issue","missing",["ok","risk","risk"]))
        g=sample(edit=lambda i,f,l,v:"2026-09-20" if f=="paid_on" else v)
        paid=next(f for f in compute(g) if f["rule"]=="H05")
        self.assertEqual(paid["status"],"missing")
        self.assertIn("时分",paid["detail"])

    def test_signature_terms_must_be_in_force_at_acceptance(self):
        def dated(value,until=None):
            rows=contract(JOINT)+([("valid_until","合同有效期至",until)] if until else [])
            graph=material([rows,sign(RECEIPT,"周宁","林岚"),WARRANTY,BANK_DOC],
                           lambda i,f,l,v:value if f=="accepted_on" else v)
            return checks(graph)[0]
        for date,until,status in (("2026-09-01",None,"missing"),("2026-08-31",None,"risk"),
                                  ("2026-09-20","2026-09-17","risk")):
            f=dated(date,until)
            self.assertEqual(f["acceptance_authority"]["records"][0]["status"],status)
            self.assertFalse(witness_edges([f]))

    def test_authority_on_both_original_and_reinspection_required_to_close(self):
        for clause,first,last,outcome in ((BOTH,("周宁","林岚"),("周宁","林岚"),"closed"),
                                         (BOTH,("周宁",),("周宁","林岚"),"open"),
                                         (BOTH,("周宁","林岚"),("周宁","王平"),"open"),
                                         (JOINT,("周宁","林岚"),("周宁","林岚"),"open")):
            with self.subTest(clause=clause,first=first,last=last):
                g=material([contract(clause),sign(OLD,*first),FIX,sign(FINAL,*last),WARRANTY,BANK_DOC])
                f,phases=checks(g)
                self.assertEqual(f["reinspection"]["state"],outcome)
                self.assertEqual(f["status"],"ok" if outcome=="closed" else "issue")
                self.assertEqual(phases[:2],["ok","ok" if outcome=="closed" else "risk"])
                self.assertEqual([r["role"] for r in f["acceptance_authority"]["records"]],["acceptance","reinspection"])

    def test_same_native_line_cannot_turn_two_names_into_one_by_removing_space(self):
        g=sample("终验须由欧阳明月签字确认",("欧阳明月",))
        g=reconstruct(g,lambda x:True,replace=lambda doc,line:line.replace("欧阳明月","欧阳 明月") if doc=="d02" else line)
        f,_=checks(g)
        self.assertEqual(f["status"],"missing")
        row,=f["acceptance_authority"]["records"][0]["signed"]
        self.assertIn("欧阳 明月",row["quote"])
        self.assertFalse(row["confirmed"])
        self.assertFalse(witness_edges([f]))

    def test_recorded_source_relations_and_legacy_review(self):
        g=sample()
        fs=execute(g,g["profile"])
        g["edges"].extend(witness_edges(fs))
        paper={"graph":g,"findings":fs,"policy":{**VERSION,"profile":g["profile"]}}
        originals={d["id"]:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==d["id"]) for d in g["documents"]}
        read=lambda doc,page:originals[doc]
        verify_sources(paper,read)
        verify_findings(paper)
        for touch in ("row","link","edge","outcome","policy"):
            forged=copy.deepcopy(paper)
            ledger=forged["graph"]["acceptance_authority_sources"]
            if touch=="row": ledger["signatures"][0]["quote"]="验收签认：陈某"
            elif touch=="link": forged["graph"]["edges"].pop()
            elif touch=="edge": next(e for e in forged["graph"]["edges"] if e["type"]==SIGNER)["to"]="d03"
            elif touch=="policy": del forged["policy"]["acceptance_authority"]
            else: next(f for f in forged["findings"] if f["rule"]=="H02")["acceptance_authority"]["required"]=["王平"]
            with self.assertRaises(ValueError):
                verify_findings(forged) if touch=="outcome" else verify_sources(forged,read)
        old=copy.deepcopy(paper)
        old["policy"]={"performance_checks":ADDENDUM_FORMAT}
        del old["graph"]["acceptance_authority_sources"]
        for f in old["findings"]:
            f.pop("signer_timing", None)
        verify_sources(old,read)
        with self.assertRaisesRegex(ValueError,"旧版"):
            verify_sources(old,read,signing=True)


def reconstruct(graph, keep, replace=lambda doc,line:line):
    pages,attestations=[],{}
    for doc in graph["documents"]:
        unit=doc["id"]
        facts=[f for f in graph["facts"] if f["doc"]==unit]
        raw=[{k:f[k] for k in ("field","value","quote","region")} for f in facts]
        for f in facts:
            if f["field"] in SIGN_FIELDS and keep((unit,f)):
                attestations[f["id"]]=f["attestation"]
        pages.append({"doc":unit,"number":1,"sha256":"page","text":"\n".join(replace(unit,f["quote"]) for f in facts),
                      "layer":{"type":"text","clause_text_only":True,"lines":{str(i):[[0,.1,.9,.2]] for i in range(1,len(facts)+1)}},
                      "extraction":{"output":{"quality":"readable","facts":raw}}})
    result=build_graph(graph["documents"],pages,attestations)
    result["profile"]=graph["profile"]
    return result
