"""Extract certificate text placement from a Photoshop template into a JSON layout.

The PSD should contain the three text layers (name, course, date) positioned on a canvas the
exact size of the pre-printed certificate. Layers are assigned top to bottom: name, course,
date. Requires the optional ``psd-tools`` package (``pip install psd-tools``); the app itself
only needs the JSON this script writes.

Usage:
    python scripts/psd_to_template.py "template certificate.psd" assets/certificate_template.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MM_PER_INCH = 25.4
POINTS_PER_INCH = 72


def extract(psd_path: Path) -> dict:
    """Return the layout dict for one PSD."""
    from psd_tools import PSDImage  # optional dependency, only for this script

    psd = PSDImage.open(psd_path)
    res = psd.image_resources.get_data(1005)
    dpi = res.horizontal / 65536 if res else 300.0
    px_to_mm = MM_PER_INCH / dpi

    layers = [layer for layer in psd.descendants() if layer.kind == "type" and layer.visible]
    if len(layers) < 3:
        raise SystemExit(
            f"Expected 3 visible text layers (name, course, date); found {len(layers)}"
        )
    layers = sorted(layers, key=lambda layer: layer.transform[5])[:3]

    fields = {}
    for key, layer in zip(("name", "course", "date"), layers, strict=True):
        scale_x, _, _, scale_y, anchor_x, baseline_y = layer.transform
        style = layer.engine_dict["StyleRun"]["RunArray"][0]["StyleSheet"]["StyleSheetData"]
        para = layer.engine_dict["ParagraphRun"]["RunArray"][0]["ParagraphSheet"]["Properties"]
        size_px = float(style.get("FontSize", 12)) * (scale_x + scale_y) / 2
        align = {0: "left", 1: "right", 2: "center"}.get(int(para.get("Justification", 0)), "left")
        if align == "center":
            anchor_x = (layer.bbox[0] + layer.bbox[2]) / 2
        fields[key] = {
            "x_mm": round(anchor_x * px_to_mm, 2),
            "baseline_mm": round(baseline_y * px_to_mm, 2),
            "size_pt": round(size_px / dpi * POINTS_PER_INCH, 2),
            "tracking": int(style.get("Tracking", 0)),
            "align": align,
            "caps": int(style.get("FontCaps", 0)) == 2,
            "faux_bold": bool(style.get("FauxBold", False)),
            "sample": layer.text,
        }
    font_name = layers[0].resource_dict["FontSet"][
        layers[0].engine_dict["StyleRun"]["RunArray"][0]["StyleSheet"]["StyleSheetData"]["Font"]
    ]["Name"]
    return {
        "name": " ".join(Path(psd_path).stem.split()).title(),
        "source": Path(psd_path).name,
        "dpi": dpi,
        "page": {
            "width_mm": round(psd.width * px_to_mm, 2),
            "height_mm": round(psd.height * px_to_mm, 2),
        },
        "font": {"postscript_name": str(font_name).strip("'\"")},
        "fields": fields,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("psd", type=Path)
    parser.add_argument(
        "out", type=Path, nargs="?", default=Path("assets/certificate_template.json")
    )
    args = parser.parse_args()
    layout = extract(args.psd)
    args.out.write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}: page {layout['page']['width_mm']} x {layout['page']['height_mm']} mm")
    for key, field in layout["fields"].items():
        print(
            f"  {key:<7} x={field['x_mm']} mm  baseline={field['baseline_mm']} mm  {field['size_pt']} pt"
        )


if __name__ == "__main__":
    main()
