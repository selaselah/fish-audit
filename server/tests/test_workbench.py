import tempfile
import unittest
from pathlib import Path

from storage import Store
from workbench import inbox, project, search_evidence


class SearchProjection(unittest.TestCase):
    def test_literal_queries_paging_and_replaced_revisions(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder))
            for i in range(15):
                store.create(str(i), f"采购 {i}", [], f"key-{i}", f"digest-{i}")
            result = {"verdict":"pass","counts":{"risk":0,"issue":0,"missing":0}}
            fact = {"id":"d01/p1/f1","doc":"d01","page":1,"name":"合同.pdf","field":"subject","label":"采购标的",
                    "value":"一号档案柜","quote":"采购标的：一号档案柜","status":"anchored"}
            def save(rev, fact):
                with store.connect(True) as db:
                    db.execute("UPDATE cases SET rev=? WHERE id='1'", (rev,))
                    project(db,"1",rev,{"result":result,"graph":{"facts":[fact]}})
            save(1,fact)
            for indexed in (store.fts_enabled, False):
                store.fts_enabled = indexed
                for query in ("柜","档案","档案柜","档案 标的","一号档案柜"):
                    self.assertEqual(search_evidence(store,"local",{"q":query})["total"],1)
                self.assertEqual(search_evidence(store,"local",{"q":'%"'})["total"],0)
            page = inbox(store,"local",None,{"page":"2"})
            self.assertEqual((page["pages"],page["total"],len(page["cases"])),(2,15,3))
            self.assertEqual(inbox(store,"local",None,{"q":"采购 14"})["total"],1)
            save(2,dict(fact,value="档案盒",quote="采购标的：档案盒",status="visual"))
            self.assertEqual(search_evidence(store,"local",{"q":"档案柜","status":"all"})["total"],0)
            self.assertEqual(search_evidence(store,"local",{"q":"档案盒"})["total"],0)
            self.assertEqual(search_evidence(store,"local",{"q":"档案盒","status":"pending"})["hits"][0]["rev"],2)
