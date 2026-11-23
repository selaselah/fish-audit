"""Stable serialization of audit requests for offline verification."""

import json


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def response_request(model, instruction, content, schema, name, max_tokens):
    return canonical({"model": model, "store": False, "instructions": instruction,
                      "input": [{"role": "user", "content": content}],
                      "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
                      "max_output_tokens": max_tokens}).encode()
