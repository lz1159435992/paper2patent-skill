#!/usr/bin/env python3
"""Render monochrome patent diagrams with fitted text, labels and canvas bounds."""
from __future__ import annotations
import argparse
import heapq
import json
import math
import sys
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

FONT_SIZE, BOX_W, BOX_H, GAP, MARGIN = 16, 260, 64, 48, 40


def number(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return float(value)


def units(text):
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def wrap_label(text, width=14):
    if not isinstance(text, str):
        raise ValueError("label must be a string")
    number(width, "wrap_width", 1)
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            if current and units(current + char) > width * 2:
                lines.append(current)
                current = ""
            current += char
        lines.append(current)
    return lines or [""]


def text_size(lines, font_size):
    return max((units(line) * font_size * 0.5 for line in lines), default=0), len(lines) * font_size * 1.3


def text_svg(cx, cy, lines, font_size=FONT_SIZE, font_family=None):
    family = font_family or "Microsoft YaHei, Noto Sans CJK SC, SimSun, sans-serif"
    first_y = cy - (len(lines) - 1) * font_size * 1.3 / 2 + font_size * 0.35
    spans = [
        f'<tspan x="{cx:g}" y="{first_y + i * font_size * 1.3:g}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    ]
    return (f'<text font-size="{font_size:g}" text-anchor="middle" fill="#000" '
            f'font-family={quoteattr(family)}>' + "".join(spans) + "</text>")


def validate_spec(spec):
    if not isinstance(spec, dict) or spec.get("diagram_type") not in ("flowchart", "block"):
        raise ValueError("diagram_type must be 'flowchart' or 'block'")
    if spec.get("layout", "horizontal") not in ("horizontal", "vertical"):
        raise ValueError("layout must be 'horizontal' or 'vertical'")
    if not isinstance(spec.get("nodes"), list) or not spec["nodes"]:
        raise ValueError("nodes must be a nonempty array")
    ids = set()
    for node in spec["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise ValueError("each node must have a nonempty string id")
        if node["id"] in ids:
            raise ValueError(f"duplicate node id: {node['id']}")
        ids.add(node["id"])
        if "rounded" in node and not isinstance(node["rounded"], bool):
            raise ValueError("node.rounded must be boolean")
        if not isinstance(node.get("label"), str) or not node["label"].strip():
            raise ValueError(f"node {node['id']} needs a nonempty label")
        if node.get("shape", "process") not in ("process", "decision", "terminator"):
            raise ValueError(f"invalid shape on {node['id']}")
        for key in ("x", "y", "w", "h", "wrap_width", "font_size"):
            if key in node:
                number(node[key], f"node.{key}", 1 if key not in {"x", "y"} else None)
        for key in ("note", "reference"):
            if key in node and not isinstance(node[key], str):
                raise ValueError(f"node.{key} must be a string")
    for key in ("box_w", "box_h", "wrap_width", "font_size", "width", "height", "gap", "margin"):
        if key in spec:
            number(spec[key], key, 1)
    for key in ("figure_no", "title", "font_family"):
        if key in spec and not isinstance(spec[key], str):
            raise ValueError(f"{key} must be a string")
    for key in ("show_title", "show_figure_no"):
        if key in spec and not isinstance(spec[key], bool):
            raise ValueError(f"{key} must be boolean")
    if not isinstance(spec.get("edges", []), list):
        raise ValueError("edges must be an array")
    edges = []
    for raw in spec.get("edges", []):
        if isinstance(raw, list) and len(raw) == 2:
            edge = {"source": raw[0], "target": raw[1]}
        elif isinstance(raw, dict):
            edge = dict(raw)
        else:
            raise ValueError("edge must be [source, target] or an object")
        if not all(isinstance(edge.get(k), str) and edge[k] in ids for k in ("source", "target")):
            raise ValueError("edge endpoints must reference existing node ids")
        if edge.get("route") not in (None, "bottom_return"):
            raise ValueError("route must be 'bottom_return' when supplied")
        if "points" in edge:
            points = edge["points"]
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError("points must contain at least two coordinate pairs")
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    raise ValueError("each point must contain x and y")
                number(point[0], "point.x")
                number(point[1], "point.y")
            if all(point == points[0] for point in points):
                raise ValueError("edge points must contain two distinct positions")
        if "label" in edge and not isinstance(edge["label"], str):
            raise ValueError("edge label must be a string")
        for key in ("source_port", "target_port"):
            if key in edge and edge[key] not in ("top", "bottom", "left", "right"):
                raise ValueError(f"{key} must select top, bottom, left or right")
        for key in ("label_x", "label_y"):
            if key in edge:
                number(edge[key], key)
        edges.append(edge)
    if not isinstance(spec.get("annotations", []), list):
        raise ValueError("annotations must be an array")
    for ann in spec.get("annotations", []):
        if not isinstance(ann, dict) or not isinstance(ann.get("text"), str):
            raise ValueError("annotation needs text, x and y")
        number(ann.get("x"), "annotation.x")
        number(ann.get("y"), "annotation.y")
        number(ann.get("font_size", 14), "annotation.font_size", 1)
        number(ann.get("wrap_width", 14), "annotation.wrap_width", 1)
    return edges


def fit_nodes(spec):
    fitted = []
    default_font = spec.get("font_size", FONT_SIZE)
    for raw in spec["nodes"]:
        node = dict(raw)
        font = node.get("font_size", default_font)
        width = node.get("w", spec.get("box_w", BOX_W))
        label = "\n".join(value for value in (node.get("reference"), node["label"], node.get("note")) if value)
        decision = node.get("shape") == "decision"
        budget = max(1, (width / (2 if decision else 1) - 24) / font)
        lines = wrap_label(label, min(node.get("wrap_width", spec.get("wrap_width", 14)), budget))
        tw, th = text_size(lines, font)
        factor = 2 if decision else 1
        node.update(
            w=max(width, factor * tw + 24),
            h=max(node.get("h", spec.get("box_h", BOX_H)), factor * th + 24),
            lines=lines, font=font,
        )
        fitted.append(node)
    return fitted


def position_nodes(spec, nodes, caption_height):
    margin, gap = spec.get("margin", MARGIN), spec.get("gap", GAP)
    vertical = spec["diagram_type"] == "flowchart" or spec.get("layout") == "vertical"
    max_width = max(node["w"] for node in nodes)
    auto_x, auto_y = margin, margin + caption_height
    for node in nodes:
        x = margin + (max_width - node["w"]) / 2 if vertical else auto_x
        node["x"] = float(node.get("x", x))
        node["y"] = float(node.get("y", auto_y))
        auto_x = node["x"] + node["w"] + gap
        if vertical:
            auto_y = node["y"] + node["h"] + gap
    for i, left in enumerate(nodes):
        for right in nodes[i + 1:]:
            if (max(left["x"], right["x"]) < min(left["x"] + left["w"], right["x"] + right["w"])
                and max(left["y"], right["y"]) < min(left["y"] + left["h"], right["y"] + right["h"])):
                raise ValueError(f"nodes overlap: {left['id']} and {right['id']}")


def ports(node):
    x, y, w, h = (node[key] for key in ("x", "y", "w", "h"))
    return {"top": (x + w / 2, y), "bottom": (x + w / 2, y + h),
            "left": (x, y + h / 2), "right": (x + w, y + h / 2)}


EPS = 1e-7


def segment_hits_rect(a, b, rect):
    lower, upper = 0.0, 1.0
    for axis, key, size in ((0, "x", "w"), (1, "y", "h")):
        lo, hi = rect[key] + EPS, rect[key] + rect[size] - EPS
        delta = b[axis] - a[axis]
        if abs(delta) < EPS:
            if not lo < a[axis] < hi:
                return False
        else:
            first, last = sorted(((lo - a[axis]) / delta, (hi - a[axis]) / delta))
            lower, upper = max(lower, first), min(upper, last)
            if upper - lower <= EPS:
                return False
    return upper - lower > EPS


def intersects(points, nodes, excluded):
    return any(
        segment_hits_rect(a, b, node)
        for node in nodes if node["id"] not in excluded
        for a, b in zip(points, points[1:])
    )


def clean_points(points):
    result = []
    for point in points:
        if result and math.dist(result[-1], point) < EPS:
            continue
        while len(result) > 1:
            a, b = result[-2], result[-1]
            ab, bc = (b[0] - a[0], b[1] - a[1]), (point[0] - b[0], point[1] - b[1])
            if abs(ab[0] * bc[1] - ab[1] * bc[0]) < EPS and ab[0] * bc[0] + ab[1] * bc[1] >= 0:
                result.pop()
            else:
                break
        result.append(point)
    return result


def orthogonal_path(start, end, obstacles, clearance):
    if math.dist(start, end) < EPS:
        return [start]
    padding = min(2, clearance / 4)
    blocked = [{**node, "x": node["x"] - padding, "y": node["y"] - padding,
                "w": node["w"] + 2 * padding, "h": node["h"] + 2 * padding} for node in obstacles]
    xs = sorted({start[0], end[0], *(n["x"] - clearance for n in obstacles),
                 *(n["x"] + n["w"] + clearance for n in obstacles)})
    ys = sorted({start[1], end[1], *(n["y"] - clearance for n in obstacles),
                 *(n["y"] + n["h"] + clearance for n in obstacles)})
    free = {}
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            if not any(n["x"] + EPS < x < n["x"] + n["w"] - EPS
                       and n["y"] + EPS < y < n["y"] + n["h"] - EPS for n in blocked):
                free[(ix, iy)] = (x, y)
    source, target = (xs.index(start[0]), ys.index(start[1])), (xs.index(end[0]), ys.index(end[1]))
    if source not in free or target not in free:
        raise ValueError("selected port is blocked; increase spacing or choose another port")
    initial = (source, 2)
    queue, best, parent = [(0.0, source, 2)], {initial: 0.0}, {}
    while queue:
        cost, point, direction = heapq.heappop(queue)
        state = (point, direction)
        if cost > best.get(state, math.inf) + EPS:
            continue
        if point == target:
            path = [free[point]]
            while state in parent:
                state = parent[state]
                path.append(free[state[0]])
            return clean_points(list(reversed(path)))
        ix, iy = point
        for neighbor, new_dir in (((ix - 1, iy), 0), ((ix + 1, iy), 0),
                                  ((ix, iy - 1), 1), ((ix, iy + 1), 1)):
            if neighbor not in free or intersects([free[point], free[neighbor]], blocked, set()):
                continue
            new_cost = cost + math.dist(free[point], free[neighbor])
            if direction != 2 and new_dir != direction:
                new_cost += clearance
            new_state = (neighbor, new_dir)
            if new_cost + EPS < best.get(new_state, math.inf):
                best[new_state], parent[new_state] = new_cost, state
                heapq.heappush(queue, (new_cost, neighbor, new_dir))
    raise ValueError("no clear orthogonal route; adjust node positions or supply points")


def route_edge(edge, nodes, vertical, gap):
    by_id = {node["id"]: node for node in nodes}
    src, dst = by_id[edge["source"]], by_id[edge["target"]]
    sp, dp = ports(src), ports(dst)
    if edge.get("points"):
        points = [tuple(map(float, p)) for p in edge["points"]]
        for endpoint, neighbor, options, key in ((0, 1, sp, "source_port"), (-1, -2, dp, "target_port")):
            old = points[endpoint]
            chosen = edge.get(key) or min(options, key=lambda name: math.dist(old, options[name]))
            anchor, adjacent = options[chosen], points[neighbor]
            if len(points) > 2:
                if old[0] == adjacent[0]:
                    points[neighbor] = (anchor[0], adjacent[1])
                elif old[1] == adjacent[1]:
                    points[neighbor] = (adjacent[0], anchor[1])
            points[endpoint] = anchor
    else:
        if src is dst:
            default_source, default_target = "right", "bottom"
        elif edge.get("route") == "bottom_return":
            default_source = default_target = "bottom"
        elif abs(dp["top"][0] - sp["top"][0]) > abs(dp["left"][1] - sp["left"][1]):
            default_source, default_target = ("right", "left") if dst["x"] > src["x"] else ("left", "right")
        else:
            default_source, default_target = ("bottom", "top") if dst["y"] > src["y"] else ("top", "bottom")
        source_port, target_port = edge.get("source_port", default_source), edge.get("target_port", default_target)
        if src is dst and source_port == target_port:
            raise ValueError("automatic self-loop needs different source and target ports")
        a, b = sp[source_port], dp[target_port]
        clearance = max(2, min(gap / 4, 10))
        normals = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}
        astub = tuple(a[i] + clearance * normals[source_port][i] for i in range(2))
        bstub = tuple(b[i] + clearance * normals[target_port][i] for i in range(2))
        if intersects([a, astub], nodes, set()) or intersects([bstub, b], nodes, set()):
            raise ValueError("port departure is blocked; adjust spacing or select another port")
        if edge.get("route") == "bottom_return":
            lane = max(n["y"] + n["h"] for n in nodes) + clearance
            left, right = (astub[0], lane), (bstub[0], lane)
            middle = orthogonal_path(astub, left, nodes, clearance) + [right]
            middle += orthogonal_path(right, bstub, nodes, clearance)
        else:
            candidates = [
                clean_points([astub, (bstub[0], astub[1]), bstub]),
                clean_points([astub, (astub[0], bstub[1]), bstub]),
            ]
            clear = [p for p in candidates if not intersects(p, nodes, set())]
            middle = min(clear, key=len) if clear else orthogonal_path(astub, bstub, nodes, clearance)
        points = [a, *middle, b]
    points = clean_points(points)
    if len(points) < 2:
        raise ValueError("edge collapses to one port; add waypoints or select different ports")
    # Every path, including manual routes and loops, passes the same geometry check.
    if intersects(points, nodes, set()):
        raise ValueError("edge crosses a node or caption; adjust points, ports or spacing")
    return points


def build_diagram(spec):
    edges = validate_spec(spec)
    font = spec.get("font_size", FONT_SIZE)
    caption = []
    if spec.get("show_figure_no", True):
        caption.append(spec.get("figure_no") or "图1")
    if spec.get("show_title", True) and spec.get("title"):
        caption.extend(wrap_label(spec["title"], 32))
    caption_height = len(caption) * font * 1.3 + 24 if caption else 0
    nodes = fit_nodes(spec)
    position_nodes(spec, nodes, caption_height)
    route_obstacles = list(nodes)
    if caption:
        caption_x = (min(n["x"] for n in nodes) + max(n["x"] + n["w"] for n in nodes)) / 2
        caption_y = min(n["y"] for n in nodes) - caption_height / 2
        caption_w, caption_h = text_size(caption, font)
        route_obstacles.append({"id": None, "x": caption_x - caption_w / 2, "y": caption_y - caption_h / 2,
                                "w": caption_w, "h": caption_h})
    elements, labels, bounds = [], [], []

    def record_text(x, y, lines, size, attrs=""):
        tw, th = text_size(lines, size)
        bounds.append((x - tw / 2, y - th / 2, x + tw / 2, y + th / 2))
        labels.append(f"<g {attrs}>" + text_svg(x, y, lines, size, spec.get("font_family")) + "</g>")

    vertical = spec["diagram_type"] == "flowchart" or spec.get("layout") == "vertical"
    for edge in edges:
        points = route_edge(edge, route_obstacles, vertical, spec.get("gap", GAP))
        clean = [p for i, p in enumerate(points) if not i or p != points[i - 1]]
        if len(clean) < 2:
            raise ValueError("edge collapses to one port; add waypoints or select different ports")
        bounds.append((min(p[0] for p in clean), min(p[1] for p in clean),
                       max(p[0] for p in clean), max(p[1] for p in clean)))
        coords = " ".join(f"{x:g},{y:g}" for x, y in clean)
        attrs = f'data-source={quoteattr(edge["source"])} data-target={quoteattr(edge["target"])}'
        elements.append(f'<polyline {attrs} points="{coords}" fill="none" stroke="#000" stroke-width="2" marker-end="url(#arrow)" />')
        if edge.get("label"):
            a, b = max(zip(clean, clean[1:]), key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]))
            lines = wrap_label(edge["label"])
            tw, th = text_size(lines, 14)
            lx, ly = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if a[0] == b[0]:
                lx += tw / 2 + 8
            else:
                ly -= th / 2 + 8
            if "label_x" not in edge and "label_y" not in edge:
                options = [(lx, ly)]
                if a[0] == b[0]:
                    options.append((a[0] - tw / 2 - 8, ly))
                else:
                    options.append((lx, (a[1] + b[1]) / 2 + th / 2 + 8))
                free = [(x, y) for x, y in options if not any(
                    max(x - tw / 2, n["x"]) < min(x + tw / 2, n["x"] + n["w"])
                    and max(y - th / 2, n["y"]) < min(y + th / 2, n["y"] + n["h"])
                    for n in route_obstacles)]
                if not free:
                    raise ValueError("edge label overlaps a node; set label_x and label_y")
                lx, ly = free[0]
            record_text(float(edge.get("label_x", lx)), float(edge.get("label_y", ly)), lines, 14, 'data-edge-label="true"')

    for node in nodes:
        x, y, w, h = (node[key] for key in ("x", "y", "w", "h"))
        bounds.append((x, y, x + w, y + h))
        if node.get("shape") == "decision":
            points = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
            coords = " ".join(f"{px:g},{py:g}" for px, py in points)
            shape = f'<polygon points="{coords}"'
        else:
            radius = 18 if node.get("rounded", node.get("shape") == "terminator") else 0
            shape = f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{radius}"'
        attrs = f'data-node-id={quoteattr(node["id"])}'
        elements.append(f'<g {attrs}>{shape} fill="#fff" stroke="#000" stroke-width="2" />'
                        + text_svg(x + w / 2, y + h / 2, node["lines"], node["font"], spec.get("font_family")) + "</g>")
    if caption:
        cx = (min(n["x"] for n in nodes) + max(n["x"] + n["w"] for n in nodes)) / 2
        cy = min(n["y"] for n in nodes) - caption_height / 2
        record_text(cx, cy, caption, font, 'data-caption="true"')
    for ann in spec.get("annotations", []):
        record_text(float(ann["x"]), float(ann["y"]), wrap_label(ann["text"], ann.get("wrap_width", 14)),
                    ann.get("font_size", 14), 'data-annotation="true"')
    margin = spec.get("margin", MARGIN)
    ox = min(0, min(b[0] for b in bounds) - margin)
    oy = min(0, min(b[1] for b in bounds) - margin)
    width = max(spec.get("width", 0), max(b[2] for b in bounds) + margin - ox)
    height = max(spec.get("height", 0), max(b[3] for b in bounds) + margin - oy)
    # Fit the canvas after every node, routed edge, label and annotation is positioned.
    header = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" '
              f'viewBox="{ox:g} {oy:g} {width:g} {height:g}">'
              '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
              'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#000" /></marker></defs>'
              f'<rect x="{ox:g}" y="{oy:g}" width="{width:g}" height="{height:g}" fill="#fff" />')
    return "\n".join([header, *elements, *labels, "</svg>"])


def build_flowchart(spec):
    return build_diagram({**spec, "diagram_type": "flowchart"})


def build_block(spec):
    return build_diagram({**spec, "diagram_type": "block"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--png", type=Path, help="optional preview, requires CairoSVG")
    parser.add_argument("--scale", type=float, default=2, help="PNG preview scale")
    args = parser.parse_args(argv)
    try:
        number(args.scale, "scale", 0.1)
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
        svg = build_diagram(spec)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Figure input error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {args.output}")
    if args.png:
        try:
            import cairosvg
            args.png.parent.mkdir(parents=True, exist_ok=True)
            cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(args.png), scale=args.scale)
        except (ImportError, OSError, ValueError) as exc:
            print(f"SVG saved; PNG preview unavailable: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
