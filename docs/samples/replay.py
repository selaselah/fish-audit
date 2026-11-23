"""Replay the archived, explicitly marked training corpus without calling an external model."""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from calculations import CalculationEvidence
from config import DATA
from controls import conclusion, execute
from run import verify


def replay(database, run_id):
    counts = Counter()
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for index in range(7):
            row = db.execute("""SELECT c.title,r.content FROM cases c JOIN reports r ON r.case_id=c.id AND r.rev=c.rev
                              WHERE c.request_key=?""", (f"{run_id}-{index}",)).fetchone()
            if not row or not row[0].startswith("合成演练 · "):
                raise ValueError(f"未找到指定演练组的第 {index+1} 案")
            saved = json.loads(row[1])
            graph = saved["graph"]
            findings = execute(graph, saved["policy"]["profile"])
            CalculationEvidence(graph).verify(findings)
            findings.extend(f for f in saved["findings"] if f["rule"] == "X01")
            result = conclusion(findings)
            verify(index, {"findings": findings, "result": result, "graph": graph})
            formulas = [c for f in findings for c in f.get("calculations", [])]
            counts.update(cases=1, formulas=len(formulas), operands=sum(len(c["operands"]) for c in formulas))
            print(row[0], result["verdict"], f"{len(formulas)} 条算式")
    print(json.dumps(dict(counts), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DATA / "audit.sqlite3")
    parser.add_argument("--run-id", default="synthetic-procurement-v2")
    args = parser.parse_args()
    replay(args.database, args.run_id)
