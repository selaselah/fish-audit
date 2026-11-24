import unittest

from config import TRAVEL
from controls import execute
from graph import attach_prior_invoices, build_graph
from invoice_approval import receipt
from invoice_identity import InvoiceIdentities, identity_relations
from invoice_masks import verify_masks


CODES = ("099926001011","099926002011")
NUMBER = "00001234"


def materials(codes=CODES, *, numbers=None, claim=None, packet=False):
    numbers = numbers or [NUMBER]*len(codes)
    claim = claim if claim is not None else [("claim_full_ref",c+" / "+n) for c,n in zip(codes,numbers) if c]
    labels = {"claim_full_ref":"随附发票代码及号码","claim_ref":"随附发票号码","invoice_code":"发票代码","invoice_id":"发票号码",
              "total":"价税合计","claim_total":"申请报销金额","currency":"币种","unit":"金额单位","traveler":"出差人员",
              "trip_start":"出差开始日期","trip_end":"出差结束日期","service_on":"费用发生日期"}
    money = [("currency","人民币"),("unit","元"),("traveler","演练甲")]
    groups = [[("claim","差旅报销单"),("claim_total",str(100*len(codes))),("trip_start","2026-10-01"),("trip_end","2026-10-03"),*claim,*money]]
    for c,n in zip(codes,numbers):
        fields = [("invoice","住宿服务发票"),("invoice_id",n),("total","100"),("service_on","2026-10-02"),*money]
        if c:
            fields.append(("invoice_code",c))
        groups.append(fields)
    docs,pages=[],[]
    for i,fields in enumerate(groups,1):
        doc = "d02" if packet and i>1 else f"d{i:02d}"
        page = i-1 if packet and i>1 else 1
        if page==1:
            docs.append({"id":doc,"name":doc+".pdf","sha256":doc})
        facts=[{"field":k,"value":v,"quote":labels[k]+"："+v if k in labels else v,"region":"top"} for k,v in fields]
        pages.append({"doc":doc,"number":page,"sha256":doc+str(page),"text":"\n".join(f["quote"] for f in facts),
                      "layer":{"type":"text","lines":{str(i+1):[[.1,.2,.8,.23]] for i in range(len(facts))}},
                      "extraction":{"output":{"quality":"readable","facts":facts}}})
    return docs,pages


class InvoiceIdentityTests(unittest.TestCase):
    def test_repeating_visible_masks_does_not_establish_an_invoice_or_a_total(self):
        for value in ("26****1234","26＊＊90","00XXXX1234","尾号1234","26…1234","□□□□","XXXX"):
            with self.subTest(value=value):
                g=build_graph(*materials([None],numbers=[value],claim=[("claim_ref",value)]),{})
                attach_prior_invoices(g,[])
                verify_masks(g)
                f={r["rule"]:r for r in execute(g,TRAVEL)}
                self.assertTrue(all(f[rule]["status"]=="missing" for rule in ("I01","I02","T02","T03")))
                self.assertNotIn("calculations",f["T03"])
                refs={m["fact"] for m in g["number_masks"]["facts"]}
                self.assertEqual(len(refs),2)
                self.assertTrue(refs<=set(f["T03"]["evidence"]))
                self.assertFalse(any(n["type"]=="invoice_number" for n in g["nodes"]))
                signed={"case_id":"test","workspace":"local","rev":1,"time":"t"}
                checked=receipt(g,[],1,"r",signed)
                self.assertEqual((checked["outcome"],checked["numbers"],checked["withheld"][0]["value"]),("incomplete_number",[],value))
                next(e for e in g["edges"] if e["type"]=="incomplete_invoice_id")["type"]="invoice_id"
                with self.assertRaisesRegex(ValueError,"精确匹配"):
                    verify_masks(g)

    def test_extra_masked_claim_blocks_summing_otherwise_matching_invoice(self):
        valid="YL-XX-1234"
        g=build_graph(*materials([None],numbers=[valid],claim=[("claim_ref",valid),("claim_ref","26****1234")]),{})
        attach_prior_invoices(g,[])
        checks={r["rule"]:r for r in execute(g,TRAVEL)}
        self.assertEqual([checks[r]["status"] for r in ("I01","I02","T02","T03")],["ok","ok","missing","missing"])
        self.assertNotIn("calculations",checks["T03"])
        docs,pages=materials([None],numbers=[valid],claim=[("claim_ref",valid)])
        page=pages[1]
        value="26****1234"
        item={"field":"invoice_id","value":value,"quote":"发票号码："+value,"region":"top"}
        page["extraction"]["output"]["facts"].append(item)
        page["text"]+="\n"+item["quote"]
        page["layer"]["lines"][str(len(page["text"].splitlines()))]=[[.1,.2,.9,.23]]
        g=build_graph(docs,pages,{})
        self.assertFalse(any(e["type"]=="invoice_id" for e in g["edges"]))
        verify_masks(g)

    def test_model_classification_requires_the_same_printed_line_and_checked_image(self):
        docs,pages=materials()
        page=pages[0]
        facts=page["extraction"]["output"]["facts"]
        candidates=[]
        for n,fact in enumerate(facts,1):
            if fact["field"]=="claim_full_ref":
                fact["field"]="claim_ref"
                candidates.append({"index":str(n),"field":"随附发票号码","value":fact["value"],"quote":fact["quote"]})
        votes=[{"index":c["index"],"support":"clear"} for c in candidates]
        page["extraction"]["check"]={"input":candidates,"output":{"checks":votes}}
        g=build_graph(docs,pages,{})
        mapped=[f for f in g["facts"] if f["field"]=="claim_full_ref"]
        self.assertEqual(len(mapped),2)
        self.assertTrue(all(f["model_field"]=="claim_ref" and f["origin"]=="printed_claim_pair" for f in mapped))
        self.assertEqual(next(f for f in execute(g,TRAVEL) if f["rule"]=="T03")["status"],"ok")
        self.assertTrue(all(facts[int(c["index"])-1]["field"]=="claim_ref" for c in candidates))
        votes[0]["support"]="conflict"
        candidates[1]["quote"]="另处号码"
        g=build_graph(docs,pages,{})
        self.assertFalse(any(f["field"]=="claim_full_ref" for f in g["facts"]))
        self.assertEqual(next(f for f in execute(g,TRAVEL) if f["rule"]=="T03")["status"],"missing")

    def test_different_codes_allow_an_explicitly_itemized_claim_and_split_invoice_pages(self):
        for packet in (False,True):
            g=build_graph(*materials(packet=packet),{})
            findings=execute(g,TRAVEL)
            checked={f["rule"]:f for f in findings}
            self.assertEqual([checked[r]["status"] for r in ("I01","T02","T03")],["ok"]*3)
            self.assertEqual(len(g["documents_by_kind"]["invoice"]),2)
            nodes,relations=identity_relations(g)
            self.assertEqual({n["label"] for n in nodes},{c+" / "+NUMBER for c in CODES})
            self.assertTrue(all(set(e["evidence"])<=set(checked["T03"]["evidence"]) for e in relations))
            self.assertEqual(checked["T03"]["calculations"][-1]["result"],"0.00")

    def test_same_pair_missing_code_conflicting_code_and_bare_claim(self):
        for codes,claim,i01 in [((CODES[0],CODES[0]),None,"risk"),((CODES[0],None),None,"missing"),
                                (CODES,[("claim_ref",NUMBER)],"ok"),(CODES,[("claim_full_ref","999 / "+NUMBER)],"ok")]:
            with self.subTest(codes=codes,claim=claim):
                g=build_graph(*materials(codes,claim=claim),{})
                f={row["rule"]:row for row in execute(g,TRAVEL)}
                self.assertEqual((f["I01"]["status"],f["T02"]["status"],f["T03"]["status"]),(i01,"missing","missing"))
                self.assertNotIn("calculations",f["T03"])
        g=build_graph(*materials(),{})
        code=next(f for f in g["facts"] if f["field"]=="invoice_code")
        number=next(f for f in g["facts"] if f["field"]=="invoice_id")
        g["facts"].append({**code,"id":"second-code","value":CODES[1]})
        self.assertEqual(InvoiceIdentities(g).describe(number)["kind"],"short_unresolved")
        g["facts"].pop()
        code["status"]="disputed"
        self.assertEqual(InvoiceIdentities(g).describe(number)["kind"],"short_unresolved")
        code["status"]="confirmed"
        code["page"]=2
        self.assertEqual(InvoiceIdentities(g).describe(number)["kind"],"short_unresolved")

    def test_twenty_digit_numbers_with_the_same_suffix_are_independent(self):
        values=["26999900000000001234","26999800000000001234"]
        g=build_graph(*materials([None,None],numbers=values,claim=[("claim_ref",v) for v in values]),{})
        self.assertEqual([n["kind"] for n in identity_relations(g)[0]],["twenty_digit","twenty_digit"])
        checked=[f for f in execute(g,TRAVEL) if f["rule"] in {"I01","T02","T03"}]
        self.assertTrue(all(f["status"]=="ok" for f in checked))
