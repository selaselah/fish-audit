"""Read-only, time-bounded checks on the local deployment and selected synthetic cases."""

import argparse
import io
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from run import BASE, get, verify as verify_result


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from verify import verify as verify_bundle


EXPECTATIONS = {"档案柜采购": 0, "同号票据与金额差异": 1, "模糊扫描与缺件": 2, "分票结算与跨单汇总": 3,
                "差旅超额与跨期": 4, "同票补件重提": 5, "采购三单合订": 6}


def inspect(case_ids, full, database, record):
    health = get("/api/health")
    if health["status"] != "ok" or not health["audit"]["configured"]:
        raise ValueError("本机服务或审计配置异常")
    record["health"] = True
    routes = ["/", "/app.js", "/style.css"] if full else ["/"]
    for path in routes:
        with urlopen(BASE + path, timeout=10) as response:
            if response.status != 200 or not response.read(1024):
                raise ValueError("页面资源不可用")
    record["web"] = True
    cases = []
    for case_id in case_ids:
        case = get("/api/cases/" + case_id)
        if not case["title"].startswith("合成演练 · "):
            raise ValueError("留观只接受指定演练案例")
        if case["status"] not in ("ready", "closed"):
            raise ValueError("演练任务尚未完成：" + case_id[:10] + " " + case["status"])
        if full:
            prefix = f"/api/cases/{case_id}/reports/{case['rev']}"
            report = get(prefix)["report"]
            expected = EXPECTATIONS.get(case["title"].removeprefix("合成演练 · "))
            if expected is not None:
                verify_result(expected, report)
            elif case["title"] == "合成演练 · 拍照取证与退回补件":
                if case["status"] != "closed" or case["decisions"][-1]["decision"] != "return":
                    raise ValueError("演练原照的退回归档记录不符")
            with urlopen(BASE + prefix + "/bundle", timeout=30) as response:
                verified_id, rev, count = verify_bundle(io.BytesIO(response.read()))
                if verified_id != case_id or rev != case["rev"] or count < 4:
                    raise ValueError("证据包版本不匹配")
                record["bundles"] = record.get("bundles", 0) + 1
        cases.append([case_id[:10], case["rev"], case["status"]])
    if full:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if connection.execute("pragma quick_check").fetchone()[0] != "ok":
                raise ValueError("SQLite 一致性异常")
            if connection.execute("pragma foreign_key_check").fetchone():
                raise ValueError("SQLite 关联一致性异常")
            record["database"] = True
        finally:
            connection.close()
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", required=True, help="ISO 时间，必须含时区")
    parser.add_argument("--case", dest="cases", action="append", required=True,
                        help="指定合成演练的任务编号，可重复使用")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--database", type=Path, default=ROOT / "server" / "data" / "audit.sqlite3")
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.until)
    if deadline.tzinfo is None:
        parser.error("--until 需要带时区")
    zone = ZoneInfo("Asia/Shanghai")
    sample = 0
    errors = 0
    args.log.parent.mkdir(exist_ok=True, parents=True)
    with args.log.open("a", buffering=1) as log:
        while True:
            now = datetime.now(zone)
            final = now >= deadline
            full = sample % 10 == 0 or final
            record = {"time":now.isoformat(timespec="seconds"), "sample":sample, "full":full, "final":final}
            start = time.monotonic()
            try:
                record["cases"] = inspect(args.cases, full, args.database, record)
                record["ok"] = True
            except (OSError, KeyError, ValueError, AssertionError, sqlite3.Error) as error:
                errors += 1
                record.update(ok=False, error=type(error).__name__, message=str(error)[:200])
            record["elapsed_ms"] = round((time.monotonic() - start) * 1000)
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            if not record["ok"] or final:
                print(json.dumps(record, ensure_ascii=False), flush=True)
            if final:
                print(f"完成 {sample+1} 次检查，异常 {errors} 次。", flush=True)
                return 0 if record["ok"] else 1
            sample += 1
            remaining = (deadline - datetime.now(zone)).total_seconds()
            time.sleep(max(0, min(60, remaining)))


if __name__ == "__main__":
    sys.exit(main())
