import copy
import unittest

from acceptance_authority import CLAUSE
from controls import VERSION, execute
from delivery_batches import FINAL_FORMAT, evidence_edges, gaps, page_sources, verify_sources
from graph import build_graph
from performance import compute, verify_findings
from test_acceptance_authority import reconstruct, sign
from test_batch_final import SEPARATE, changed, final_record, packet
from test_delivery_batches import NAMED, RULE, contract, named_receipt, states


JOINT="终验须由郑敏、陈琪共同签字确认"
SINGLE="最终验收应由郑敏签名确认"


def example(names=("郑敏","陈琪"),*,final_clause=JOINT,batch_clauses=NAMED,batches=None,finals=None,
            extra_clauses=(),rule=SEPARATE,contract_edits=None,**kwargs):
    conditions=[(CLAUSE,"验收签认约定",v) for v in batch_clauses]
    if final_clause:
        conditions.append((CLAUSE,"终验签认约定",final_clause))
    conditions.extend((CLAUSE,"验收签认约定",v) for v in extra_clauses)
    agreement=changed(contract(rule),**(contract_edits or {}))+conditions
    if batches is None and batch_clauses:
        batches=[named_receipt(1,["周宁"]),named_receipt(2,["林岚","何平"])]
    if finals is None:
        finals=[sign(final_record(),*names)]
    return packet(agreement=agreement,batches=batches,finals=finals,**kwargs)


def three_scoped(names=("郑敏","陈琪"),*,claimed="郑敏、陈琪、陈和平",**options):
    second=["林岚","何平","陈和平"]
    return example(names,final_clause="终验须由"+claimed+"共同签字确认",
                   batch_clauses=["第一批验收须由周宁签字确认","第二批验收须由"+"、".join(second)+"共同签字确认"],
                   batches=[named_receipt(1,["周宁"]),named_receipt(2,second)],**options)


class FinalSignatoryTests(unittest.TestCase):
    def test_three_people_on_a_batch_and_on_the_final_are_distinct_requirements(self):
        for names,expected in ((["郑敏","陈琪"],"missing"),(["郑敏","陈琪","陈和平"],"ok"),(["郑敏","陈琪","何平"],"risk")):
            graph=three_scoped(names)
            h,phases,cash=states(graph)
            entry=h["batch_acceptance"]
            final=entry["separate_final"]
            self.assertEqual([b["status"] for b in entry["batches"]],["ok","ok"])
            self.assertEqual(final["signing_requirement"]["required"],["郑敏","陈琪","陈和平"])
            self.assertEqual(final["status"],expected)
            cross=[e for e in evidence_edges([h,*phases]) if e["type"]=="final_name_on_batch_record"]
            self.assertEqual(len(cross),int(expected=="missing"))
            if expected=="missing":
                other,=final["signatures_on_batches"]
                self.assertEqual((other["name"],other["batch_index"],other["unit"]),("陈和平",2,"d03"))
                self.assertEqual((cross[0]["from"],cross[0]["to"]),(final["signing_requirement"]["clause_ref"],other["signature_ref"]))
                self.assertFalse(any(e["type"]=="final_named_signature" for e in evidence_edges([h,*phases])))
                self.assertIsNone(entry["completion_on"])
                self.assertEqual([p["status"] for p in phases],["ok","ok","ok","missing"])
                for payment in (phases[-1],cash):
                    basis=payment["final_signature_condition"]
                    self.assertEqual(basis["missing_names"],["陈和平"])
                    self.assertEqual(basis["batch_signatures"],[other["signature_ref"]])
                    self.assertTrue(set(basis["evidence"])<=set(payment["evidence"]))
                self.assertFalse(any("final_signature_condition" in p for p in phases[:3]))
            else:
                self.assertNotIn("final_signature_condition",cash)
        for names in ("郑敏、陈琪与陈和平","郑敏、陈琪和陈和平"):
            self.assertEqual(states(three_scoped(claimed=names))[0]["batch_acceptance"]["separate_final"]["signing_requirement"]["required"],
                             ["郑敏","陈琪","陈和平"])
        for names in ("郑敏、陈琪或陈和平","郑敏、陈琪、采购部","郑敏、陈琪、陈琪"):
            self.assertFalse(states(three_scoped(claimed=names))[0]["batch_acceptance"]["separate_final"].get("signing_requirement"))
        foreign=sign(final_record(batch_receipt_refs="YS-10、YS-201"),"郑敏","陈琪")
        h,_,cash=states(three_scoped(finals=[foreign]))
        self.assertNotIn("signatures_on_batches",h["batch_acceptance"]["separate_final"])
        self.assertNotIn("final_signature_condition",cash)

    def test_scoped_roster_replay_checks_the_expert_input_and_archived_geometry(self):
        from delivery_batches import STANDARD_FORMAT, verify_roster_evidence
        from graph import link_procedures
        from model import audit_graph
        from unittest.mock import patch
        g=three_scoped()
        read=lambda doc,page:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==doc)
        fs=execute(g,g["profile"])
        with patch("model.structured",return_value=({"followups":[]},{"model":"fixture"})):
            _,expert=audit_graph(g,fs)
        calls={"expert":expert,"pages":[]}
        link_procedures(g,fs,calls)
        policy={**VERSION,"profile":g["profile"]}
        paper={"graph":g,"findings":fs,"policy":policy,"calls":calls}
        verify_sources(paper,read)
        verify_findings(paper)
        verify_roster_evidence(paper)
        with self.assertRaisesRegex(ValueError,"行框"):
            verify_roster_evidence(paper,read_layout=lambda doc,page:{"lines":{}})
        for field in ("batch_acceptance","final_signature_condition"):
            changed=copy.deepcopy(paper)
            proc=next(p for p in changed["calls"]["expert"]["input"]["procedures"] if field in p)
            del proc[field]
            with self.assertRaisesRegex(ValueError,"专家输入"): verify_roster_evidence(changed)
        old=three_scoped()
        old["delivery_batch_sources"]=page_sources(old,read,STANDARD_FORMAT)
        old["gaps"]=[k for k in old["gaps"] if k["quality"]!="delivery_batch_clause"]+gaps(old["delivery_batch_sources"])
        previous=execute(old,old["profile"])
        old["edges"].extend(evidence_edges(previous))
        historical={"graph":old,"findings":previous,"policy":{**policy,"version":"2026.11.28.22","delivery_batches":STANDARD_FORMAT}}
        verify_sources(historical,read)
        self.assertNotIn("signing_requirement",next(f["batch_acceptance"] for f in previous if f["rule"]=="H02")["separate_final"])
        with self.assertRaisesRegex(ValueError,"会签名单.*重审"): verify_sources(historical,read,signing=True)

    def test_only_the_final_original_can_supply_final_signatures(self):
        for g,names,batch_edges in ((example(),["郑敏","陈琪"],3),(example(["郑敏"],final_clause=SINGLE,batch_clauses=[]),["郑敏"],0)):
            h,phases,cash=states(g)
            check=h["batch_acceptance"]
            final=check["separate_final"]
            self.assertEqual((h["status"],cash["status"],check["completion_on"]),("ok","ok","2026-09-25"))
            self.assertEqual([p["status"] for p in phases],["ok"]*4)
            requirement=final["signing_requirement"]
            self.assertEqual(requirement["required"],names)
            record=next(r for r in check["records"] if r.get("role")=="final")
            self.assertEqual([s["name"] for s in record["signing"]["signed"]],names)
            self.assertNotIn(requirement["clause_ref"],phases[1]["evidence"]+phases[2]["evidence"])
            self.assertNotIn(record["unit"],phases[1]["scope"]+phases[2]["scope"])
            witnesses=evidence_edges([h,*phases])
            self.assertEqual(sum(e["type"]=="batch_named_signature" for e in witnesses),batch_edges)
            final_links=[e for e in witnesses if e["type"]=="final_named_signature"]
            self.assertEqual([e["to"] for e in final_links],[s["fact"] for s in record["signing"]["signed"]])
            self.assertTrue(all(e["from"]==requirement["clause_ref"] and {e["from"],e["to"]}<=set(e["evidence"]) for e in final_links))

    def test_other_batches_and_combined_or_repeated_names_do_not_fill_a_missing_signature(self):
        batches=[named_receipt(1,["周宁"]),named_receipt(2,["林岚","陈琪"])]
        clauses=[NAMED[0],"第二批验收须由林岚、陈琪共同签字确认"]
        for names,status in ((["郑敏"],"missing"),(["郑敏","林岚"],"risk"),(["郑敏","陈琪","陈琪"],"missing"),
                             (["郑敏、陈琪"],"missing"),(["郑 敏","陈琪"],"missing"),([],"missing")):
            with self.subTest(names=names):
                h,phases,cash=states(example(names,batches=batches,batch_clauses=clauses))
                check=h["batch_acceptance"]
                r=next(r for r in check["records"] if r.get("role")=="final")
                self.assertEqual((r["signing"]["status"],h["status"],cash["status"]),(status,status,"missing"))
                self.assertEqual([p["status"] for p in phases],["ok"]*3+[status])
                self.assertIsNone(check["completion_on"])
                self.assertTrue(all(s["unit"]==r["unit"] for s in r["signing"]["signed"]))
                self.assertFalse(any(e["type"] in ("batch_final_basis","final_named_signature") for e in evidence_edges([h,*phases])))
                if names==["郑敏","林岚"]:
                    self.assertEqual((r["signing"]["missing_names"],r["signing"]["other_names"]),(["陈琪"],["林岚"]))
        h,ps,_=states(example(finals=[]))
        final=h["batch_acceptance"]["separate_final"]
        self.assertEqual((final["records"],final["signing_requirement"]["required"]),([],["郑敏","陈琪"]))
        self.assertEqual([p["status"] for p in ps],["ok","ok","ok","missing"])

    def test_omitted_original_line_and_unconfirmed_signature_are_still_inspectable(self):
        quote="验收签认：陈琪（已签字）"
        raw=example(["郑敏"],omissions=[(4,quote)])
        pending=reconstruct(example(),lambda item:not(item[0]=="d04" and item[1]["quote"]==quote))
        for g,has_observation in ((raw,False),(pending,True)):
            h,phases,_=states(g)
            r=next(r for r in h["batch_acceptance"]["records"] if r.get("role")=="final")
            signing=r["signing"]
            witness=next(s for s in signing["signed"] if s["quote"]==quote)
            self.assertTrue(witness["native"] and witness["line"] and not witness["confirmed"])
            self.assertEqual(bool(witness["facts"]),has_observation)
            self.assertEqual(signing["missing_names"],["陈琪"])
            self.assertIn("陈琪",h["detail"])
            self.assertEqual([p["status"] for p in phases],["ok","ok","ok","missing"])
        g=example()
        next(f for f in g["facts"] if f["doc"]=="d04" and f["quote"]==quote)["value"]="陈 琪（已签字）"
        h,ps,_=states(g)
        self.assertIsNone(h["batch_acceptance"]["completion_on"])
        self.assertNotEqual(ps[-1]["status"],"ok")

    def test_same_physical_pdf_keeps_batch_and_final_signature_pages_distinct(self):
        batches=[named_receipt(1,["周宁"]),named_receipt(2,["林岚","陈琪"])]
        clauses=[NAMED[0],"第二批验收须由林岚、陈琪共同签字确认"]
        for names,status in ((["郑敏","陈琪"],"ok"),(["郑敏"],"missing")):
            original=example(names,batches=batches,batch_clauses=clauses)
            pages,attestations=[],{}
            for page,doc in enumerate(original["documents"],1):
                facts=[f for f in original["facts"] if f["doc"]==doc["id"]]
                raw=[{k:f[k] for k in ("field","value","quote","region")} for f in facts]
                lines={str(i):[[0,.1,.9,.2]] for i in range(1,len(facts)+1)}
                for i,f in enumerate(facts,1):
                    if f["attestation"]:
                        attestations[f"packet/p{page}/f{i}"]=f["attestation"]
                pages.append({"doc":"packet","number":page,"sha256":"demo","text":"\n".join(f["quote"] for f in facts),
                              "layer":{"type":"text","clause_text_only":True,"lines":lines},
                              "extraction":{"output":{"quality":"readable","facts":raw}}})
            g=build_graph([{"id":"packet","name":"合成采购合订件.pdf","sha256":"fixture"}],pages,attestations)
            g["warranty_as_of"]="2026-12-31"
            g["profile"]=original["profile"]
            h,phases,_=states(g)
            final=next(r for r in h["batch_acceptance"]["records"] if r.get("role")=="final")
            self.assertEqual((h["status"],[f["status"] for f in phases]),(status,["ok"]*3+[status]))
            self.assertEqual([(r["page"],r["name"]) for r in final["signing"]["signed"]],[(4,name) for name in names])
            self.assertTrue(all(e["to"].startswith("packet/p4/") for e in evidence_edges([h,*phases]) if e["type"]=="final_named_signature"))

    def test_completed_signatures_cannot_cure_quality_reference_identity_or_payment_timing(self):
        for value,status in (({"inspection_basis":"柜温不高于9℃","measured_result":"柜温8℃"},"issue"),
                             ({"batch_receipt_refs":"YS-10、YS-29"},"risk"),({"accepted_on":"2026-09-18"},"risk")):
            h,ps,_=states(example(finals=[sign(final_record(**value),"郑敏","陈琪")]))
            check=h["batch_acceptance"]
            final=next(r for r in check["records"] if r.get("role")=="final")
            self.assertEqual((final["signing"]["status"],h["status"],check["completion_on"]),("ok",status,None))
            self.assertEqual([p["status"] for p in ps],["ok","ok","ok","risk"])
        for edits in ({"buyer":"另一采购方"},{"accepted_on":"2026-09-01"}):
            h,ps,_=states(example(finals=[sign(final_record(**edits),"郑敏","陈琪")]))
            self.assertNotEqual(h["status"],"ok")
            self.assertFalse(any(e["type"]=="final_named_signature" for e in evidence_edges([h,*ps])))
        h,ps,cash=states(example(paid="2026-11-22"))
        self.assertEqual((h["status"],ps[-1]["status"],cash["status"]),("ok","ok","risk"))
        h,ps,_=states(example(contract_edits={"effect_clause":"本合同自双方盖章并经甲方董事会批准后生效"}))
        self.assertNotIn("ok",[p["status"] for p in ps])
        self.assertFalse(h["batch_acceptance"]["completion_on"])

    def test_competing_clauses_unresolved_authority_and_different_final_versions_are_held(self):
        for kwargs in ({"extra_clauses":[SINGLE]},{"extra_clauses":[NAMED[0]]},{"batch_clauses":[NAMED[0]]},
                       {"final_clause":"终验及整改复验须由郑敏、陈琪共同签字确认"},{"final_clause":"终验须由郑敏或陈琪签字确认"},
                       {"final_clause":"终验须由采购负责人签字确认"},{"final_clause":"终验须由同上签字确认"},
                       {"rule":RULE},{"omissions":[(1,"附加约定：另须监理会签")]},
                       {"finals":[sign(final_record(),"郑敏","陈琪"),sign(final_record(acceptance_number="ZY-31"),"郑敏","陈琪")]}):
            with self.subTest(kwargs=kwargs):
                h,ps,_=states(example(**kwargs))
                self.assertNotEqual(h["status"],"ok")
                self.assertFalse(any(e["type"]=="final_named_signature" for e in evidence_edges([h,*ps])))
        h,ps,_=states(example(omissions=[(4,"签认附注：陈琪一栏为代签，授权未附")]))
        self.assertEqual([p["status"] for p in ps],["missing"]*4)
        self.assertFalse(h["batch_acceptance"]["completion_on"])

    def test_current_replay_binds_every_final_endpoint_and_preserves_previous_rules(self):
        g=example()
        texts={d["id"]:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==d["id"]) for d in g["documents"]}
        read=lambda d,n:texts[d]
        findings=execute(g,g["profile"])
        g["edges"].extend(evidence_edges(findings))
        report={"graph":g,"findings":findings,"policy":{**VERSION,"profile":g["profile"]}}
        verify_sources(report,read)
        verify_findings(report)
        for part in ("edge","scope","signer","version"):
            altered=copy.deepcopy(report)
            h=next(f["batch_acceptance"] for f in altered["findings"] if f.get("batch_acceptance"))
            if part=="edge":
                next(e for e in altered["graph"]["edges"] if e["type"]=="final_named_signature")["to"]="d03/p1/f9"
            elif part=="scope":
                h["separate_final"]["signing_requirement"]["clause_ref"]=h["batches"][0]["signing_requirement"]["clause_ref"]
            elif part=="signer":
                next(r for r in h["records"] if r.get("role")=="final")["signing"]["signed"][0]["confirmed"]=False
            else:
                altered["policy"]["delivery_batches"]=FINAL_FORMAT
            with self.assertRaises(ValueError):
                verify_sources(altered,read) if part in ("edge","version") else verify_findings(altered)
        g["delivery_batch_sources"]=page_sources(g,read,FINAL_FORMAT)
        g["gaps"]=[v for v in g["gaps"] if v["quality"]!="delivery_batch_clause"]+gaps(g["delivery_batch_sources"])
        old=compute(g)
        self.assertEqual([f["status"] for f in old if f["rule"]=="H04"],["missing"]*4)
        self.assertFalse(any(e["type"]=="final_named_signature" for e in evidence_edges(old)))
