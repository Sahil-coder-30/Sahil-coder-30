"""Render a GitHub contribution calendar as a looping "build drop" animation SVG.

Every day with contributions falls into its slot, week by week, until the year's
graph is built. A scan line then sweeps across it, the build is marked as passed,
and the loop starts again.

Usage: GITHUB_TOKEN=... python3 scripts/build_drop.py <username> <output.svg>
"""

import json
import os
import sys
import urllib.request

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel weekday } }
      }
    }
  }
}
"""

LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# Layout
WIDTH, HEIGHT = 880, 200
CELL, PITCH = 11, 14
TOP = 44

# Timeline, in seconds
LOOP = 11.0
DROP_START, WEEK_STEP, DAY_STEP = 0.4, 0.075, 0.018
FALL, SETTLE = 0.42, 0.22
SCAN_START, SCAN_END = 5.2, 6.8
FADE_START, FADE_END = 9.6, 10.2


def fetch_calendar(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": "build-drop-svg"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def pct(t):
    return f"{max(0.0, min(100.0, t / LOOP * 100)):.2f}%"


def cell_keyframes(name, start, fall_from):
    """Keyframes for one cell: hidden above, fall, small bounce, hold, fade out."""
    land = start + FALL
    return (
        f"@keyframes {name}{{"
        f"0%,{pct(start)}{{transform:translateY(-{fall_from}px);opacity:0;animation-timing-function:cubic-bezier(.55,0,1,.45)}}"
        f"{pct(start + 0.06)}{{opacity:1}}"
        f"{pct(land)}{{transform:translateY(0);animation-timing-function:ease-out}}"
        f"{pct(land + SETTLE / 2)}{{transform:translateY(-3px);animation-timing-function:ease-in}}"
        f"{pct(land + SETTLE)},{pct(FADE_START)}{{transform:translateY(0);opacity:1}}"
        f"{pct(FADE_END)},100%{{transform:translateY(0);opacity:0}}"
        "}"
    )


def render(calendar, login):
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    grid_w = len(weeks) * PITCH - (PITCH - CELL)
    left = (WIDTH - grid_w) / 2

    slots, cells, months = [], [], []
    last_month = None
    for w, week in enumerate(weeks):
        x = left + w * PITCH
        for day in week["contributionDays"]:
            y = TOP + day["weekday"] * PITCH
            slots.append((x, y))
            level = LEVELS.get(day["contributionLevel"], 0)
            if level:
                cells.append((x, y, level, w, day))
            month = day["date"][5:7]
            if day["weekday"] == 0 and month != last_month and int(day["date"][8:10]) <= 7 and w < len(weeks) - 2:
                last_month = month
                months.append((x, MONTHS[int(month) - 1]))

    build_done = DROP_START + len(weeks) * WEEK_STEP + 7 * DAY_STEP + FALL + SETTLE
    scan_from, scan_to = left - 30, left + grid_w + 30

    css = [
        ":root{--bg:#ffffff;--slot:#ebedf0;--l1:#9be9a8;--l2:#40c463;--l3:#30a14e;--l4:#216e39;"
        "--text:#57606a;--title:#1f2328;--scan:#2da44e;--ok:#1a7f37}",
        "@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--slot:#161b22;--l1:#0e4429;--l2:#006d32;"
        "--l3:#26a641;--l4:#39d353;--text:#8b949e;--title:#e6edf3;--scan:#39d353;--ok:#3fb950}}",
        ".bg{fill:var(--bg)}.slot{fill:var(--slot)}",
        ".l1{fill:var(--l1)}.l2{fill:var(--l2)}.l3{fill:var(--l3)}.l4{fill:var(--l4)}",
        ".c{opacity:0;animation-duration:%ss;animation-iteration-count:infinite;animation-fill-mode:both}" % LOOP,
        "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}",
        ".month{font-size:10px;fill:var(--text)}",
        ".status{font-size:12px;font-weight:600}",
        ".meta{font-size:12px;fill:var(--text)}",
        ".building{fill:var(--text);animation:building %ss infinite}" % LOOP,
        ".passed{fill:var(--ok);opacity:0;animation:passed %ss infinite}" % LOOP,
        ".scan{opacity:0;animation:scan %ss infinite linear}" % LOOP,
        # Status text swaps from "building" to "passed" once every cell has landed.
        f"@keyframes building{{0%,{pct(build_done - 0.2)}{{opacity:1}}{pct(build_done)},{pct(FADE_END)}{{opacity:0}}"
        f"{pct(FADE_END + 0.2)},100%{{opacity:1}}}}",
        f"@keyframes passed{{0%,{pct(build_done)}{{opacity:0}}{pct(build_done + 0.25)},{pct(FADE_START)}{{opacity:1}}"
        f"{pct(FADE_END)},100%{{opacity:0}}}}",
        f"@keyframes scan{{0%,{pct(SCAN_START)}{{transform:translateX({scan_from:.0f}px);opacity:0}}"
        f"{pct(SCAN_START + 0.15)}{{opacity:1}}{pct(SCAN_END - 0.15)}{{opacity:1}}"
        f"{pct(SCAN_END)},100%{{transform:translateX({scan_to:.0f}px);opacity:0}}}}",
        "@media (prefers-reduced-motion:reduce){.c,.building,.passed,.scan{animation:none}"
        ".c{opacity:1}.building{opacity:0}.passed{opacity:1}}",
    ]

    body = []
    for i, (x, y, level, w, day) in enumerate(cells):
        start = DROP_START + w * WEEK_STEP + day["weekday"] * DAY_STEP
        name = f"d{i}"
        css.append(cell_keyframes(name, start, int(y + CELL + 6)))
        count = day["contributionCount"]
        title = f'{count} contribution{"s" if count != 1 else ""} on {day["date"]}'
        body.append(
            f'<rect class="c l{level}" x="{x:.0f}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
            f'style="animation-name:{name}"><title>{title}</title></rect>'
        )

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="{login}: {total} contributions in the last year, built as an animation">',
        "<defs>",
        '<linearGradient id="scanGrad" x1="0" x2="1" y1="0" y2="0">'
        '<stop offset="0" stop-color="var(--scan)" stop-opacity="0"/>'
        '<stop offset=".85" stop-color="var(--scan)" stop-opacity=".25"/>'
        '<stop offset="1" stop-color="var(--scan)" stop-opacity=".9"/>'
        "</linearGradient>",
        "</defs>",
        "<style>" + "".join(css) + "</style>",
        f'<rect class="bg" width="{WIDTH}" height="{HEIGHT}" rx="10"/>',
    ]
    for x, name in months:
        out.append(f'<text class="month" x="{x:.0f}" y="{TOP - 10}">{name}</text>')
    for x, y in slots:
        out.append(f'<rect class="slot" x="{x:.0f}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>')
    out.extend(body)
    grid_h = 7 * PITCH - (PITCH - CELL)
    out.append(
        f'<g class="scan"><rect x="-60" y="{TOP - 6}" width="60" height="{grid_h + 12}" fill="url(#scanGrad)"/>'
        f'<rect x="-1" y="{TOP - 6}" width="2" height="{grid_h + 12}" rx="1" fill="var(--scan)"/></g>'
    )
    status_y = HEIGHT - 26
    out.append(f'<text class="status building" x="{left:.0f}" y="{status_y}">▸ building contribution graph…</text>')
    out.append(f'<text class="status passed" x="{left:.0f}" y="{status_y}">✓ build passed</text>')
    out.append(
        f'<text class="meta" x="{left + grid_w:.0f}" y="{status_y}" text-anchor="end">'
        f"{total} contributions in the last year</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    login, path = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is not set")
    svg = render(fetch_calendar(login, token), login)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
