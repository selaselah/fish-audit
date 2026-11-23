import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path

from calculations import CalculationEvidence, FORMAT
from protocol import canonical, response_request


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_request(trace, instructions, page_image=None):
    if "request_format" not in trace:
        return
    require(trace["request_format"] == "responses-json-v1", "未知的模型请求格式")
    prompt = instructions.get(trace["prompt_sha256"])
    require(prompt and sha(prompt.encode()) == trace["prompt_sha256"], "无法还原模型指令")
    content = []
    if page_image is not None:
        image = base64.b64encode(page_image).decode("ascii")
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + image, "detail": "high"})
    if "input" in trace:
        content.append({"type": "input_text", "text": canonical(trace["input"])})
    body = response_request(trace["requested_model"], prompt, content, trace["schema"], trace["schema_name"], trace["max_output_tokens"])
    require(sha(body) == trace["request_sha256"], "模型请求与归档的输入、指令或输出约束不符")


def verify(source):
    with zipfile.ZipFile(source) as bundle:
        names = bundle.namelist()
        require(len(names) == len(set(names)), "包内出现同名文件")
        manifest = json.loads(bundle.read("manifest.json"))
        entries = manifest["files"]
        expected = {item["path"] for item in entries}
        require(len(entries) == len(expected) and set(names) == expected | {"manifest.json"}, "文件目录不匹配")
        for item in entries:
            with bundle.open(item["path"]) as stream:
                hasher = hashlib.sha256()
                size = 0
                while chunk := stream.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
            require(size == item["bytes"] and hasher.hexdigest() == item["sha256"], "文件校验失败：" + item["path"])
        hashes = {item["path"]: item["sha256"] for item in entries}
        report = json.loads(bundle.read("report.json"))
        journal = json.loads(bundle.read("journal.json"))
        case_id, revision = manifest["case_id"], manifest["revision"]
        require(case_id == report["case_id"] == journal["id"], "底稿归属不一致")
        require(hashes["report.json"] == manifest["report_sha256"] and any(
            item["rev"] == revision and item["hash"] == hashes["report.json"] for item in journal["revisions"]), "底稿版本摘要不符")
        graph = report["graph"]
        if report["policy"].get("archived_methods"):
            for name, expected in report["policy"]["code_sha256"].items():
                require(hashes.get("methods/" + name) == expected, "执行程序版本不符：" + name)
        nodes = {node["id"]: node for node in graph["nodes"]}
        require(len(nodes) == len(graph["nodes"]), "图节点重复")
        for doc in graph["documents"]:
            require(hashes["originals/" + doc["id"] + doc["ext"]] == doc["sha256"] == nodes[doc["id"]]["sha256"], "原件摘要不符")
        for trace in report["calls"]["pages"]:
            doc, page = trace["doc"], trace["page"]
            page_node = nodes[f"{doc}/p{page}"]
            require(hashes[f"pages/{doc}/{page}.jpg"] == trace["page_sha256"] == page_node["sha256"], "页图摘要不符")
            if "text_sha256" in page_node:
                require(hashes[f"pages/{doc}/{page}.txt"] == page_node["text_sha256"], "文字层摘要不符")
            calls = [trace, *([trace["check"]] if trace.get("check") else [])]
            if any(call.get("request_format") for call in calls):
                photo = bundle.read(f"pages/{doc}/{page}.jpg")
                for call in calls:
                    verify_request(call, report["calls"].get("instructions", {}), photo)
        verify_request(report["calls"]["expert"], report["calls"].get("instructions", {}))
        for match in graph.get("prior_invoices", []):
            path = f"prior/{match['case_id']}/r{match['rev']}/{match['doc']}/{match['page']}.jpg"
            require(hashes[path] == match["page_hash"] and match["id"] in nodes, "历史票号证据不符")
        page_checks = {(t["doc"],t["page"]): t.get("check") for t in report["calls"]["pages"]}
        texts = {}
        for fact in graph["facts"]:
            require(fact["source_sha256"] == nodes[fact["doc"]]["sha256"] and
                    fact["page_sha256"] == nodes[f"{fact['doc']}/p{fact['page']}"]["sha256"], "取值与来源不符")
            if fact.get("origin") == "verified_printed_heading":
                check = page_checks.get((fact["doc"],fact["page"])) or {}
                key = fact["id"].rsplit("/", 1)[-1]
                candidate = fact.get("original_candidate") or fact
                inputs = [row for row in check.get("input", []) if row["index"] == key]
                votes = [row["support"] for row in check.get("output", {}).get("checks", []) if row["index"] == key]
                require(len(inputs) == 1 and inputs[0]["quote"] == candidate["quote"] and
                        inputs[0]["value"] == candidate["value"] and votes == ["clear"], "印刷标题缺少对应的视觉复检")
            if "unit" in fact:
                section = nodes[fact["unit"]]
                require(section["type"] == "document_section" and section["source"] == fact["doc"]
                        and section["page"] == fact["page"], "合订单据归属与原页不符")
            line = fact.get("source_line")
            if line:
                path = f"pages/{fact['doc']}/{fact['page']}.txt"
                if path not in texts:
                    texts[path] = bundle.read(path).decode().splitlines()
                text = texts[path]
                require(1 <= line["number"] <= len(text) and text[line["number"]-1] == line["text"], "引文定位与原文字层不符")
        for item in graph["edges"]:
            require(item["from"] in nodes and item["to"] in nodes and item["evidence"] and
                    set(item["evidence"]) <= nodes.keys(), "图谱存在未登记引用")
        for finding in report["findings"]:
            require(set(finding["evidence"]) <= nodes.keys(), "程序引用不存在")
        if "calculations" in report["policy"]:
            require(report["policy"]["calculations"] == FORMAT, "未知的金额复算格式")
            CalculationEvidence(graph).verify(report["findings"])
        for checksum, instruction in report["calls"].get("instructions", {}).items():
            require(sha(instruction.encode()) == checksum, "提示词摘要不符")
        return case_id, revision, len(entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="离线核对 Fish Audit 导出包的文件与引用。")
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        case_id, revision, files = verify(args.bundle)
        print(f"校验成功：{case_id} R{revision}，{files} 个文件。")
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"校验失败：{error}\n")
