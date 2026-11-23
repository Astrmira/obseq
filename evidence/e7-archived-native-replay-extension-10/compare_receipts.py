"""Compare complete receipts with per-case exclusions for version metadata."""

import json


def normalize(data, pointers):
    for pointer in pointers:
        parent = data
        for component in pointer.strip("/").split("/")[:-1]:
            parent = parent[int(component)] if isinstance(parent, list) else parent[component]
        key = pointer.rsplit("/", 1)[1]
        key = int(key) if isinstance(parent, list) else key
        version = parent[key]
        if not isinstance(version, str) or not version[:1].isdigit():
            raise ValueError(f"missing version metadata at {pointer}")
        parent[key] = None
    return data


def compare(expected, observed, pointers):
    if expected == observed:
        return "PASS"
    if pointers:
        try:
            left = json.dumps(normalize(json.loads(expected), pointers), sort_keys=True, allow_nan=False)
            right = json.dumps(normalize(json.loads(observed), pointers), sort_keys=True, allow_nan=False)
        except (ValueError, KeyError, IndexError, TypeError):
            return "FAIL_divergence"
        if left == right:
            return "PASS_stable"
    return "FAIL_divergence"
