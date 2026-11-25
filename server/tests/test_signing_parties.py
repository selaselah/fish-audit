import copy
import unittest

from contract_effect import APPROVAL_FORMAT, sources, verify
from controls import VERSION, execute
from graph import link_procedures
from performance import compute, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


BUYER = "青禾演练设备有限公司"
SELLER = "云桥演练冷链有限公司"
FIELD = "甲方印章单位名称"
BRANCH = BUYER + "杭州分公司"


def sample(imprints=(), *, omitted=(), signing=None, checked=True):
    def names(doc, field, label, value):
        if field == "buyer_signature" and signing is not None:
            return signing
        return value.replace("演练甲", BUYER).replace("演练乙", SELLER)

    attestations = {}
    for number in (9, 10):
        ref = f"d01/p1/f{number}"
        receipt = dict(format="field-source-v1", doc="d01", page=1, original_sha256="sample",
                       page_sha256="page", rev=1, operation="confirm", report_hash="a"*64)
        if not checked and number == 9:
            receipt["page_sha256"] = "other page"
        attestations[ref] = dict(fact=ref, decision="confirm", rev=1, source_check=receipt)
    rows = CONTRACT + list(imprints)
    graph = material([rows, RECEIPT, WARRANTY, BANK_DOC], names, omissions=omitted, attestations=attestations)
    return graph


def original_reader(graph, omitted=()):
    def read(doc, page):
        return "\n".join([f["quote"] for f in graph["facts"] if f["doc"] == doc and f["page"] == page] +
                         [line for index, line in omitted if doc == f"d{index:02d}" and page == 1])
    return read


class SigningPartiesTests(unittest.TestCase):
    def test_missed_branch_name_links_its_physical_line_and_holds_only_dependent_checks(self):
        omitted = [(1, FIELD+"："+BRANCH)]
        graph = sample(omitted=omitted)
        found = execute(graph, graph["profile"])
        h01 = next(f for f in found if f["rule"] == "H01")
        record, = h01["effect_review"]["party_seals"]
        self.assertEqual((record["state"], h01["status"]), ("different", "risk"))
        self.assertNotIn("已有材料支持", h01["detail"])
        line, = [r for r in graph["contract_effect_sources"]["signing_rows"] if r["role"] == "imprint"]
        self.assertEqual((line["line"], line["quote"], line["facts"]), (len(CONTRACT)+1, omitted[0][1], []))
        self.assertEqual(record["comparison"][1], line["id"])
        self.assertLessEqual({line["id"], "d01/p1"}, set(h01["evidence"]))
        self.assertEqual([f["status"] for f in found if f["rule"] in ("H02","H03","H04","H05")],
                         ["ok","ok","missing","missing","missing","missing"])
        link_procedures(graph, found, {"expert":{"model":"fixture"}, "pages":[]})
        report = {"graph":graph,"findings":found,"policy":{**VERSION,"profile":graph["profile"]}}
        read = original_reader(graph, omitted)
        verify(report, read)
        verify_findings(report)
        for corrupt in ("ledger", "row", "edge", "findings", "native"):
            changed = copy.deepcopy(report)
            g = changed["graph"]
            if corrupt == "ledger":
                g["contract_effect_sources"]["signing_rows"][-1]["unit"] = "d02"
            if corrupt == "row":
                next(n for n in g["nodes"] if n["id"] == line["id"])["label"] = FIELD+"："+BUYER
            if corrupt == "edge":
                next(e for e in g["edges"] if e["type"] == "contract_seal_name_comparison")["to"] = "d02/p1"
            if corrupt == "findings":
                next(f for f in changed["findings"] if f["rule"] == "H01")["effect_review"]["party_seals"][0]["state"] = "match"
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                if corrupt == "findings":
                    verify_findings(changed)
                else:
                    verify(changed, (lambda d,p: read(d,p).replace(BRANCH, BUYER)) if corrupt == "native" else read)

    def test_only_complete_names_and_a_bound_signing_receipt_can_match(self):
        aligned = ("buyer_seal_name",FIELD,BUYER)
        other = ("seller_seal_name","乙方印章单位名称",SELLER)
        cases = [
            ([aligned,other], {}, [("buyer","match","ok"),("seller","match","ok")]),
            ([aligned], {"checked":False}, [("buyer","signature","missing")]),
            ([("buyer_seal_name",FIELD,"青禾演练＊＊有限公司")], {}, [("buyer","partial","missing")]),
            ([("buyer_seal_name",FIELD,BUYER.replace("设备","设 备"))], {}, [("buyer","partial","missing")]),
            ([aligned,("buyer_seal_name",FIELD,BRANCH)], {}, [("buyer","multiple","missing")]),
            ([], {"omitted":[(1,"印章单位名称："+BUYER)]}, [("unspecified","side","missing")]),
            ([], {"signing":BRANCH+"（已盖章）"}, [("buyer","different","risk")]),
            ([], {"signing":BRANCH+"（已盖章）","checked":False}, [("buyer","signature","missing")]),
            ([], {"signing":"陈演练（已签字）"}, []),
            ([], {"omitted":[(2,FIELD+"："+BRANCH)]}, []),
        ]
        for imprints, options, expected in cases:
            with self.subTest(expected=expected, options=options):
                finding = compute(sample(imprints, **options))[0]
                results = finding["effect_review"].get("party_seals", [])
                self.assertEqual([(r["side"],r["state"],r["status"]) for r in results], expected)
                self.assertTrue(all(bool(r["comparison"]) == (r["status"] in ("ok","risk")) for r in results))
                if expected and expected[0][2] != "ok":
                    self.assertNotEqual(finding["status"], "ok")

    def test_old_fixed_version_replays_but_approval_rechecks_the_same_contract(self):
        omitted = []
        graph = sample([("buyer_sealed_on", FIELD, BRANCH)])
        read = original_reader(graph, omitted)
        graph["contract_effect_sources"] = sources(graph, read, APPROVAL_FORMAT)
        old = {"graph":graph,"findings":compute(graph),
               "policy":{**VERSION,"version":"2026.11.26.01","contract_effect":APPROVAL_FORMAT}}
        self.assertEqual(old["findings"][0]["status"], "ok")
        verify(old, read)
        with self.assertRaisesRegex(ValueError, "签章主体"):
            verify(old, read, signing=True)
