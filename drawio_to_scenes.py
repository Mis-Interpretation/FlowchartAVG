"""Convert a draw.io AVG flowchart into per-scene JSON files for AI agents.

Usage:
    python drawio_to_scenes.py <input.drawio> [-o output_dir]
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
import zlib
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

REQUIRE_PREFIXES = ("需要：", "需要:", "requires:", "Requires:")
OBTAIN_PREFIXES = ("获得：", "获得:", "obtains:", "Obtains:")
NEAREST_SNAP_THRESHOLD = 120.0  # px


def strip_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
    for p in prefixes:
        if text.startswith(p):
            return text[len(p):].strip()
    return None


def load_graph_model(path: Path) -> ET.Element:
    """Return the <mxGraphModel> element, decompressing if needed."""
    tree = ET.parse(path)
    root = tree.getroot()
    model = root.find(".//mxGraphModel")
    if model is not None:
        return model
    diagram = root.find(".//diagram")
    if diagram is None or not diagram.text:
        raise ValueError("No <mxGraphModel> or <diagram> payload found")
    raw = base64.b64decode(diagram.text.strip())
    inflated = zlib.decompress(raw, -15).decode("utf-8")
    xml_text = unquote(inflated)
    return ET.fromstring(xml_text)


def parse_cells(model: ET.Element) -> dict[str, dict]:
    cells = {}
    for cell in model.iter("mxCell"):
        cell_id = cell.get("id")
        if cell_id is None:
            continue
        geom = cell.find("mxGeometry")
        geom_data = None
        source_point = None
        target_point = None
        if geom is not None:
            try:
                x = float(geom.get("x", "0") or 0)
                y = float(geom.get("y", "0") or 0)
                w = float(geom.get("width", "0") or 0)
                h = float(geom.get("height", "0") or 0)
                geom_data = (x, y, w, h)
            except ValueError:
                geom_data = None
            for pt in geom.findall("mxPoint"):
                role = pt.get("as")
                try:
                    px = float(pt.get("x", "0") or 0)
                    py = float(pt.get("y", "0") or 0)
                except ValueError:
                    continue
                if role == "sourcePoint":
                    source_point = (px, py)
                elif role == "targetPoint":
                    target_point = (px, py)
        cells[cell_id] = {
            "id": cell_id,
            "value": (cell.get("value") or "").strip(),
            "style": cell.get("style") or "",
            "vertex": cell.get("vertex") == "1",
            "edge": cell.get("edge") == "1",
            "parent": cell.get("parent"),
            "source": cell.get("source"),
            "target": cell.get("target"),
            "geom": geom_data,
            "source_point": source_point,
            "target_point": target_point,
        }
    return cells


def classify(cells: dict[str, dict]):
    scenes, items, edges, edge_labels = {}, {}, {}, []
    for c in cells.values():
        style = c["style"]
        if c["vertex"]:
            if "edgeLabel" in style:
                edge_labels.append(c)
            elif "rounded=1" in style:
                scenes[c["id"]] = c
            elif "text;" in style and "fillColor=none" in style:
                name = strip_prefix(c["value"], OBTAIN_PREFIXES)
                if name:
                    items[c["id"]] = {**c, "item_name": name}
        elif c["edge"]:
            edges[c["id"]] = c
    return scenes, items, edges, edge_labels


def rect_center(geom):
    x, y, w, h = geom
    return (x + w / 2.0, y + h / 2.0)


def point_in_rect(pt, geom) -> bool:
    px, py = pt
    x, y, w, h = geom
    return x <= px <= x + w and y <= py <= y + h


def nearest_vertex(pt, candidates: dict[str, dict]) -> str | None:
    """Return cell id of the candidate whose rect contains pt, else the closest within threshold."""
    if pt is None:
        return None
    for cid, c in candidates.items():
        if c["geom"] and point_in_rect(pt, c["geom"]):
            return cid
    best_id, best_dist = None, math.inf
    for cid, c in candidates.items():
        if not c["geom"]:
            continue
        cx, cy = rect_center(c["geom"])
        d = math.hypot(cx - pt[0], cy - pt[1])
        if d < best_dist:
            best_id, best_dist = cid, d
    if best_dist <= NEAREST_SNAP_THRESHOLD:
        return best_id
    return None


def resolve_endpoints(edge: dict, scenes: dict, items: dict) -> tuple[str | None, str | None]:
    all_vertices = {**scenes, **items}
    src = edge["source"]
    tgt = edge["target"]
    if src is None:
        src = nearest_vertex(edge["source_point"], all_vertices)
    if tgt is None:
        tgt = nearest_vertex(edge["target_point"], all_vertices)
    return src, tgt


def extract_conditions(edge_id: str, edge_labels: list[dict]) -> list[str]:
    conds = []
    for label in edge_labels:
        if label["parent"] != edge_id:
            continue
        name = strip_prefix(label["value"], REQUIRE_PREFIXES)
        if name:
            conds.append(name)
    return conds


def slugify_scene_id(index: int) -> str:
    return f"scene_{index}"


def build_graph(scenes: dict, items: dict, edges: dict, edge_labels: list[dict]):
    # Order scenes by (y, x) of geom so ids are stable across runs.
    ordered = sorted(
        scenes.values(),
        key=lambda c: (c["geom"][1] if c["geom"] else 0, c["geom"][0] if c["geom"] else 0),
    )
    cell_to_sid = {}
    scene_records = {}
    for i, c in enumerate(ordered, 1):
        sid = slugify_scene_id(i)
        cell_to_sid[c["id"]] = sid
        scene_records[sid] = {
            "id": sid,
            "name": c["value"] or sid,
            "source_cell_id": c["id"],
            "exits": [],
            "rewards": [],
            "incoming": [],
        }

    collected_items: set[str] = set()

    for edge in edges.values():
        src, tgt = resolve_endpoints(edge, scenes, items)
        if src is None or tgt is None:
            continue
        conditions = extract_conditions(edge["id"], edge_labels)

        if src in scenes and tgt in items:
            item_name = items[tgt]["item_name"]
            collected_items.add(item_name)
            sid = cell_to_sid[src]
            if item_name not in scene_records[sid]["rewards"]:
                scene_records[sid]["rewards"].append(item_name)
            continue

        if src in scenes and tgt in scenes:
            src_sid = cell_to_sid[src]
            tgt_sid = cell_to_sid[tgt]
            scene_records[src_sid]["exits"].append({
                "to": tgt_sid,
                "to_name": scene_records[tgt_sid]["name"],
                "conditions": conditions,
            })
            scene_records[tgt_sid]["incoming"].append({
                "from": src_sid,
                "from_name": scene_records[src_sid]["name"],
                "conditions": conditions,
            })

    return scene_records, sorted(collected_items)


SCHEMA = {
    "description": "AVG 流程图的场景化 JSON。index.json 是入口；每个场景一个独立 JSON 文件。",
    "index_fields": {
        "source": "原始 drawio 文件名。",
        "generated_at": "本次生成的 ISO8601 本地时间。",
        "scenes": "全部场景的清单，每项给出 id、可读名称 name、对应文件 file。按此列表可按需加载场景。",
        "items": "全流程中玩家可获得的全部物品/线索名称（去重后）。",
        "schema": "本字段；描述各字段的语义，供 AI agent 理解数据含义。"
    },
    "scene_fields": {
        "id": "场景的稳定标识（如 scene_1），与 index.scenes[].id 对应。",
        "name": "场景的可读名称，来自 drawio 节点文字。",
        "source_cell_id": "原 drawio 节点 id，保留用于回溯调试，agent 可忽略。",
        "exits": "从本场景可前往的其他场景列表。每项是一次『跳转机会』。",
        "rewards": "停留/到达本场景时可获得的物品或线索名（字符串数组）。",
        "incoming": "有哪些场景可以到达本场景，以及到达所需条件。用于反向推理。"
    },
    "exit_fields": {
        "to": "目标场景的 id。可用来加载 <to>.json。",
        "to_name": "目标场景的可读名称（冗余字段，便于直接展示）。",
        "conditions": "前往该目标所需的物品/状态名数组；为空数组表示无条件。多个条件默认按『与』语义——需同时满足。"
    },
    "incoming_fields": {
        "from": "来源场景的 id。",
        "from_name": "来源场景的可读名称。",
        "conditions": "从该来源进入本场景所需的条件数组；语义同 exit_fields.conditions。"
    },
    "conventions": {
        "condition_semantics": "默认 AND。若未来引入 OR/NOT，会在该条目下新增 operator 字段并在此说明。",
        "empty_array": "所有列表字段永远是数组（可能为空），不会是 null。",
        "id_stability": "场景 id 由其在画布上的 (y, x) 顺序派生；只要相对位置不变，id 就稳定。"
    }
}


def write_outputs(out_dir: Path, source_name: str, scene_records: dict, items: list[str]):
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "source": source_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "schema": SCHEMA,
        "scenes": [
            {"id": sid, "name": rec["name"], "file": f"{sid}.json"}
            for sid, rec in scene_records.items()
        ],
        "items": items,
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for sid, rec in scene_records.items():
        (out_dir / f"{sid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert draw.io AVG flowchart to scene JSONs.")
    parser.add_argument("input", type=Path, help="Path to .drawio file")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"),
                        help="Output directory (default: ./output)")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    model = load_graph_model(args.input)
    cells = parse_cells(model)
    scenes, items, edges, edge_labels = classify(cells)
    scene_records, collected_items = build_graph(scenes, items, edges, edge_labels)
    write_outputs(args.output, args.input.name, scene_records, collected_items)

    total_exits = sum(len(r["exits"]) for r in scene_records.values())
    total_rewards = sum(len(r["rewards"]) for r in scene_records.values())
    print(f"{len(scene_records)} scenes, {total_exits} exits, {total_rewards} rewards -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
