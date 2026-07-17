from __future__ import annotations


CANONICAL_MCP_RESOURCE = "https://mcp.justinnwajei.com"


def normalize_resource(value: str | None) -> str:
    return (value or "").strip().rstrip("/")


def canonical_resource(value: str | None) -> str | None:
    normalized = normalize_resource(value)
    return CANONICAL_MCP_RESOURCE if normalized == CANONICAL_MCP_RESOURCE else None
