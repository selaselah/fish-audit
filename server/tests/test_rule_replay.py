from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from rule_replay import RuleMismatch, RulesUnavailable, check_receipt, replay_from_git


class HistoricalRules(unittest.TestCase):
    def setUp(self):
        area=tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.repo=Path(area.name)
        folder=self.repo/"server"
        folder.mkdir()
        self.git("init","-q","-b","main")
        self.git("config","user.name","Synthetic rules")
        self.git("config","user.email","fixture@example.invalid")
        (folder/"controls.py").write_text("""import config, model, graph, policy
VERSION={"version":config.version,"sources":{},"rule_sources":{}}
def execute(g,p):
    return [{"id":"F1","detail":model.value}]
def additional(g,proposals):
    return []
def conclusion(findings):
    return {"verdict":"review","signoff_required":True}
""")
        (folder/"model.py").write_text("from rule_values import value\n")
        (folder/"graph.py").write_text("# Synthetic graph schema\n")
        (folder/"policy.py").write_text("# Synthetic policy\n")
        (folder/"config.py").write_text("version='1'\n")
        self.value=folder/"rule_values.py"
        self.value.write_text("value='first release'\n")
        self.git("add","server")
        self.git("commit","-qm","first release")
        self.first=self.git("rev-parse","HEAD").strip()
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.py")}
        self.report={"case_id":"sample","policy":{"version":"1","sources":{},"rule_sources":{},"profile":"fixture","code_sha256":hashes},
                     "graph":{"profile":"fixture"},"calls":{"expert":{"output":{"followups":[]}}},
                     "findings":[{"id":"F1","detail":"first release"}],"result":{"verdict":"review","signoff_required":True}}
        self.value.write_text("value='second release'\n")
        self.git("commit","-qam","second release")
        self.tip=self.git("rev-parse","HEAD").strip()

    def git(self,*args):
        return subprocess.check_output(["git","-C",str(self.repo),*args],text=True)

    def test_selects_a_single_release_and_covers_transitive_dependencies(self):
        self.value.write_text("value='uncommitted local edit'\n")
        outcome=replay_from_git(self.report,"main",self.repo)
        self.assertEqual((outcome["commit"],outcome["trusted_tip"],outcome["state"]),(self.first,self.tip,"verified"))
        self.assertEqual(outcome["modules"],self.report["policy"]["code_sha256"])
        for name in ("config.py","rule_values.py"):
            changed=deepcopy(self.report)
            changed["policy"]["code_sha256"].pop(name)
            with self.subTest(name=name),self.assertRaises(RulesUnavailable):
                replay_from_git(changed,"main",self.repo)

    def test_actual_disagreements_are_distinct_from_missing_source(self):
        for kind in ("finding","suggestion","json-type"):
            changed=deepcopy(self.report)
            if kind=="finding":
                changed["findings"][0]["detail"]="a different saved finding"
            elif kind=="suggestion":
                changed["result"]["verdict"]="pass"
            else:
                changed["result"]["signoff_required"]=1
            with self.subTest(kind=kind):
                outcome=replay_from_git(changed,self.tip,self.repo)
                self.assertEqual((outcome["state"],outcome["commit"]),("mismatch",self.first))
        with self.assertRaises(RulesUnavailable):
            replay_from_git(self.report,"missing-release",self.repo)

    def test_does_not_assemble_rules_from_different_releases(self):
        config=self.repo/"server"/"config.py"
        config.write_text("version='3'\n")
        self.git("commit","-qam","third release")
        mixed=deepcopy(self.report)
        mixed["policy"]["code_sha256"]["config.py"]=hashlib.sha256(config.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RulesUnavailable,"全部依赖摘要"):
            replay_from_git(mixed,"main",self.repo)

    def test_receipt_binds_case_revision_source_and_computed_result(self):
        outcome=replay_from_git(self.report,"main",self.repo)
        checked=datetime.now(timezone.utc).isoformat()
        checksum="e"*64
        receipt={**outcome,"format":"fish-audit-rule-replay/v1","case_id":"sample","rev":2,"report_sha256":checksum,
                 "checked_at":checked,"rule_version":"1"}
        def verify(record):
            return check_receipt(record,self.report,2,checksum,"2025-01-01T00:00:00+00:00","main",self.repo)
        self.assertEqual(verify(receipt),outcome)
        for field,value in (("case_id","another"),("rev",1),("rev",True),("report_sha256","a"*64),("verdict","pass"),
                            ("findings_sha256","b"*64),("modules",{}),("commit","c"*40),("trusted_tip","c"*40),
                            ("checked_at","2024-01-01T00:00:00+00:00"),("state","unavailable")):
            with self.subTest(field=field),self.assertRaises((RuleMismatch,RulesUnavailable)):
                verify({**receipt,field:value})
