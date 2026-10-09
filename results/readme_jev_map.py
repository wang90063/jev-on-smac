"""Draw the 'Where Jev was tried' map for the README -> docs/jev_map.svg

    python results/readme_jev_map.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "docs" / "jev_map.svg"
W = 960
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
INK, MUTED, RULE = "#1f2328", "#59636e", "#d0d7de"
PANEL = "#f6f8fa"
CARD = "#ffffff"
NO, MEH = "#cf222e", "#9a6700"
JEV = "#8250df"

# n, question (2 lines), what Jev saw (1-2 lines), Jev's result, baselines [(name, value)], verdict, colour
BEFORE = [
    (1, ["Which library program should run this battle?", "once, at the start; 5 options"],
     ["Battle summary; per program: what it does, the fight", "it was written for, its record on fresh fights"],
     "Jev 295 / 600 wins",
     [("Nearest-cluster lookup (default)", "299"), ("Random pick, same 5 options", "273")],
     "beats random, not the default", NO),
    (2, ["Same pick, plus evidence", "Jev asked only when the evidence was unclear"],
     ["All of ① + each program's win/loss record vs", "attack-move in the 8 most similar training battles"],
     "Jev +1 net vs default",
     [("Evidence vote over the same records", "+1"), ("Jev and the vote differed on", "2 / 600")],
     "copies the evidence", NO),
    (3, ["Hold position or push?", "once, at the start, in today's system"],
     ["Unit stat cards + the 8 most similar other battles,", "each with its real hold and push results"],
     "Jev +6 net / 720",
     [("Evidence vote over the same 8 battles", "+5"), ("Best pick per battle in hindsight (ceiling)", "+25")],
     "= vote", NO),
]
DURING = [
    (4, ["How should each unit group fight right now?", "at decision steps; 3–5 options per question"],
     ["Battle state + the options + a manual saying which", "unit mixes each option suits"],
     "Jev 91 / 115 wins (in-sample)",
     [("Random answers to the same questions", "74"), ("Attack-move (default) / hand rules", "53 / 92")],
     "= hand rules", NO),
    (5, ["Which preset tactic for the next 5 steps?", "mid-battle, only where the value model is unsure"],
     ["Model's top 3 tactics + keep current; for each: what", "it does, model estimate, record in 20 similar moments"],
     "Jev 527 / 1,000 wins",
     [("Value model alone (default)", "523"), ("Random pick, same 4 options", "519")],
     "+4, p = 0.61", NO),
]
JUDGE = [
    (6, ["Will we win from here?", "yes / no at each recorded decision point"],
     ["Battle state + the 8 most similar training moments", "with their real outcomes"],
     "Jev AUC 0.874",
     [("Our HP ÷ their HP", "0.835"), ("Average outcome of the same 8", "0.77–0.80")],
     "best judge, not significant", MEH),
    (7, ["What is P(win) after each of 13 actions?", "then take the action with the highest"],
     ["Same as ⑥, plus how each of the 8 examples", "turned out under each of the 13 actions"],
     "Jev +0.1 (max 37.5)",
     [("Average of the same 8 examples", "+5.4"), ("Value model (default)", "+1.1")],
     "cannot tell actions apart", NO),
    (8, ["Switch only when Jev says we are losing", "rule tuned on 300 points, rerun on 300 fresh"],
     ["Same as ⑥; the vote proposes the switch,", "Jev's P(win) decides whether to take it"],
     "Jev +5.42 → +0.06",
     [("No gate: always take the vote's switch", "+2.13"), ("Gate on HP ratio instead", "+2.07")],
     "did not replicate", NO),
    (9, ["Two tactics: which one wins more here?", "one is ≥ 3 wins of 5 better, known from simulation"],
     ["Battle summary + what each of the two tactics does", ""],
     "Jev 45 / 73 correct",
     [("Random", "36.5"), ("Fixed rule: pick “keep attack-move” if offered", "46")],
     "= a fixed rule", NO),
]

CW, CH = 430, 168  # card size


def text(x, y, s, size=13, color=INK, weight=400, anchor="start", italic=False):
    st = ' font-style="italic"' if italic else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{st}>{escape(s)}</text>')


def card(x, y, item):
    n, q, saw, res, bases, verdict, vcol = item
    out = [f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" rx="8" fill="{CARD}" stroke="{RULE}"/>',
           f'<circle cx="{x + 20}" cy="{y + 22}" r="11" fill="{JEV}"/>',
           text(x + 20, y + 26.5, str(n), 12, "#fff", 700, "middle"),
           text(x + 40, y + 27, q[0], 13.5, INK, 600),
           text(x + 40, y + 45, q[1], 12, MUTED, 400, italic=True)]
    for i, line in enumerate(saw):
        if not line:
            continue
        if i == 0:
            out.append(f'<text x="{x + 40}" y="{y + 68}" font-size="12" fill="{MUTED}">'
                       f'<tspan font-weight="700" fill="{INK}">Jev saw: </tspan>{escape(line)}</text>')
        else:
            out.append(text(x + 40, y + 68 + 15 * i, line, 12, MUTED))
    out.append(f'<line x1="{x + 40}" y1="{y + 94}" x2="{x + CW - 14}" y2="{y + 94}" stroke="{RULE}"/>')
    out.append(text(x + 40, y + 116, res, 13.5, JEV, 700))
    cw = 10 + 6.9 * len(verdict)
    out.append(f'<rect x="{x + CW - cw - 14}" y="{y + 103}" width="{cw}" height="19" rx="9.5" '
               f'fill="{vcol}" fill-opacity="0.12" stroke="{vcol}" stroke-opacity="0.5"/>')
    out.append(text(x + CW - 14 - cw / 2, y + 116.5, verdict, 11.5, vcol, 600, "middle"))
    for i, (name, val) in enumerate(bases):
        yy = y + 139 + 18 * i
        out.append(text(x + 40, yy, name, 12.5, MUTED))
        out.append(text(x + CW - 14, yy, val, 12.5, INK, 700, "end"))
    return out


def main():
    g = []
    pad, gap = 24, 14
    colx = [pad + 16, pad + 16 + CW + 20]

    # ---- legend -------------------------------------------------------------------------
    ly = 22
    g.append(f'<circle cx="{pad + 8}" cy="{ly - 4}" r="5" fill="{JEV}"/>')
    g.append(text(pad + 19, ly, "Jev's result", 12.5, INK, 600))
    g.append(f'<rect x="{pad + 112}" y="{ly - 9}" width="10" height="10" rx="2" fill="{MUTED}"/>')
    g.append(text(pad + 128, ly, "Baselines given the same information, no Jev.  (default) = what the system did there without Jev.",
                  12.5, MUTED))

    # ---- panel A: choosing a tactic --------------------------------------------------
    ya = ly + 16
    ha = 74 + 3 * CH + 2 * gap + 18
    g.append(f'<rect x="{pad}" y="{ya}" width="{W - 2 * pad}" height="{ha}" rx="12" fill="{PANEL}" stroke="{RULE}"/>')
    g.append(text(pad + 16, ya + 28, "A.  Choosing a tactic", 17, INK, 700))
    g.append(text(pad + 210, ya + 28, "measured in real battles: wins, or net wins vs the default", 13, MUTED))
    ty = ya + 52
    g.append(f'<line x1="{colx[0]}" y1="{ty}" x2="{colx[1] + CW}" y2="{ty}" stroke="{MUTED}" stroke-width="1.5" marker-end="url(#arr)"/>')
    g.append(f'<circle cx="{colx[0]}" cy="{ty}" r="4" fill="{MUTED}"/>')
    g.append(text(colx[0] + 10, ty - 7, "BEFORE THE BATTLE", 11.5, MUTED, 700))
    g.append(f'<circle cx="{colx[1]}" cy="{ty}" r="4" fill="{MUTED}"/>')
    g.append(text(colx[1] + 10, ty - 7, "DURING THE BATTLE", 11.5, MUTED, 700))
    y0 = ty + 14
    for i, it in enumerate(BEFORE):
        g += card(colx[0], y0 + i * (CH + gap), it)
    for i, it in enumerate(DURING):
        g += card(colx[1], y0 + i * (CH + gap), it)
    tx, tyy = colx[1], y0 + 2 * (CH + gap)
    g.append(f'<rect x="{tx}" y="{tyy}" width="{CW}" height="{CH}" rx="8" fill="none" stroke="{RULE}" stroke-dasharray="4 4"/>')
    for i, line in enumerate(["Every time, a random pick, a lookup, a vote,",
                              "or hand rules with the same information",
                              "did about as well.",
                              "",
                              "The choices themselves were worth little:",
                              "even a perfect pick in ③ adds only +25 of 720."]):
        g.append(text(tx + 18, tyy + 34 + i * 19, line, 13, MUTED, 400, italic=True))

    # ---- panel B: judging the battle ----------------------------------------------------
    yb = ya + ha + 18
    gb = 30  # room for the ⑥ → ⑧ label
    hb = 64 + 2 * CH + gb + 18
    g.append(f'<rect x="{pad}" y="{yb}" width="{W - 2 * pad}" height="{hb}" rx="12" fill="{PANEL}" stroke="{RULE}"/>')
    g.append(text(pad + 16, yb + 28, "B.  Judging the battle", 17, INK, 700))
    g.append(text(pad + 210, yb + 28, "offline, no new battles: recorded decision points whose true outcomes", 13, MUTED))
    g.append(text(pad + 210, yb + 46, "were found by simulation.  ⑦ ⑧ score = true advantage gained, summed over points", 13, MUTED))
    y1 = yb + 64
    pos = {}
    for i, it in enumerate(JUDGE):
        x, y = colx[i % 2], y1 + (i // 2) * (CH + gb)
        g += card(x, y, it)
        pos[it[0]] = (x, y)
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
