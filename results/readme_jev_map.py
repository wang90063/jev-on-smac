"""Draw the 'Where Jev was tried' map for the README -> report/jev_map.svg

    python results/readme_jev_map.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "report" / "jev_map.svg"
W = 960
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
INK, MUTED, RULE = "#1f2328", "#59636e", "#d0d7de"
PANEL_A, PANEL_B = "#f6f8fa", "#f6f8fa"
CARD = "#ffffff"
NO, MEH, BEST = "#cf222e", "#9a6700", "#1a7f37"
JEV = "#8250df"

# (number, question lines, result line, control line, verdict, verdict colour)
BEFORE = [
    (1, ["Which program from the tactic library", "suits this battle?"],
     "Jev 295 / 600 wins", "Lookup of most similar battles: 299 / 600", "no better", NO),
    (2, ["Same, plus each program's record", "in the 8 most similar past battles"],
     "Jev +1 net", "Majority vote over those records: +1", "copies the evidence", NO),
    (3, ["Hold position or push?", "(current system, 8 similar battles shown)"],
     "Jev +6 net / 720", "Majority vote of the same 8: +5", "= vote", NO),
]
DURING = [
    (4, ["Every step: how should each unit group", "fight? attack-move / kite / hold / fall back"],
     "Jev 77 / 115 wins", "Random answers: 74 / 115", "≈ random", NO),
    (5, ["Every 5 steps, only when the value model", "is unsure: which preset tactic next?"],
     "Jev +4 net / 1,000 (p = 0.61)", "Random pick: −4", "not significant", NO),
]
JUDGE = [
    (6, ["Will we win from here?", "(8 similar examples shown)"],
     "Jev AUC 0.874", "HP ratio: AUC 0.835", "best judge, not significant", MEH),
    (7, ["What is P(win) after each", "of these 13 actions?"],
     "Jev rank corr. 0.054", "Our value model: 0.305", "cannot tell actions apart", NO),
    (8, ["Switch tactics only when Jev", "says we are losing (uses ⑥)"],
     "Jev +5.42 → +0.06 on fresh data", "Always switch on similar-battle advice: +2.13", "did not replicate", NO),
    (9, ["Sanity check: one of two programs is", "clearly better here. Which one?"],
     "Jev 45 / 73 correct", "“Pick the option that changes nothing”: 46 / 73", "no discrimination", NO),
]

CW, CH = 430, 118  # card size


def text(x, y, s, size=13, color=INK, weight=400, anchor="start", italic=False):
    st = ' font-style="italic"' if italic else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{st}>{escape(s)}</text>')


def card(x, y, item):
    n, q, res, ctl, verdict, vcol = item
    out = [f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" rx="8" fill="{CARD}" stroke="{RULE}"/>',
           f'<circle cx="{x + 20}" cy="{y + 22}" r="11" fill="{JEV}"/>',
           text(x + 20, y + 26.5, str(n), 12, "#fff", 700, "middle")]
    for i, line in enumerate(q):
        out.append(text(x + 40, y + 27 + i * 18, line, 13.5, INK, 600 if i == 0 else 400))
    out.append(text(x + 40, y + 71, res, 13, JEV, 600))
    out.append(text(x + 40, y + 90, ctl, 12.5, MUTED))
    # verdict chip, bottom right
    cw = 9 + 6.9 * len(verdict)
    out.append(f'<rect x="{x + CW - cw - 12}" y="{y + CH - 26}" width="{cw}" height="18" rx="9" '
               f'fill="{vcol}" fill-opacity="0.12" stroke="{vcol}" stroke-opacity="0.5"/>')
    out.append(text(x + CW - 12 - cw / 2, y + CH - 13, verdict, 11.5, vcol, 600, "middle"))
    return out, (x, y)


def main():
    g = []
    pad, gap = 24, 14
    colx = [pad + 16, pad + 16 + CW + 20]

    # ---- panel A: choosing a tactic --------------------------------------------------
    ya = 20
    ha = 74 + 3 * CH + 2 * gap + 18
    g.append(f'<rect x="{pad}" y="{ya}" width="{W - 2 * pad}" height="{ha}" rx="12" fill="{PANEL_A}" stroke="{RULE}"/>')
    g.append(text(pad + 16, ya + 28, "A.  Choosing a tactic", 17, INK, 700))
    g.append(text(pad + 210, ya + 28, "measured in real battles: wins, or net wins vs the default", 13, MUTED))
    # timeline
    ty = ya + 52
    g.append(f'<line x1="{colx[0]}" y1="{ty}" x2="{colx[1] + CW}" y2="{ty}" stroke="{MUTED}" stroke-width="1.5" marker-end="url(#arr)"/>')
    g.append(f'<circle cx="{colx[0]}" cy="{ty}" r="4" fill="{MUTED}"/>')
    g.append(text(colx[0] + 10, ty - 7, "BEFORE THE BATTLE", 11.5, MUTED, 700))
    g.append(f'<circle cx="{colx[1]}" cy="{ty}" r="4" fill="{MUTED}"/>')
    g.append(text(colx[1] + 10, ty - 7, "DURING THE BATTLE", 11.5, MUTED, 700))
    y0 = ty + 14
    for i, it in enumerate(BEFORE):
        g += card(colx[0], y0 + i * (CH + gap), it)[0]
    for i, it in enumerate(DURING):
        g += card(colx[1], y0 + i * (CH + gap), it)[0]
    # takeaway in the empty slot under panel A's right column
    tx, tyy = colx[1], y0 + 2 * (CH + gap)
    g.append(f'<rect x="{tx}" y="{tyy}" width="{CW}" height="{CH}" rx="8" fill="none" stroke="{RULE}" stroke-dasharray="4 4"/>')
    for i, line in enumerate(["Wherever Jev chose, a random pick, a lookup,",
                              "or a plain vote over the same information",
                              "did about as well. The best possible pick was",
                              "itself small: +25 of 720 battles for ③."]):
        g.append(text(tx + 18, tyy + 30 + i * 19, line, 13, MUTED, 400, italic=True))

    # ---- panel B: judging the battle ----------------------------------------------------
    yb = ya + ha + 18
    gb = 30  # room for the ⑥ → ⑧ label
    hb = 46 + 2 * CH + gb + 18
    g.append(f'<rect x="{pad}" y="{yb}" width="{W - 2 * pad}" height="{hb}" rx="12" fill="{PANEL_B}" stroke="{RULE}"/>')
    g.append(text(pad + 16, yb + 28, "B.  Judging the battle", 17, INK, 700))
    g.append(text(pad + 210, yb + 28, "measured offline on recorded decision points, no battles played", 13, MUTED))
    y1 = yb + 46
    pos = {}
    for i, it in enumerate(JUDGE):
        x, y = colx[i % 2], y1 + (i // 2) * (CH + gb)
        g += card(x, y, it)[0]
        pos[it[0]] = (x, y)
    # arrow ⑥ -> ⑧ : a good judgment did not become a good action
    x6, y6 = pos[6]
    x8, y8 = pos[8]
    ax = x6 + 64
    g.append(f'<path d="M {ax} {y6 + CH} L {ax} {y8}" stroke="{JEV}" stroke-width="2" fill="none" marker-end="url(#arrj)"/>')
    g.append(text(ax + 10, y6 + CH + gb / 2 + 4.5, "judging well ≠ acting well", 11.5, JEV, 700))

    H = yb + hb + 20
    defs = (f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker>'
            f'<marker id="arrj" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{JEV}"/></marker></defs>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="{FONT}">\n{defs}\n<rect width="{W}" height="{H}" fill="#ffffff"/>\n' + "\n".join(g) + "\n</svg>\n")
    OUT.write_text(svg)
    print(OUT, W, H)


if __name__ == "__main__":
    main()
