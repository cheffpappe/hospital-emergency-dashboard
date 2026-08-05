"""Analyze Hospital Emergency Dashboard PBIX layout (extracted)."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

LAYOUT = Path(r"C:\Users\Suvarna Shanmukh\AppData\Local\Temp\pbix-extract\extracted\Report\Layout")


def load_layout() -> dict:
    raw = LAYOUT.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-16-le")
    return json.loads(text)


def walk_query(node, tables: set[str], fields: set[str]) -> None:
    if isinstance(node, dict):
        if "Entity" in node and isinstance(node["Entity"], str):
            tables.add(node["Entity"])
        if "Property" in node and isinstance(node["Property"], str):
            fields.add(node["Property"])
        for v in node.values():
            walk_query(v, tables, fields)
    elif isinstance(node, list):
        for item in node:
            walk_query(item, tables, fields)


def extract_title(sv: dict) -> str | None:
    for key in ("vcObjects", "objects"):
        obj = sv.get(key) or {}
        titles = obj.get("title") or []
        for t in titles:
            props = (t.get("properties") or {}).get("text") or {}
            expr = props.get("expr") or {}
            lit = (expr.get("Literal") or {}).get("Value")
            if lit:
                return str(lit).strip("'\"")
    return None


def extract_textbox_plain(config_str: str) -> list[str]:
    # Power BI textboxes store runs with text values
    texts = re.findall(r'"textValue"\s*:\s*"((?:\\.|[^"\\])*)"', config_str)
    cleaned = []
    for t in texts:
        t = bytes(t, "utf-8").decode("unicode_escape") if "\\" in t else t
        t = t.strip()
        if t and t not in cleaned:
            cleaned.append(t)
    # fallback: literal display strings
    if not cleaned:
        for m in re.findall(r"Value\":\"'([^']{2,120})'\"", config_str):
            if m not in cleaned:
                cleaned.append(m)
    return cleaned


def main() -> None:
    layout = load_layout()
    tables: set[str] = set()
    fields: set[str] = set()
    visual_types: Counter[str] = Counter()
    pages = []

    for section in layout.get("sections", []):
        page = {
            "name": section.get("displayName"),
            "visuals": [],
        }
        for vc in section.get("visualContainers", []):
            cfg = json.loads(vc["config"])
            sv = cfg.get("singleVisual") or {}
            vt = sv.get("visualType", "unknown")
            visual_types[vt] += 1
            title = extract_title(sv)
            walk_query(sv.get("prototypeQuery"), tables, fields)
            walk_query(sv.get("projections"), tables, fields)

            projections = []
            for role, items in (sv.get("projections") or {}).items():
                for item in items or []:
                    q = item.get("queryRef")
                    if q:
                        projections.append(f"{role}:{q}")

            entry = {
                "type": vt,
                "title": title,
                "projections": projections,
            }
            if vt == "textbox":
                entry["texts"] = extract_textbox_plain(vc["config"])
            if vt == "slicer":
                entry["texts"] = extract_textbox_plain(vc["config"])
            page["visuals"].append(entry)
        pages.append(page)

    # Also harvest string literals that look like chart titles from raw
    raw_bytes = LAYOUT.read_bytes()
    raw = (
        raw_bytes.decode("utf-16")
        if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff")
        else raw_bytes.decode("utf-16-le")
    )
    literals = sorted(set(re.findall(r"\"Value\":\"'([^']{3,100})'\"", raw)))

    out = {
        "pages": pages,
        "tables": sorted(tables),
        "fields": sorted(fields),
        "visualTypeCounts": dict(visual_types),
        "literals": literals,
    }
    out_path = Path(__file__).resolve().parents[1] / "docs" / "pbix-analysis.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print("PAGES:", [p["name"] for p in pages])
    print("TABLES:", sorted(tables))
    print("FIELDS:", sorted(fields))
    print("VISUALS:", dict(visual_types))
    print("LITERALS sample:")
    for lit in literals[:80]:
        print(" -", lit)


if __name__ == "__main__":
    main()
