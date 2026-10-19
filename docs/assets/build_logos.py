"""Builds the Spec Master logos (stdlib only): the banner used by the README
and a square mark. Retro neon on a perspective grid, with light trails.

The letters are hand-built polylines on a 4x6 grid, so the SVGs need no
font and render the same everywhere. Run from anywhere:

    python3 docs/assets/build_logos.py

and it rewrites spec-master-logo.svg and spec-master-mark.svg next to it.
"""
import os
W, H = 1280, 400
HORIZON = 262
VP = (W / 2, HORIZON)
CYAN, CYAN_SOFT, CORE, ORANGE = "#19e6ff", "#7ff3ff", "#eaffff", "#ff8a1f"

# glyph: (width, [polylines]); a polyline ending with "Z" is closed
G = {
    "S": (4, [[(4, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3), (4, 4), (4, 5), (3, 6), (0, 6)]]),
    "P": (4, [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]]),
    "E": (4, [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]]),
    "C": (4, [[(4, 0), (1, 0), (0, 1), (0, 5), (1, 6), (4, 6)]]),
    "M": (4.6, [[(0, 6), (0, 0), (1, 0), (2.3, 2.6), (3.6, 0), (4.6, 0), (4.6, 6)]]),
    "A": (4, [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)], [(0, 3.6), (4, 3.6)]]),
    "T": (4, [[(0, 0), (4, 0)], [(2, 0), (2, 6)]]),
    "R": (4, [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)], [(2.4, 3), (4, 4.6), (4, 6)]]),
    "H": (4, [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]]),
    "N": (4, [[(0, 6), (0, 0), (4, 6), (4, 0)]]),
    "F": (4, [[(4, 0), (0, 0), (0, 6)], [(0, 3), (3, 3)]]),
    "O": (4, [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), "Z"]]),
    "D": (4, [[(0, 0), (3, 0), (4, 1), (4, 5), (3, 6), (0, 6), "Z"]]),
    "I": (0, [[(0, 0), (0, 6)]]),
    "V": (4, [[(0, 0), (0, 3.6), (2, 6), (4, 3.6), (4, 0)]]),
    "L": (4, [[(0, 0), (0, 6), (4, 6)]]),
    "-": (2.4, [[(0, 3), (2.4, 3)]]),
    " ": (2.4, []),
}


def text_paths(text, x, y, unit, tracking):
    """(path d, total width) for `text` with its top-left at (x, y)."""
    cursor, parts = 0.0, []
    for index, char in enumerate(text):
        width, lines = G[char]
        for line in lines:
            closed = line[-1] == "Z"
            points = [p for p in line if p != "Z"]
            coords = " L ".join(f"{x + (cursor + px) * unit:.1f} {y + py * unit:.1f}" for px, py in points)
            parts.append(f"M {coords}" + (" Z" if closed else ""))
        cursor += width + (tracking if index < len(text) - 1 else 0)
    return " ".join(parts), cursor * unit


def centered(text, y, unit, tracking):
    _, width = text_paths(text, 0, 0, unit, tracking)
    return text_paths(text, (W - width) / 2, y, unit, tracking)[0]


def grid():
    lines = []
    for i in range(-14, 15):  # rays from the vanishing point to the bottom edge
        x_bottom = VP[0] + i * 118
        lines.append(f"M {VP[0]:.1f} {VP[1]} L {x_bottom:.1f} {H}")
    for z in range(1, 16):  # floor lines, closer together towards the horizon
        y = HORIZON + (H - HORIZON) / (z * 0.62 + 0.38)
        lines.append(f"M 0 {y:.1f} L {W} {y:.1f}")
    return " ".join(lines)


def floor_x(ray_x_bottom, y):
    t = (H - y) / (H - HORIZON)
    return ray_x_bottom + (VP[0] - ray_x_bottom) * t


def banner():
    word = centered("SPEC MASTER", 64, 18.5, 1.25)
    tagline = centered("HARNESS FOR SPEC-DRIVEN DEVELOPMENT", 204, 3.1, 2.3)
    lane_y = HORIZON + (H - HORIZON) / (3 * 0.62 + 0.38)
    ray = VP[0] - 3 * 118
    turn_x = floor_x(ray, lane_y)
    head_x = 1004
    trail = f"M {ray:.1f} {H} L {turn_x:.1f} {lane_y:.1f} L {head_x} {lane_y:.1f}"
    far_y = HORIZON + (H - HORIZON) / (7 * 0.62 + 0.38)
    far_head = 842
    far_trail = f"M {W} {far_y:.1f} L {far_head} {far_y:.1f}"
    chamfer = 26
    panel = (f"M {chamfer} 0 L {W - chamfer} 0 L {W} {chamfer} L {W} {H - chamfer} L {W - chamfer} {H} "
             f"L {chamfer} {H} L 0 {H - chamfer} L 0 {chamfer} Z")
    corner = 34
    brackets = " ".join([
        f"M 18 {18 + corner} L 18 18 L {18 + corner} 18",
        f"M {W - 18 - corner} 18 L {W - 18} 18 L {W - 18} {18 + corner}",
        f"M 18 {H - 18 - corner} L 18 {H - 18} L {18 + corner} {H - 18}",
        f"M {W - 18 - corner} {H - 18} L {W - 18} {H - 18} L {W - 18} {H - 18 - corner}",
    ])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
  <title id="title">Spec Master</title>
  <desc id="desc">Spec Master: harness for spec-driven development. Neon lettering over a perspective grid with an orange light trail.</desc>
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#02030a"/>
      <stop offset="0.72" stop-color="#051226"/>
      <stop offset="1" stop-color="#0a2a44"/>
    </linearGradient>
    <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#030712"/>
      <stop offset="1" stop-color="#010207"/>
    </linearGradient>
    <linearGradient id="gridFade" gradientUnits="userSpaceOnUse" x1="0" y1="{HORIZON}" x2="0" y2="{H}">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>
      <stop offset="0.35" stop-color="{CYAN}" stop-opacity="0.28"/>
      <stop offset="1" stop-color="{CYAN}" stop-opacity="0.6"/>
    </linearGradient>
    <linearGradient id="horizonFade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="{CYAN_SOFT}" stop-opacity="1"/>
      <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="haze" cx="0.5" cy="1" r="0.75" fx="0.5" fy="1">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0.22"/>
      <stop offset="0.6" stop-color="{CYAN}" stop-opacity="0.05"/>
      <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">
      <rect width="4" height="1" fill="#ffffff" fill-opacity="0.035"/>
    </pattern>
    <filter id="glowWide" x="-10%" y="-40%" width="120%" height="180%">
      <feGaussianBlur stdDeviation="9"/>
    </filter>
    <filter id="glow" x="-10%" y="-40%" width="120%" height="180%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="panel"><path d="{panel}"/></clipPath>
  </defs>

  <g clip-path="url(#panel)">
    <rect width="{W}" height="{HORIZON}" fill="url(#sky)"/>
    <rect x="0" y="{HORIZON - 150}" width="{W}" height="150" fill="url(#haze)"/>
    <rect y="{HORIZON}" width="{W}" height="{H - HORIZON}" fill="url(#floor)"/>
    <path d="{grid()}" stroke="url(#gridFade)" stroke-width="1.4" fill="none"/>
    <rect x="0" y="{HORIZON - 5}" width="{W}" height="10" fill="url(#horizonFade)" filter="url(#glowWide)"/>
    <rect x="0" y="{HORIZON - 0.8}" width="{W}" height="1.6" fill="url(#horizonFade)"/>

    <path d="{far_trail}" stroke="{CYAN}" stroke-width="6" fill="none" opacity="0.45" filter="url(#glowWide)"/>
    <path d="{far_trail}" stroke="{CYAN}" stroke-width="2.2" fill="none"/>
    <path d="M {far_head} {far_y - 3.5:.1f} L {far_head - 14} {far_y - 1.5:.1f} L {far_head - 14} {far_y + 1.5:.1f} L {far_head} {far_y + 3.5:.1f} Z" fill="{CORE}" filter="url(#glow)"/>

    <path d="{trail}" stroke="{ORANGE}" stroke-width="12" fill="none" stroke-linejoin="miter" opacity="0.55" filter="url(#glowWide)"/>
    <path d="{trail}" stroke="{ORANGE}" stroke-width="4.5" fill="none" stroke-linejoin="miter"/>
    <path d="{trail}" stroke="#ffe2c2" stroke-width="1.4" fill="none" stroke-linejoin="miter"/>
    <path d="M {head_x} {lane_y - 7:.1f} L {head_x + 26} {lane_y - 3:.1f} L {head_x + 26} {lane_y + 3:.1f} L {head_x} {lane_y + 7:.1f} Z" fill="{ORANGE}" filter="url(#glow)"/>
    <path d="M {head_x + 4} {lane_y - 1.5:.1f} L {head_x + 22} {lane_y - 1:.1f} L {head_x + 22} {lane_y + 1:.1f} L {head_x + 4} {lane_y + 1.5:.1f} Z" fill="#fff4e6"/>

    <path d="{word}" stroke="{CYAN}" stroke-width="15" fill="none" stroke-linecap="square" stroke-linejoin="miter" opacity="0.7" filter="url(#glowWide)"/>
    <path d="{word}" stroke="{CYAN}" stroke-width="8.5" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>
    <path d="{word}" stroke="{CORE}" stroke-width="2.6" fill="none" stroke-linecap="square" stroke-linejoin="miter"/>

    <path d="{tagline}" stroke="{CYAN_SOFT}" stroke-width="1.9" fill="none" stroke-linecap="square" stroke-linejoin="miter" filter="url(#glow)"/>

    <rect width="{W}" height="{H}" fill="url(#scan)"/>
  </g>
  <path d="{panel}" stroke="{CYAN}" stroke-opacity="0.55" stroke-width="2" fill="none"/>
  <path d="{brackets}" stroke="{CYAN_SOFT}" stroke-width="3" fill="none" stroke-linecap="square" filter="url(#glow)"/>
</svg>
"""


S = 512
MARK_HORIZON = 352
MARK_VP = (S / 2, MARK_HORIZON)


def mark_centered(text, y, unit, tracking):
    _, width = text_paths(text, 0, 0, unit, tracking)
    return text_paths(text, (S - width) / 2, y, unit, tracking)[0]


def mark_grid():
    lines = [f"M {MARK_VP[0]:.1f} {MARK_VP[1]} L {MARK_VP[0] + i * 64:.1f} {S}" for i in range(-9, 10)]
    for z in range(1, 12):
        y = MARK_HORIZON + (S - MARK_HORIZON) / (z * 0.62 + 0.38)
        lines.append(f"M 0 {y:.1f} L {S} {y:.1f}")
    return " ".join(lines)


def mark():
    mono = mark_centered("SM", 110, 30, 1.4)
    lane_y = MARK_HORIZON + (S - MARK_HORIZON) / (2 * 0.62 + 0.38)
    ray = MARK_VP[0] - 2 * 64
    turn_x = ray + (MARK_VP[0] - ray) * ((S - lane_y) / (S - MARK_HORIZON))
    head_x = 404
    trail = f"M {ray:.1f} {S} L {turn_x:.1f} {lane_y:.1f} L {head_x} {lane_y:.1f}"
    c = 34
    panel = f"M {c} 0 L {S - c} 0 L {S} {c} L {S} {S - c} L {S - c} {S} L {c} {S} L 0 {S - c} L 0 {c} Z"
    k = 30
    brackets = " ".join([
        f"M 20 {20 + k} L 20 20 L {20 + k} 20", f"M {S - 20 - k} 20 L {S - 20} 20 L {S - 20} {20 + k}",
        f"M 20 {S - 20 - k} L 20 {S - 20} L {20 + k} {S - 20}",
        f"M {S - 20 - k} {S - 20} L {S - 20} {S - 20} L {S - 20} {S - 20 - k}",
    ])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}" role="img" aria-labelledby="title">
  <title id="title">Spec Master</title>
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#02030a"/><stop offset="0.7" stop-color="#051226"/><stop offset="1" stop-color="#0a2a44"/>
    </linearGradient>
    <linearGradient id="gridFade" gradientUnits="userSpaceOnUse" x1="0" y1="{MARK_HORIZON}" x2="0" y2="{S}">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset="0.35" stop-color="{CYAN}" stop-opacity="0.3"/>
      <stop offset="1" stop-color="{CYAN}" stop-opacity="0.65"/>
    </linearGradient>
    <linearGradient id="horizonFade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset="0.5" stop-color="{CYAN_SOFT}"/>
      <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="haze" cx="0.5" cy="1" r="0.8">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0.24"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">
      <rect width="4" height="1" fill="#ffffff" fill-opacity="0.035"/>
    </pattern>
    <filter id="glowWide" x="-20%" y="-40%" width="140%" height="180%"><feGaussianBlur stdDeviation="10"/></filter>
    <filter id="glow" x="-20%" y="-40%" width="140%" height="180%">
      <feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="panel"><path d="{panel}"/></clipPath>
  </defs>
  <g clip-path="url(#panel)">
    <rect width="{S}" height="{MARK_HORIZON}" fill="url(#sky)"/>
    <rect x="0" y="{MARK_HORIZON - 160}" width="{S}" height="160" fill="url(#haze)"/>
    <rect y="{MARK_HORIZON}" width="{S}" height="{S - MARK_HORIZON}" fill="#020510"/>
    <path d="{mark_grid()}" stroke="url(#gridFade)" stroke-width="1.5" fill="none"/>
    <rect x="0" y="{MARK_HORIZON - 5}" width="{S}" height="10" fill="url(#horizonFade)" filter="url(#glowWide)"/>
    <rect x="0" y="{MARK_HORIZON - 0.8}" width="{S}" height="1.6" fill="url(#horizonFade)"/>
    <path d="{trail}" stroke="{ORANGE}" stroke-width="12" fill="none" opacity="0.55" filter="url(#glowWide)"/>
    <path d="{trail}" stroke="{ORANGE}" stroke-width="5" fill="none"/>
    <path d="{trail}" stroke="#ffe2c2" stroke-width="1.5" fill="none"/>
    <path d="M {head_x} {lane_y - 8:.1f} L {head_x + 28} {lane_y - 3:.1f} L {head_x + 28} {lane_y + 3:.1f} L {head_x} {lane_y + 8:.1f} Z" fill="{ORANGE}" filter="url(#glow)"/>
    <path d="{mono}" stroke="{CYAN}" stroke-width="22" fill="none" stroke-linecap="square" opacity="0.7" filter="url(#glowWide)"/>
    <path d="{mono}" stroke="{CYAN}" stroke-width="13" fill="none" stroke-linecap="square"/>
    <path d="{mono}" stroke="{CORE}" stroke-width="4" fill="none" stroke-linecap="square"/>
    <rect width="{S}" height="{S}" fill="url(#scan)"/>
  </g>
  <path d="{panel}" stroke="{CYAN}" stroke-opacity="0.55" stroke-width="3" fill="none"/>
  <path d="{brackets}" stroke="{CYAN_SOFT}" stroke-width="4" fill="none" stroke-linecap="square" filter="url(#glow)"/>
</svg>
"""


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for name, build in (("spec-master-logo.svg", banner), ("spec-master-mark.svg", mark)):
        with open(os.path.join(here, name), "w", encoding="utf-8") as fh:
            fh.write(build())
        print(os.path.join(here, name))
