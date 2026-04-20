"""Download a Miro flowchart board's items and connectors into flat + graph JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import quote

import requests


API_BASE = "https://api.miro.com"
BOARD_URL_RE = re.compile(r"/app/board/([^/?#]+)")
PAGE_SLEEP = 0.7
PAGE_LIMIT = 50
MAX_429_RETRIES = 3


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in ("br", "p", "div", "li"):
            self._parts.append("\n")


    def text(self) -> str:
        return "".join(self._parts).strip()


def strip_html(html: Optional[str]) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def parse_board_id(url: str) -> str:
    m = BOARD_URL_RE.search(url)
    if not m:
        raise ValueError(
            f"无法从链接提取 board ID: {url!r}。\n"
            "期望格式类似: https://miro.com/app/board/XXXXXXXX=/"
        )
    return m.group(1)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _request_with_retry(method: str, url: str, token: str, **kwargs: Any) -> requests.Response:
    resp: Optional[requests.Response] = None
    for attempt in range(MAX_429_RETRIES + 1):
        resp = requests.request(method, url, headers=_headers(token), timeout=30, **kwargs)
        if resp.status_code != 429:
            return resp
        if attempt == MAX_429_RETRIES:
            return resp
        retry_after = float(resp.headers.get("Retry-After", "2"))
        print(f"[429] rate limited, sleeping {retry_after}s (attempt {attempt + 1})", file=sys.stderr)
        time.sleep(retry_after)
    assert resp is not None
    return resp


def verify_board(board_id: str, token: str) -> dict[str, Any]:
    url = f"{API_BASE}/v2/boards/{quote(board_id, safe='')}"
    resp = _request_with_retry("GET", url, token)
    if resp.status_code == 401:
        raise RuntimeError("401 Unauthorized: token 无效或已过期")
    if resp.status_code == 403:
        raise RuntimeError("403 Forbidden: token 没有访问该 board 的权限")
    if resp.status_code == 404:
        raise RuntimeError(f"404 Not Found: board {board_id} 不存在或无权访问")
    resp.raise_for_status()
    return resp.json()


def _fetch_paginated(path: str, board_id: str, token: str, label: str, api_version: str = "v2") -> list[dict[str, Any]]:
    url = f"{API_BASE}/{api_version}/boards/{quote(board_id, safe='')}/{path}"
    params: dict[str, Any] = {"limit": PAGE_LIMIT}
    out: list[dict[str, Any]] = []
    page = 0
    while True:
        page += 1
        resp = _request_with_retry("GET", url, token, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"拉取 {label} 失败 (page {page}): HTTP {resp.status_code} — {resp.text[:300]}"
            )
        payload = resp.json()
        batch = payload.get("data") or []
        out.extend(batch)
        print(f"[{label} page {page}] 累计 {len(out)} / total={payload.get('total')}", file=sys.stderr)

        cursor = payload.get("cursor")
        if not cursor:
            break
        params["cursor"] = cursor
        time.sleep(PAGE_SLEEP)
    return out


def fetch_items(board_id: str, token: str) -> list[dict[str, Any]]:
    return _fetch_paginated("items", board_id, token, "items", api_version="v2-experimental")


def fetch_connectors(board_id: str, token: str) -> list[dict[str, Any]]:
    return _fetch_paginated("connectors", board_id, token, "connectors")


def _extract_item_content(item: dict[str, Any]) -> str:
    data = item.get("data") or {}
    for key in ("content", "title"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    return ""


def _extract_connector_caption(conn: dict[str, Any]) -> str:
    captions = conn.get("captions") or []
    parts: list[str] = []
    for c in captions:
        if isinstance(c, dict):
            content = c.get("content")
            if isinstance(content, str):
                parts.append(content)
    return " | ".join(parts)


def build_graph(items: list[dict[str, Any]], connectors: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for it in items:
        nid = it.get("id")
        if nid is None:
            continue
        html = _extract_item_content(it)
        nodes.append({
            "id": str(nid),
            "type": it.get("type"),
            "content_html": html,
            "content_text": strip_html(html),
            "position": it.get("position"),
            "geometry": it.get("geometry"),
        })
        node_ids.add(str(nid))

    edges: list[dict[str, Any]] = []
    dangling: list[dict[str, Any]] = []
    incoming: dict[str, int] = {nid: 0 for nid in node_ids}
    outgoing: dict[str, int] = {nid: 0 for nid in node_ids}
    for c in connectors:
        start = (c.get("startItem") or {}).get("id")
        end = (c.get("endItem") or {}).get("id")
        caption_html = _extract_connector_caption(c)
        edge = {
            "id": str(c.get("id")),
            "from": str(start) if start is not None else None,
            "to": str(end) if end is not None else None,
            "caption_html": caption_html,
            "caption_text": strip_html(caption_html),
        }
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            dangling.append(edge)
            continue
        edges.append(edge)
        incoming[edge["to"]] = incoming.get(edge["to"], 0) + 1
        outgoing[edge["from"]] = outgoing.get(edge["from"], 0) + 1

    entry_ids = sorted(nid for nid in node_ids if incoming.get(nid, 0) == 0 and outgoing.get(nid, 0) > 0)
    isolated_ids = sorted(nid for nid in node_ids if incoming.get(nid, 0) == 0 and outgoing.get(nid, 0) == 0)

    return {
        "nodes": nodes,
        "edges": edges,
        "dangling_edges": dangling,
        "entry_node_ids": entry_ids,
        "isolated_node_ids": isolated_ids,
    }


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Download Miro flowchart board to JSON.")
    ap.add_argument("url", help="Miro board URL, e.g. https://miro.com/app/board/XXXXXXXX=/")
    args = ap.parse_args()

    token = os.environ.get("MIRO_TOKEN")
    if not token:
        print("错误: 未设置环境变量 MIRO_TOKEN", file=sys.stderr)
        return 2

    try:
        board_id = parse_board_id(args.url)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    print(f"Board ID: {board_id}", file=sys.stderr)

    try:
        info = verify_board(board_id, token)
        print(f"Board 名称: {info.get('name', '<unknown>')}", file=sys.stderr)

        items = fetch_items(board_id, token)
        connectors = fetch_connectors(board_id, token)
        graph = build_graph(items, connectors)
    except requests.RequestException as e:
        print(f"网络错误: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    safe_id = board_id.replace("=", "")
    items_path = f"{safe_id}_items.json"
    conn_path = f"{safe_id}_connectors.json"
    graph_path = f"{safe_id}_graph.json"
    _write_json(items_path, items)
    _write_json(conn_path, connectors)
    _write_json(graph_path, graph)

    print(
        f"完成: items={len(items)}, connectors={len(connectors)}, "
        f"nodes={len(graph['nodes'])}, edges={len(graph['edges'])}, "
        f"dangling={len(graph['dangling_edges'])}, "
        f"entries={len(graph['entry_node_ids'])}, isolated={len(graph['isolated_node_ids'])}"
    )
    print(f"  items:      {items_path}")
    print(f"  connectors: {conn_path}")
    print(f"  graph:      {graph_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
