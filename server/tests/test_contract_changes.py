import copy
import unittest
import pypdfium2 as pdfium
from PIL import Image

from contract_changes import verify_sources
from controls import VERSION, execute
from documents import clause_text_only, layer_type
from performance import NATIVE_FORMAT, compute, verify_findings
from test_performance import CONTRACT, RECEIPT, WARRANTY, BANK_DOC, material


CHANGE = [("contract_addendum","","采购合同补充协议"),("addendum_number","补充协议编号","BC-121"),
          ("base_contract_ref","原合同编号","YL-121"),*CONTRACT[2:5],
          ("change_scope","变更范围","仅变更验收标准，其余条款不变"),
          ("previous_criterion","原验收标准","柜温不高于4℃"),("revised_criterion","变更后验收标准","柜温不高于2℃"),
          ("change_timing","变更适用时点","仅适用于本协议生效后进行的验收"),("change_effect_clause","协议生效条款","本协议自双方盖章之日起生效"),
          ("buyer_sealed_on","甲方盖章日期","2026-09-10"),("seller_sealed_on","乙方盖章日期","2026-09-12"),*CONTRACT[8:10]]
GROUPS = [CONTRACT,CHANGE,RECEIPT,WARRANTY,BANK_DOC]


def case(changed=None, receipt=None, *extra, omissions=()):
    def edit(i,field,label,value):
        return ((changed or {}) if i==2 else (receipt or {}) if i==3 else {}).get(field,value)
    return material([*GROUPS,*extra],edit,omissions=omissions)


def assessment(graph):
    findings=compute(graph)
    return next(f for f in findings if f["rule"]=="H02"), [f["status"] for f in findings if f["rule"]=="H04"]


class ContractChangeTests(unittest.TestCase):
    def test_stricter_limit_overrides_stale_basis_with_both_pages(self):
        graph=case()
        finding, phases=assessment(graph)
        change=finding["quality_change"]
        self.assertEqual((finding["status"],phases),("issue",["ok","risk","risk"]))
        self.assertEqual((change["state"],change["effective_on"],change["accepted_on"]),("applied","2026-09-12","2026-09-20"))
        self.assertIn("所引检验依据",finding["detail"])
        self.assertIn("柜温3°C",finding["detail"])
        edges={e["to"] for e in graph["edges"] if e["type"] in ("contract_id","base_contract_ref")}
        self.assertEqual(len(edges),1)
        cited={f["field"] for f in graph["facts"] if f["id"] in finding["evidence"]}
        self.assertTrue({"previous_criterion","revised_criterion","change_timing","change_effect_clause","measured_result",
                         "buyer_signature","seller_signature","accepted_on","inspection_basis"}<=cited)
        self.assertEqual(next(f for f in compute(graph) if f["rule"]=="H05")["status"],"missing")

    def test_positive_and_wrong_basis_and_prospective_late_relaxation(self):
        reading={"measured_result":"柜温1℃","inspection_basis":"柜温不高于2℃"}
        f,phases=assessment(case(receipt=reading))
        self.assertEqual((f["status"],phases),("ok",["ok"]*3))
        f,_=assessment(case(receipt={**reading,"inspection_basis":"柜温不高于4℃"}))
        self.assertEqual(f["status"],"risk")
        late={"revised_criterion":"柜温不高于8℃","seller_sealed_on":"2026-09-22"}
        f,phases=assessment(case(late,{"measured_result":"柜温6℃","inspection_basis":"柜温不高于8℃"}))
        self.assertEqual((f["status"],f["quality_change"]["state"],phases),("issue","original",["ok","risk","risk"]))

    def test_clauses_and_identity_that_cannot_establish_a_version(self):
        for field,value in (("base_contract_ref","YL-122"),("addendum_number","尾号121"),("seller","演练丙"),
                            ("subject","冷冻车"),("previous_criterion","柜温不高于8℃"),("revised_criterion","重量至少4kg"),
                            ("change_scope","验收标准、支付比例同时变更"),("change_timing","追溯至原合同签订日"),
                            ("change_effect_clause","经双方盖章并报董事会批准后生效"),
                            ("seller_signature","第三方（已盖章）"),("seller_sealed_on","2026-08-31"),
                            ("seller_sealed_on","2026-09-20"),("seller_signature",None)):
            with self.subTest(field=field,value=value):
                f,phases=assessment(case({field:value}))
                self.assertEqual((f["quality_change"]["state"],f["status"]),("pending","missing"))
                self.assertEqual(phases[1:],["missing","missing"])
        f,phases=assessment(case(None,None,CHANGE))
        self.assertEqual((f["quality_change"]["state"],phases),("pending",["missing"]*3))
        signed_failure={"acceptance_result":"不合格"}
        f,_=assessment(case({"seller_signature":None},signed_failure))
        self.assertEqual(f["status"],"issue")

    def test_draft_unsigned_mislinked_partial_and_unverified_sources(self):
        additional = [("change_state","补充协议状态","草案")]
        for graph,expected in ((material([CONTRACT,CHANGE+additional,RECEIPT,WARRANTY,BANK_DOC]),"missing"),
                               (case(receipt={"contract_id":"YL-X"}),"missing"),(case(receipt={"acceptance_scope":"分批验收"}),"risk")):
            f,phases=assessment(graph)
            self.assertEqual((f["quality_change"]["state"],phases),("pending",["ok",expected,expected]))
        graph=case()
        next(f for f in graph["facts"] if f["doc"]=="d02" and f["field"]=="seller_signature")["status"]="anchored"
        f,_=assessment(graph)
        self.assertEqual(f["quality_change"]["state"],"pending")
        for omission in ("付款备注：另须取得抵押担保", "原合同编号展示说明：本单只列尾号"):
            graph=case(omissions=[(2,omission)])
            f,phases=assessment(graph)
            self.assertEqual((f["quality_change"]["state"],phases),("pending",["missing"]*3))
            self.assertEqual(graph["quality_addenda"]["pages"][0]["uncovered"][0]["quote"],omission)
            edge,=[e for e in graph["edges"] if e["type"]=="base_contract_ref"]
            self.assertEqual(edge["to"],edge["evidence"][0])
        graph=case(omissions=[(1,"合同编号：仅列尾号")])
        self.assertTrue(graph["quality_addenda"]["limited_numbers"])
        self.assertEqual(assessment(graph)[0]["quality_change"]["state"],"pending")

    def test_unclassified_or_mixed_layout_and_closed_history(self):
        f,_=assessment(material([CONTRACT,RECEIPT],omissions=[(1,"合同另见双方签订的补充协议")]))
        self.assertEqual(f["quality_change"]["state"],"pending")
        graph=case()
        graph["quality_addenda"]["pages"][0]["text_only"]=False
        self.assertEqual(assessment(graph)[0]["quality_change"]["state"],"pending")
        f,phases=assessment(case(None,None,RECEIPT))
        self.assertEqual((f["quality_change"]["state"],phases),("pending",["ok","missing","missing"]))
        f,_=assessment(case(None,None,[("other","","待辨附件")]))
        self.assertEqual(f["quality_change"]["state"],"pending")
        self.assertNotIn("quality_change",next(f for f in compute(case(),NATIVE_FORMAT) if f["rule"]=="H02"))

    def test_small_raster_rider_requires_visual_read_even_on_a_native_page(self):
        with pdfium.PdfDocument.new() as pdf:
            page=pdf.new_page(595,842)
            self.assertTrue(clause_text_only(page))
            picture=pdfium.PdfImage.new(pdf)
            bitmap=pdfium.PdfBitmap.from_pil(Image.new("RGB",(20,12),"black"))
            picture.set_bitmap(bitmap)
            picture.set_matrix(pdfium.PdfMatrix(60,0,0,15,40,50))
            page.insert_obj(picture)
            page.gen_content()
            self.assertEqual(layer_type(page),"text")
            self.assertFalse(clause_text_only(page))
            page.close()
            bitmap.close()

    def test_day_only_payment_and_separated_digits_do_not_authorize_settlement(self):
        def same_day(i,field,label,value):
            return {"paid_on":"2026-09-20","inspection_basis":"柜温不高于2℃","measured_result":"柜温1℃"}.get(field,value)
        findings=compute(material(GROUPS,same_day))
        paid=next(f for f in findings if f["rule"]=="H05")
        self.assertEqual(paid["status"],"missing")
        self.assertIn("时分",paid["detail"])
        for change in ({"revised_criterion":"柜温不高于2 0℃"},{"base_contract_ref":"YL-1 21"}):
            f,_=assessment(case(change))
            self.assertEqual(f["quality_change"]["state"],"pending")

    def test_rederive_sources_findings_links_and_old_positive_signoff(self):
        graph=case()
        report={"policy":{**VERSION,"profile":graph["profile"]},"graph":graph,"findings":execute(graph,graph["profile"])}
        texts={f"d{i:02d}":"\n".join(l+"："+v if l else v for _,l,v in group) for i,group in enumerate(GROUPS,1)}
        read=lambda doc,page:texts[doc]
        verify_sources(report,read)
        verify_findings(report)
        for kind in ("quote","number","evidence","marker"):
            forged=copy.deepcopy(report)
            if kind=="quote":
                forged["graph"]["quality_addenda"]["signals"][0]["quote"]="补充协议另有约定"
            elif kind=="number":
                next(e for e in forged["graph"]["edges"] if e["type"]=="base_contract_ref")["to"]="d03"
            elif kind=="marker":
                del forged["policy"]["quality_addenda"]
            else:
                next(f for f in forged["findings"] if f["rule"]=="H02")["quality_change"]["effective_on"]="2026-08-01"
            with self.assertRaises(ValueError):
                verify_findings(forged) if kind=="evidence" else verify_sources(forged,read)
        old=copy.deepcopy(report)
        old["policy"]={"performance_checks":NATIVE_FORMAT}
        del old["graph"]["quality_addenda"]
        old["findings"]=[{"rule":"H02","status":"ok"}]
        verify_sources(old,read)
        with self.assertRaisesRegex(ValueError,"旧版"):
            verify_sources(old,read,signing=True)
