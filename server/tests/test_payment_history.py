from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from PIL import Image

from calculations import FORMAT
from config import BANK, CaseError
from controls import VERSION, conclusion, execute
from evidence import export_bundle
from graph import build_graph, link_procedures
from identity import Directory
from jobs import CODE_DIGESTS, METHODS
from payment_history import LIMIT
from policy import link_sources
from storage import Store, encode
from test_transfers import receipt_material
from verify import replay_rules, sha, verify, verify_payment_history


class PaymentHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = Store(self.root)

    def workpaper(self, case_id, *, fresh=True, history=True, workspace="local", user=None, **fields):
        docs, pages = receipt_material(**fields)
        for doc, page in zip(docs, pages):
            # The controlled extractor supplies the text layer. The bundle still carries real image bytes.
            photo = io.BytesIO()
            Image.new("RGB", (24, 20), color=(12, 34, int(doc["id"][1:]))).save(photo, format="JPEG")
            data = photo.getvalue()
            doc.update(ext=".jpg", size=len(data), sha256=sha(data))
            page.update(sha256=sha(data), width=24, height=20)
            path = self.store.files / case_id / doc["id"]
            path.mkdir(parents=True, exist_ok=True)
            (path / "original.jpg").write_bytes(data)
            (path / "1.jpg").write_bytes(data)
        if fresh:
            self.store.create(case_id, "演练 "+case_id, docs, case_id, case_id, BANK, workspace, user)
            for doc, page in zip(docs, pages):
                self.store.put_pages(case_id, doc["id"], [page])
        graph = build_graph(docs, pages, {})
        graph["profile"] = BANK
        lookup = (lambda signature: self.store.payment_history(case_id, signature)) if history else None
        findings = execute(graph, BANK, lookup)
        calls = {"expert": {"model": "fixture", "output": {"followups": []}}, "pages": [
            {"model":"fixture", "doc":p["doc"], "page":1, "page_sha256":p["sha256"]} for p in pages]}
        link_procedures(graph, findings, calls)
        link_sources(graph)
        policy = {**VERSION, "profile": BANK, "code_sha256": CODE_DIGESTS, "calculations": FORMAT, "archived_methods": True}
        report = {"case_id": case_id, "graph": graph, "findings": findings, "result": conclusion(findings), "policy": policy, "calls": calls}
        self.store.save_report(case_id, report, sha(encode(report).encode()), METHODS)
        return report

    def sign(self, case, decision="approve"):
        self.store.review(case, 1, "演练验收", "合成底稿回归", decision)

    def assert_controls(self, report, same, full):
        self.assertEqual({f["rule"]: f["status"] for f in report["findings"] if f["rule"] in {"B06", "B07"}},
                         {"B06": same, "B07": full})

    def test_scope_decisions_and_legacy_backfill(self):
        legacy = self.workpaper("archived", history=False)
        self.sign("archived")
        self.workpaper("returned")
        self.sign("returned", "return")
        self.workpaper("pending")
        with self.store.connect(True) as db:
            db.execute("DROP TABLE payment_index")
            db.execute("PRAGMA user_version=2")
        self.store = Store(self.root)
        self.assertEqual(legacy, self.store.report("archived", 1)["report"])
        same = self.workpaper("copy")
        self.assert_controls(same, "risk", "ok")
        matches = same["graph"]["payment_history"]["matches"]
        self.assertEqual({(m["case_id"], m["decision"]) for m in matches}, {("archived", "approve"), ("returned", "return")})
        self.assertTrue(all({f["field"] for f in m["evidence"]} == {"transfer_ref", "payer"} for m in matches))
        full = self.workpaper("another", transfer_ref="YL-081-B")
        self.assert_controls(full, "ok", "risk")
        self.assertEqual([m["case_id"] for m in full["graph"]["payment_history"]["matches"]], ["archived"])
        directory = Directory(self.store)
        session, workspace = directory.register({"login":"fixture-other", "name":"演练", "password":"synthetic-password-42", "workspace":"乙企业"})
        unrelated = self.workpaper("other", workspace=workspace, user=directory.user(session))
        self.assert_controls(unrelated, "ok", "ok")
        with self.store.connect() as db, self.assertRaises(CaseError):
            self.store.signed_source(db, "other", "archived", 1)

    def test_currency_amount_names_dates_and_masked_references(self):
        self.workpaper("base", transfer_ref="00001234")
        self.sign("base")
        for i, (fields, expected) in enumerate([
                ({"transfer_ref":"1234"}, ("ok","risk")),
                ({"transfer_ref":"XXXX1234"}, ("missing","missing")),
                ({"transfer_ref":None}, ("missing","missing")),
                ({"transfer_ref":"00001234","currency":"美元"}, ("risk","missing")),
                ({"transfer_ref":"OTHER","transfer_status":"已受理"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","payment_term":"分期结算"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","total":"0.00","transfer_amount":"0"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","payee_account":"********0081"}, ("ok","missing")),
                ({"transfer_ref":"OTHER","total":"9,000","transfer_amount":"9,000"}, ("ok","ok")),
                ({"transfer_ref":"00001234","payer":"演练丙","buyer":"演练丙"}, ("ok","ok")),
                ({"transfer_ref":"OTHER","paid_on":"2026-10-01"}, ("ok","missing"))]):
            with self.subTest(fields=fields):
                self.assert_controls(self.workpaper("probe"+str(i), **fields), *expected)
        self.workpaper("case-sensitive", contract_id="YL-lower", transfer_ref="lower-A")
        self.sign("case-sensitive")
        self.assert_controls(self.workpaper("upper", contract_id="YL-lower", transfer_ref="LOWER-A"), "ok", "risk")

    def test_concurrent_approvals_require_new_review_and_frozen_replay(self):
        cases = ["batch-A", "batch-B"]
        initial = [self.workpaper(cid, transfer_ref=cid) for cid in cases]
        barrier = threading.Barrier(2)
        def decide(cid):
            barrier.wait(timeout=5)
            try:
                self.sign(cid)
                return "approved"
            except CaseError as error:
                self.assertEqual(error.status, 409)
                return "stale"
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(decide, cases))
        self.assertCountEqual(decisions, ["approved", "stale"])
        index = decisions.index("stale")
        cid = cases[index]
        self.assertEqual(self.store.detail(cid)["status"], "ready")
        self.store.rerun(cid, 1)
        revised = self.workpaper(cid, fresh=False, transfer_ref=cid)
        self.assert_controls(revised, "ok", "risk")
        self.assert_controls(initial[index], "ok", "ok")
        replay_rules(self.store.report(cid, 1)["report"])
        replay_rules(revised)
        self.store.review(cid, 2, "演练验收", "已核对两笔流水，升级复核", "escalate")

    def test_bundle_links_originals_signoffs_and_exact_citations(self):
        self.workpaper("base")
        self.sign("base")
        report = self.workpaper("second", transfer_ref="YL-081-B")
        stream = io.BytesIO()
        export_bundle(self.store, "second", 1, stream)
        self.assertEqual(verify(stream, True)[:2], ("second", 1))
        with zipfile.ZipFile(stream) as bundle:
            hashes = {r["path"]: r["sha256"] for r in json.loads(bundle.read("manifest.json"))["files"]}
            self.assertIn("prior/base/r1/originals/d02.jpg", hashes)
            journal = json.loads(bundle.read("journal.json"))
            for field, value in (("decision", "return"), ("title", "被替换的底稿"), ("signed_at", "2000-01-01T00:00:00+00:00")):
                modified = deepcopy(report)
                modified["graph"]["payment_history"]["matches"][0][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    verify_payment_history(bundle, hashes, modified, journal)
            modified = deepcopy(report)
            modified["graph"]["payment_history"]["matches"][0]["evidence"][0]["quote"] += "虚构"
            with self.assertRaisesRegex(ValueError, "逐字引文"):
                verify_payment_history(bundle, hashes, modified, journal)

    def test_bounded_lookup_keeps_exact_count(self):
        for i in range(LIMIT+2):
            cid = "returned-"+str(i)
            self.workpaper(cid)
            self.sign(cid, "return")
        current = self.workpaper("copy")
        history = current["graph"]["payment_history"]
        self.assertEqual(history["counts"], {"same": LIMIT+2, "full": 0})
        self.assertEqual(len(history["matches"]), LIMIT)
        self.assertTrue(any("列示最近签收" in f["detail"] for f in current["findings"]))

    def test_invalid_index_cannot_create_a_finding_against_unrelated_originals(self):
        self.workpaper("base", transfer_ref="YL-AAA")
        self.sign("base")
        with self.store.connect(True) as db:
            db.execute("UPDATE payment_index SET reference='YL-BBB' WHERE case_id='base'")
        with self.assertRaisesRegex(CaseError, "与已签收底稿中的原文不一致"):
            self.workpaper("new", transfer_ref="YL-BBB")
