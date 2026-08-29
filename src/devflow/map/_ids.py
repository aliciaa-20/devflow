"""Stable Change Impact Map node identifiers shared with Phase 7 report linking."""

from __future__ import annotations


def change_node_id() -> str:
    return "change"


def artifact_node_id(artifact_path: str) -> str:
    return f"artifact:{artifact_path}"


def risk_node_id(index: int, category: str) -> str:
    return f"risk:{index}:{category}"


def history_node_id(artifact_path: str) -> str:
    return f"history:{artifact_path}"
