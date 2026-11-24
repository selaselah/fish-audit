import unittest

from config import TRAVEL
from controls import execute
from graph import build_graph
from invoice_identity import InvoiceIdentities, identity_relations


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
