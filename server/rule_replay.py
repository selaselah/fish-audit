"""Replay a saved graph using byte-matched rule modules from a trusted checkout or its Git history."""

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CORE_MODULES = {"controls.py","config.py","model.py","graph.py","policy.py"}


class RulesUnavailable(ValueError):
    pass


class RuleMismatch(ValueError):
    pass


def result_bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def compare_rules(report, engine):
    policy = report["policy"]
    if any(policy.get(k) != engine.VERSION.get(k) for k in ("version","sources","rule_sources","invoice_sources","invoice_approval","invoice_identity","invoice_lookup","invoice_number_masks","performance_checks","quality_number_classification","quality_references","delegation_checks","quality_addenda","acceptance_authority","delivery_batches","contract_effect","warranty_checks")):
        raise RuleMismatch("制度与执行程序目录和当时的规则版本不符。")
    if report["graph"].get("profile") != policy["profile"]:
        raise RuleMismatch("底稿与规则的业务范围不符。")
    findings = engine.execute(report["graph"],policy["profile"])
    followups = report["calls"]["expert"]["output"]["followups"]
    findings += engine.additional(report["graph"],[p for p in followups if p["procedure"]!="no_trigger"])
    saved = report["findings"]
    if len(findings) != len(saved):
        raise RuleMismatch(f"复算得到 {len(findings)} 项发现，底稿记载 {len(saved)} 项。")
    for actual,expected in zip(findings,saved):
        if result_bytes(actual) != result_bytes(expected):
            raise RuleMismatch(f"发现 {expected['id']} 的内容与规则复算不符。")
    decision = engine.conclusion(findings)
    if result_bytes(decision) != result_bytes(report["result"]):
        raise RuleMismatch("复算的整案建议或状态计数与底稿不符。")
    return {"finding_count":len(findings),"verdict":decision["verdict"],
            "findings_sha256":hashlib.sha256(result_bytes(findings)).hexdigest(),
            "result_sha256":hashlib.sha256(result_bytes(decision)).hexdigest()}


def git(repo, *args):
    env = {"PATH":os.environ.get("PATH",os.defpath),"GIT_TERMINAL_PROMPT":"0","GIT_NO_REPLACE_OBJECTS":"1",
           "GIT_NO_LAZY_FETCH":"1","GIT_OPTIONAL_LOCKS":"0"}
    cmd = ["git","-C",str(repo),*args]
    try:
        return subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=15).stdout
    except (OSError,subprocess.SubprocessError) as exc:
        raise RulesUnavailable("本地版本库或指定的可信提交不可读。") from exc


@lru_cache(maxsize=16)
def history(repo, tip):
    # Include merge results on the chosen release line. A checkout or a fetch is unnecessary.
    return git(repo,"rev-list","--first-parent",tip,"--","server").decode("ascii").splitlines()


@lru_cache(maxsize=150)
def tree(repo, commit):
    listing = git(repo,"ls-tree","-z",commit,"--","server/")
    modules = {}
    for row in listing.split(b"\0"):
        if not row:
            continue
        metadata,filename = row.split(b"\t",1)
        filename = filename.removeprefix(b"server/")
        mode,kind,oid = metadata.split()
        if kind==b"blob" and mode in {b"100644",b"100755"} and re.fullmatch(rb"[A-Za-z_]\w*\.py",filename):
            modules[filename.decode("ascii")] = oid.decode("ascii")
    return modules


@lru_cache(maxsize=400)
def blob(repo, oid):
    data = git(repo,"cat-file","blob",oid)
    return data,hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=400)
def module_imports(source):
    imports = set()
    try:
        syntax = ast.parse(source)
    except (SyntaxError,ValueError) as exc:
        raise RulesUnavailable("本机 Python 无法解析匹配到的规则源码。") from exc
    for node in ast.walk(syntax):
        if isinstance(node,ast.Import):
            imports.update(alias.name.split(".",1)[0]+".py" for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module:
            imports.add(node.module.split(".",1)[0]+".py")
    return imports


def matching_modules(available, hashes, read, roots):
    # A recorded import that disappeared from this release must still be accounted for.
    candidates = available.keys() | hashes.keys()
    pending,matched = list(roots),{}
    while pending:
        name = pending.pop()
        if name in matched:
            continue
        if name not in available:
            return None,name
        source,checksum = read(available[name])
        if hashes.get(name) != checksum:
            return None,name
        matched[name] = source,checksum
        pending.extend(sorted(module_imports(source) & candidates))
    return matched,None


def recorded_hashes(report):
    hashes = report["policy"].get("code_sha256",{})
    if not isinstance(hashes,dict) or not CORE_MODULES.issubset(hashes):
        raise RulesUnavailable("这版底稿保存的规则源码摘要不完整，无法确认当时使用的程序。")
    return hashes


def trusted_engine(report, ref, repo, pinned=None, issued_tip=None):
    hashes = recorded_hashes(report)
    tip = git(repo,"rev-parse","--verify","--end-of-options",ref+"^{commit}").decode("ascii").strip()
    if issued_tip is not None:
        if not isinstance(issued_tip,str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})",issued_tip):
            raise RulesUnavailable("复算记录中的发布版本无效。")
        ancestors = git(repo,"rev-list","--first-parent",tip).decode("ascii").splitlines()
        if issued_tip not in ancestors:
            raise RulesUnavailable("记录所据的发布版本不在本机信任的发布历史中。")
        tip = issued_tip
    commits = history(repo,tip)
    if pinned is not None:
        if not isinstance(pinned,str) or pinned not in commits:
            raise RulesUnavailable("复算记录所列提交不在指定的本地发布历史中。")
        commits = [pinned]
    for commit in commits:
        modules,_ = matching_modules(tree(repo,commit),hashes,lambda oid: blob(repo,oid),["controls.py"])
        if modules:
            return tip,commit,modules
    raise RulesUnavailable("在指定的本地发布历史中没有找到全部依赖摘要相符的规则版本。")


def run_matching_sources(report, modules):
    with tempfile.TemporaryDirectory(prefix="fish-rule-replay-") as folder:
        directory = Path(folder)
        for name,(data,_) in modules.items():
            (directory/name).write_bytes(data)
        cmd = [sys.executable,"-I","-B",str(Path(__file__).resolve()),str(directory)]
        # The isolated process sees just the selected source modules and the saved report on stdin.
        try:
            output = subprocess.run(cmd,cwd=directory,env={"PATH":os.defpath},input=json.dumps(report,ensure_ascii=False).encode(),
                                    capture_output=True,check=True,timeout=30)
            outcome = json.loads(output.stdout)
        except (OSError,subprocess.SubprocessError,ValueError) as exc:
            raise RulesUnavailable("本机未能运行所选规则。请使用项目的 Python 环境检查依赖。") from exc
    if outcome["state"]=="unavailable":
        raise RulesUnavailable(outcome["message"])
    return {**outcome,"modules":{name:checksum for name,(_,checksum) in sorted(modules.items())}}


def replay_from_git(report, ref="HEAD", repo=ROOT, *, pinned=None, issued_tip=None):
    repo = Path(repo).resolve()
    tip,commit,modules = trusted_engine(report,ref,repo,pinned,issued_tip)
    return {**run_matching_sources(report,modules),"commit":commit,"trusted_tip":tip}


def replay_installed(report, folder=ROOT/"server"):
    hashes = recorded_hashes(report)
    def read(path):
        if path.is_symlink() or not path.is_file():
            raise RulesUnavailable("本机规则源码须为普通文件："+path.name)
        source = path.read_bytes()
        return source,hashlib.sha256(source).hexdigest()
    available = {path.name:path for path in Path(folder).glob("*.py") if re.fullmatch(r"[A-Za-z_]\w*\.py",path.name)}
    roots = sorted(CORE_MODULES)
    if "supplement" in report:
        roots.append("supplements.py")
    modules,unmatched = matching_modules(available,hashes,read,roots)
    if unmatched:
        raise RulesUnavailable("严格复算需要与底稿一致的本机规则版本："+unmatched)
    return run_matching_sources(report,modules)


def check_receipt(receipt, report, revision, report_hash, created, ref, repo=ROOT):
    expected = {"format":"fish-audit-rule-replay/v1","state":"verified","case_id":report["case_id"],"rev":revision,
                "report_sha256":report_hash,"rule_version":report["policy"]["version"]}
    if any(result_bytes(receipt.get(k))!=result_bytes(v) for k,v in expected.items()):
        raise RuleMismatch("复算记录不属于该证据包版本，或未记录复算一致。")
    checked_at = datetime.fromisoformat(receipt["checked_at"])
    if checked_at.tzinfo is None or checked_at<datetime.fromisoformat(created):
        raise RuleMismatch("复算记录的时间早于所引底稿或缺少时区。")
    outcome = replay_from_git(report,ref,repo,pinned=receipt["commit"],issued_tip=receipt["trusted_tip"])
    if outcome["state"]!="verified" or any(result_bytes(receipt.get(k))!=result_bytes(v) for k,v in outcome.items()):
        raise RuleMismatch("记录中的提交、规则依赖、发现摘要或整案建议与独立复算不符。")
    return outcome


if __name__ == "__main__":
    sys.path.insert(0,sys.argv[1])
    try:
        import controls
        result = {"state":"verified",**compare_rules(json.load(sys.stdin),controls)}
    except (RuleMismatch,KeyError,ValueError,TypeError,IndexError,ArithmeticError) as error:
        message = str(error) if isinstance(error,RuleMismatch) else "归档数据无法按照所选版本的规则复算。"
        result = {"state":"mismatch","message":message}
    except ImportError:
        result = {"state":"unavailable","message":"复算环境缺少所选规则的 Python 依赖，请使用项目的虚拟环境。"}
    print(json.dumps(result,ensure_ascii=True))
