"""
app.py
Kairos: a self-inquiry tool built on the Knowledge Quadrant Framework.

You describe your day. Claude (Anthropic's AI) reads it through the framework and
shows you where your work sits: which parts are yours, and which a tool could take.
Kairos does not save what you write.

Run:  streamlit run app.py
"""

import datetime as dt
import html
import os
import random
import string
import urllib.parse

import streamlit as st

import analyzer
import emailer
import framework as fw

SITE = "https://puneetsrivastava.com"

st.set_page_config(
    page_title="Kairos · Know where you stand",
    page_icon="kairos-icon.png",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------- state
ss = st.session_state
if "theme" not in ss:
    qp = st.query_params.get("theme", "")
    ss["theme"] = "night" if qp in ("night", "dark") else "day"
if "stage" not in ss:
    ss["stage"] = "intro"
if "session_token" not in ss:
    ss["session_token"] = "KQ-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
if "mode" not in ss:
    ss["mode"] = "guided"
if "nonce" not in ss:
    ss["nonce"] = 0


def wkey(k: str) -> str:
    """Widget keys change each time the writing page is re-entered, so answers restore cleanly."""
    return f"{k}_{ss['nonce']}"


def answer(k: str) -> str:
    return ss.get(wkey(k), ss.get("_keep_" + k, "")) or ""


def go_write():
    ss["nonce"] += 1
    ss["stage"] = "write"
token = ss["session_token"]

# --------------------------------------------------------------------------- theme
PALETTES = {
    "day": dict(
        bg="#f7f4ee", surface="#ffffff", surface2="#f3efe7", line="#e3ddd1", line2="#cfc7b8",
        text="#1c1b19", body="#34322e", muted="#5b574f", faint="#6f6a61",
        accent="#8a6a1c", accent_hover="#6f5412", on_accent="#ffffff",
        wash="rgba(138,106,28,0.10)", wash2="rgba(138,106,28,0.22)",
        shadow="0 1px 2px rgba(28,27,25,.04), 0 6px 20px rgba(28,27,25,.05)",
    ),
    "night": dict(
        bg="#1c1d20", surface="#242529", surface2="#2a2b2f", line="#34353a", line2="#4a4a4f",
        text="#eeeae3", body="#d9d5cd", muted="#b0aba1", faint="#938e84",
        accent="#d4b466", accent_hover="#e6c983", on_accent="#1c1d20",
        wash="rgba(212,180,102,0.10)", wash2="rgba(212,180,102,0.24)",
        shadow="none",
    ),
}
P = PALETTES[ss["theme"]]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap');
:root {
  --bg:%(bg)s; --surface:%(surface)s; --surface2:%(surface2)s; --line:%(line)s; --line2:%(line2)s;
  --text:%(text)s; --body:%(body)s; --muted:%(muted)s; --faint:%(faint)s;
  --accent:%(accent)s; --accent-hover:%(accent_hover)s; --on-accent:%(on_accent)s;
  --wash:%(wash)s; --wash2:%(wash2)s; --shadow:%(shadow)s;
  --serif:'Source Serif 4', Georgia, serif; --sans:'Inter', system-ui, -apple-system, sans-serif;
}
/* hide Streamlit chrome */
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer, .stDeployButton { display:none !important; }
html, body, .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: var(--bg) !important; color: var(--body); font-family: var(--sans);
}
[data-testid="stMainBlockContainer"], .block-container { max-width: 760px; padding-top: 1.4rem; padding-bottom: 4rem; }
:where(.stApp) p, :where(.stApp) li { color: var(--body); font-family: var(--sans); font-size: 1.02rem; line-height: 1.7; }
:where(.stApp) h1, :where(.stApp) h2, :where(.stApp) h3, :where(.stApp) h4 { font-family: var(--serif); color: var(--text); font-weight: 600; letter-spacing: -0.01em; }
a { color: var(--accent) !important; }

/* buttons */
.stButton button, [data-testid="stDownloadButton"] button, [data-testid="stLinkButton"] a {
  font-family: var(--sans); font-weight: 600; border-radius: 8px; min-height: 44px;
  background: transparent; color: var(--text) !important; border: 1px solid var(--line2);
}
.stButton button:hover, [data-testid="stDownloadButton"] button:hover, [data-testid="stLinkButton"] a:hover {
  border-color: var(--accent); color: var(--accent) !important; background: transparent;
}
.stButton button[kind="primary"], [data-testid="stBaseButton-primary"] {
  background: var(--accent) !important; color: var(--on-accent) !important; border: 1px solid var(--accent) !important;
  font-size: 1rem; padding: 0.55rem 1.4rem;
}
.stButton button[kind="primary"]:hover { background: var(--accent-hover) !important; color: var(--on-accent) !important; }
.stButton button p, [data-testid="stDownloadButton"] button p { color: inherit !important; font-size: inherit; }

/* inputs */
.stTextArea textarea, .stTextInput input {
  background: var(--surface) !important; color: var(--text) !important; caret-color: var(--accent);
  border-radius: 10px !important; font-family: var(--sans); font-size: 1.02rem; line-height: 1.6;
}
.stTextArea [data-baseweb="textarea"], .stTextInput [data-baseweb="input"] {
  background: var(--surface) !important; border: 1px solid var(--line2) !important; border-radius: 10px !important;
}
.stTextArea [data-baseweb="textarea"]:focus-within { border-color: var(--accent) !important; box-shadow: 0 0 0 3px var(--wash) !important; }
.stTextArea textarea::placeholder { color: var(--faint) !important; opacity: 1; }
.stTextArea label, .stTextInput label, .stRadio label, [data-testid="stWidgetLabel"] p { color: var(--text) !important; }
[data-testid="stTextAreaRootElement"] + div, .stTextArea [data-testid="InputInstructions"] { display: none; }
.stRadio [role="radiogroup"] label p { color: var(--body) !important; }
[data-testid="stToggle"] label p { color: var(--muted) !important; font-size: .92rem; }
[data-testid="stExpander"] details { background: var(--surface); border: 1px solid var(--line) !important; border-radius: 10px; }
[data-testid="stExpander"] summary p { color: var(--text) !important; font-weight: 500; }
[data-testid="stAlert"] { border-radius: 10px; }
[data-testid="stSpinner"] p, .stSpinner p { color: var(--muted) !important; }

.st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px; }
.st-key-topbar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }
.st-key-topbar [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; }
.st-key-topbar button { min-height: 38px; padding: 0 14px; }
[data-testid="stTextInputRootElement"] { border: 1px solid var(--line2) !important; border-radius: 10px !important; background: var(--surface) !important; }
/* custom blocks */
.k-top { display:flex; align-items:center; gap:10px; padding: 4px 0; }
.k-top .mark svg { width: 30px; height: 30px; display:block; }
.k-top .word { font-family: var(--serif); font-weight: 600; font-size: 1.25rem; color: var(--text); }
.k-top .by { font-size: .85rem; color: var(--faint); }
.k-top .by a { color: var(--muted) !important; text-decoration: none; }
.k-steps { display:flex; gap: 18px; margin: 10px 0 6px; font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; color: var(--faint); font-weight: 600; }
.k-steps .on { color: var(--accent); }
.k-eyebrow { font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; color: var(--accent); font-weight: 600; margin: 0 0 6px; }
.k-hero { text-align: center; padding: 28px 0 8px; }
.k-hero .mark svg { width: 84px; height: 84px; }
.k-hero h1 { font-size: clamp(2.6rem, 8vw, 3.6rem); margin: 10px 0 6px; padding: 0; }
.k-hero .lede { font-family: var(--serif); font-size: 1.35rem; color: var(--text); line-height: 1.4; margin: 0 auto 8px; max-width: 540px; }
.k-hero .sub { color: var(--muted); max-width: 520px; margin: 0 auto; }
.k-card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 24px 26px; margin: 14px 0; box-shadow: var(--shadow); }
.k-card h3 { font-size: 1.35rem; margin: 0 0 8px; padding: 0; }
.k-quote { font-family: var(--serif); font-style: italic; font-size: 1.25rem; line-height: 1.5; color: var(--accent); margin: 0 0 12px; }
.k-src { font-size: .85rem; color: var(--faint); margin-top: 10px; }
.k-steps3 { display:grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin: 16px 0 6px; }
.k-steps3 div { background: var(--surface2); border-radius: 12px; padding: 16px; }
.k-steps3 b { display:block; font-family: var(--serif); color: var(--text); font-size: 1.1rem; margin-bottom: 4px; }
.k-steps3 span { color: var(--muted); font-size: .93rem; line-height: 1.5; display:block; }
.k-trust { text-align:center; color: var(--faint); font-size: .88rem; margin-top: 10px; }
.k-q { font-family: var(--serif); font-size: 1.22rem; color: var(--text); margin: 22px 0 2px; line-height: 1.35; }
.k-q small { font-family: var(--sans); font-size: .82rem; color: var(--faint); margin-left: 6px; font-weight: 400; }
.k-hint { color: var(--muted); font-size: .92rem; margin: 0 0 6px; }
.k-meter { margin: 18px 0 8px; }
.k-meter .bar { height: 6px; background: var(--line); border-radius: 4px; overflow: hidden; }
.k-meter .fill { height: 100%%; background: var(--accent); border-radius: 4px; }
.k-meter .lbl { font-size: .88rem; color: var(--muted); margin-top: 6px; }
.k-ideas { columns: 2; gap: 20px; padding-left: 18px; margin: 4px 0 10px; }
.k-ideas li { color: var(--muted); font-size: .95rem; margin-bottom: 4px; break-inside: avoid; }

.k-persona { text-align: center; padding: 30px 26px; }
.k-persona .pre { color: var(--muted); font-size: .95rem; margin: 0; }
.k-persona h2 { font-size: clamp(2rem, 6vw, 2.6rem); margin: 4px 0 12px; padding: 0; }
.k-pill { display:inline-block; padding: 4px 14px; border-radius: 20px; font-size: .82rem; font-weight: 600; color: #fff; }
.k-persona .desc { font-size: 1.08rem; color: var(--body); max-width: 520px; margin: 14px auto 6px; }
.k-persona .note { font-size: .85rem; color: var(--faint); margin: 0; }
.k-ladder { margin: 22px auto 4px; max-width: 520px; }
.k-ladder .dots { display:flex; justify-content: space-between; align-items:center; position: relative; }
.k-ladder .dots:before { content:''; position:absolute; left:6px; right:6px; top:50%%; height:2px; background: var(--line); }
.k-ladder .dot { width: 12px; height: 12px; border-radius: 50%%; background: var(--line2); position: relative; z-index: 1; }
.k-ladder .dot.on { width: 20px; height: 20px; background: var(--accent); box-shadow: 0 0 0 5px var(--wash2); }
.k-ladder .ends { display:flex; justify-content: space-between; font-size: .76rem; color: var(--faint); margin-top: 8px; text-transform: uppercase; letter-spacing: .08em; }

.k-grid { display:grid; grid-template-columns: 26px 1fr 1fr; gap: 8px; margin-top: 10px; }
.k-grid .ax { font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--faint); font-weight: 600; text-align:center; align-self: end; }
.k-grid .ay { writing-mode: vertical-rl; transform: rotate(180deg); font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--faint); font-weight: 600; text-align:center; align-self: center; justify-self: center; }
.k-cell { border-radius: 12px; padding: 16px; border: 1px solid var(--line); min-height: 108px; }
.k-cell.top { border: 2px solid var(--accent); }
.k-cell .pct { font-family: var(--serif); font-size: 2rem; font-weight: 600; color: var(--text); line-height: 1; }
.k-cell .nm { font-weight: 600; color: var(--text); font-size: .95rem; margin-top: 6px; }
.k-cell .ax2 { font-size: .8rem; color: var(--muted); }
.k-insight { font-family: var(--serif); font-size: 1.2rem; line-height: 1.55; color: var(--text); margin: 0; }
.k-two { display:grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.k-two h4 { font-size: 1.05rem; margin: 0 0 6px; }
.k-two ul { margin: 0; padding-left: 18px; }
.k-two li { color: var(--body); font-size: .98rem; }
.k-sig li { margin-bottom: 10px; }
.k-sig .ph { color: var(--text); font-weight: 500; }
.k-sig .why { color: var(--muted); font-size: .93rem; display:block; }
.k-ask { background: var(--wash); border: 1px solid var(--wash2); }
.k-ask .big { font-family: var(--serif); font-size: 1.35rem; line-height: 1.45; color: var(--text); margin: 0 0 14px; }
.k-ask ol { margin: 0; padding-left: 20px; }
.k-ask li { color: var(--body); margin-bottom: 8px; }
.k-care { background: var(--surface2); border-left: 4px solid var(--accent); }
.k-foot { text-align:center; color: var(--faint); font-size: .85rem; margin-top: 36px; }
.k-foot a { color: var(--muted) !important; }
@media (max-width: 640px) {
  .k-top .by { display: none; }
  .k-steps3, .k-two { grid-template-columns: 1fr; }
  .k-ideas { columns: 1; }
  .k-card { padding: 20px 18px; }
}
</style>
""" % P
st.markdown(CSS, unsafe_allow_html=True)

MARK = """<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="14.25" fill="none" stroke="var(--accent)" stroke-width="1.5"/><path d="M6.1 6.1 L25.9 25.9 A14 14 0 0 1 6.1 6.1 Z" fill="var(--text)"/><circle cx="16" cy="11.2" r="1.1" fill="var(--accent)"/><path d="M15.2 12.7 h1.6 v3.3 h-1.6 z" fill="var(--accent)"/></svg>"""

# Quoted verbatim from puneetsrivastava.com (#framework). Keep in sync with the homepage.
HOME_QUOTE = ("The question nobody is asking clearly enough is not whether AI will take your job. "
              "It is which part of what you do is actually yours.")
HOME_DEF = ("The framework maps how people create value at work, and how exposed that value is to AI. "
            "Two axes. <b>Knowledge</b>: explicit knowledge is documented and searchable, the kind AI "
            "replicates at scale; tacit knowledge is judgment earned by living through real situations. "
            "<b>Output</b>: accuracy means there is a right answer and being wrong costs something; "
            "originality means there is no right answer, only a fresh one.")

RISK_COLORS = {
    "Critical": "#b03a2e", "High": "#c8661b", "Medium-High": "#a97c00", "Medium": "#6d7275",
    "Medium-Low": "#13806c", "Low": "#2f8a4c", "Very Low": "#2a6aa0", "Minimal": "#5b3a8d",
}
QUAD_ORDER = ["doctor", "builder", "general", "creator"]

GUIDED = [
    ("g0", "Walk through your day. What did you actually spend your time on?",
     "Meetings, analysis, emails, a hard conversation, a document you wrote... any order is fine.", True, 150),
    ("g1", "What decision did only you make today?",
     "Big or small. Something that needed your judgment, not just your time.", False, 100),
    ("g2", "What felt mechanical, something a tool could have done?",
     "Reports, updates, copying, chasing, formatting...", False, 100),
    ("g3", "What gave you energy today, and what drained it?",
     "Be honest. This is only for you.", False, 100),
]

PROBE_QUESTIONS = {
    "The Doer": [
        "Was there a moment today where you decided something, or did you mostly execute what was already decided?",
        "If you hadn't shown up today, which of those tasks would have still gotten done?",
        "What's the one thing from today that only you could have done?",
    ],
    "The Responder": [
        "Of all the decisions you made today, how many were yours versus escalated to you by someone else's urgency?",
        "Did anything today make you think differently, or was it mostly familiar territory?",
        "What would have to change for tomorrow to feel less reactive?",
    ],
    "The Craftsman": [
        "When you fixed that issue today, did you follow a known process or figure something out fresh?",
        "Is your technical depth visible to the people who make decisions about your future?",
        "What would you build if someone gave you a week with no tickets and no requests?",
    ],
    "The Utility Player": [
        "Do people come to you because of a specific skill, or because you're reliable across many things?",
        "What's the thing you do that no one else on your team can do?",
        "Are you being stretched today, or just spread thin?",
    ],
    "The Architect": [
        "The system you're designing: who owns it after you hand it off?",
        "What breaks first if you step away for two weeks?",
        "Do the people you're aligning today understand why the structure matters, or just that it does?",
    ],
    "The Strategist": [
        "The call you made today: could you explain the reasoning to someone junior in a way that teaches them to make it themselves next time?",
        "Is your judgment being used at the right altitude, or are you solving problems a level below where you should be operating?",
        "What are you the last line of defense for?",
    ],
    "The Visionary": [
        "The idea you're sitting with: does anyone else in your organization see it yet?",
        "What would have to be true for that thinking to become a decision in the next 90 days?",
        "Who do you have these kinds of conversations with regularly?",
    ],
    "The Oracle": [
        "When you shared that perspective today, was it heard as insight or as opinion?",
        "How much of what you know is written down somewhere accessible to others?",
        "Are you building something that carries your thinking forward, or is it still mostly in your head?",
    ],
}
_QUAD_PROBE_PRIORITY = ["creator", "general", "builder", "doctor"]
_QUAD_PERSONAS = {
    "doctor": ["The Doer", "The Responder"],
    "builder": ["The Craftsman", "The Architect"],
    "general": ["The Strategist"],
    "creator": ["The Visionary", "The Oracle"],
}


def _pick_probe_questions(blend, dominant_persona):
    """Return up to 2 probe questions driven by the lowest-weighted quadrants."""
    priority = _QUAD_PROBE_PRIORITY
    zero_quads = [q for q in priority if blend.get(q, 0) == 0]
    non_zero = sorted([(q, blend[q]) for q in priority if blend.get(q, 0) > 0],
                      key=lambda x: (x[1], priority.index(x[0])))
    if len(zero_quads) >= 2:
        probe_quads = zero_quads[:2]
    elif len(zero_quads) == 1:
        probe_quads = [zero_quads[0], non_zero[0][0]] if non_zero else zero_quads[:1]
    else:
        probe_quads = [non_zero[0][0], non_zero[1][0]] if len(non_zero) >= 2 else [non_zero[0][0]]
    questions, used = [], []
    for quad in probe_quads:
        candidates = _QUAD_PERSONAS.get(quad, [])
        key = dominant_persona if dominant_persona in candidates else next(
            (p for p in candidates if p not in used), candidates[0] if candidates else None)
        if not key:
            continue
        used.append(key)
        q_list = PROBE_QUESTIONS.get(key, [])
        idx = min(used[:-1].count(key), len(q_list) - 1)
        if q_list:
            questions.append(q_list[idx])
    return questions


def build_summary_text(result, token="") -> str:
    p = fw.persona_by_name(result["dominant_persona"])
    risk = p["risk"] if p else "unknown"
    lines = ["KAIROS: your day, read back", "",
             f"Date: {dt.date.today().isoformat()}", f"Reference: {token}",
             f"You read mostly as: {result['dominant_persona']} ({risk} displacement risk)"]
    if p:
        lines.append(p["desc"])
    lines += ["", "Quadrant blend:"]
    for k in QUAD_ORDER:
        lines.append(f"  {fw.QUADRANTS[k]['label']:<14} {result['quadrant_blend'][k]:>3}%")
    lines.append("")
    if result.get("insight"):
        lines += ["What your words reveal:", "  " + result["insight"], ""]
    if result.get("displacement_signals"):
        lines.append("Tasks a tool could handle:")
        for s in result["displacement_signals"]:
            lines.append(f"  - \"{s.get('phrase', '')}\": {s.get('why', '')}")
        lines.append("")
    if result.get("energizing"):
        lines.append("Energized you: " + "; ".join(result["energizing"]))
    if result.get("draining"):
        lines.append("Drained you: " + "; ".join(result["draining"]))
    if result.get("honest_question"):
        lines += ["", "A question to sit with:", "  " + result["honest_question"]]
    lines += ["", "Kairos | Built on the Knowledge Quadrant Framework by Puneet Srivastava",
              f"{SITE}/#framework"]
    return "\n".join(lines)


def esc(x) -> str:
    return html.escape(str(x or ""))


def md(block: str):
    # Strip indentation and blank lines so Markdown never turns HTML into a code block.
    st.markdown("\n".join(l.strip() for l in block.splitlines() if l.strip()), unsafe_allow_html=True)


def words_in(text: str) -> int:
    return len(text.split()) if text and text.strip() else 0


def compose_transcript() -> str:
    if ss["mode"] == "free":
        return answer("free_text").strip()
    parts = []
    for key, q, _hint, _req, _h in GUIDED:
        ans = answer(key).strip()
        if ans:
            parts.append(f"{q}\n{ans}")
    return "\n\n".join(parts)


def validate(text: str):
    words = text.split()
    if len(words) < 40:
        return False, (f"Just a little more. You've written {len(words)} words so far; about forty is enough. "
                       "No need to organize it.")
    if len(set(w.lower() for w in words)) / len(words) < 0.30:
        return False, "Looks like something got repeated. Just write naturally about your day."
    if sum(1 for c in text if ord(c) < 128) / len(text) < 0.90:
        return False, "Kairos currently reads English best. Write however you normally think; no need to be formal."
    return True, ""


def reset():
    for k in list(ss.keys()):
        if k not in ("theme", "session_token"):
            del ss[k]
    ss["mode"] = "guided"
    ss["nonce"] = 0
    go_write()


# --------------------------------------------------------------------------- top bar
topbar = st.container(key="topbar")
c1, c2 = topbar.columns([5, 1], vertical_alignment="center")
with c1:
    md(f"""<div class="k-top"><span class="mark">{MARK}</span><span class="word">Kairos</span>
    <span class="by">by <a href="{SITE}" target="_blank">Puneet Srivastava</a></span></div>""")
with c2:
    night = ss["theme"] == "night"
    if st.button("☀︎ Day" if night else "☾ Night", key="theme_btn", use_container_width=True,
                 help="Switch between day and night"):
        ss["theme"] = "day" if night else "night"
        st.rerun()

stage = ss["stage"]

# --------------------------------------------------------------------------- intro
if stage == "intro":
    md(f"""<div class="k-hero"><span class="mark">{MARK}</span>
    <h1>Kairos</h1>
    <p class="lede">A few honest minutes about your workday. See which part of it is truly yours.</p>
    <p class="sub">Kairos reads a plain description of your day through the Knowledge Quadrant Framework
    and shows you where your work stands as AI gets better at the rest.</p></div>""")

    md(f"""<div class="k-card"><div class="k-eyebrow">The Knowledge Quadrant Framework</div>
    <p class="k-quote">&ldquo;{HOME_QUOTE}&rdquo;</p>
    <p>{HOME_DEF}</p>
    <div class="k-src">From <a href="{SITE}/#framework" target="_blank">puneetsrivastava.com</a></div></div>""")

    md("""<div class="k-steps3">
    <div><b>1. Describe</b><span>Answer four short questions about today, in your own words.</span></div>
    <div><b>2. Read</b><span>Claude maps your day onto the four quadrants and eight personas.</span></div>
    <div><b>3. Reflect</b><span>Get an honest picture and one question to sit with.</span></div></div>""")

    b1, b2, b3 = st.columns([1, 2, 1])
    with b2:
        if st.button("Begin", type="primary", use_container_width=True):
            go_write()
            st.rerun()
    md("""<p class="k-trust">No login. About five minutes. Kairos does not save what you write.<br>
    Your answers are sent to Claude (Anthropic's AI) only to produce your read.</p>""")

# --------------------------------------------------------------------------- write
elif stage == "write":
    md("""<div class="k-steps"><span class="on">1 · Describe your day</span><span>2 · Your read</span></div>""")
    md("""<h2 style="margin:4px 0 4px">Tell me about today</h2>
    <p class="k-hint">Write the way you would talk to a friend. Short answers are fine; the first question matters most.
    One ordinary day is enough.</p>""")

    free = st.toggle("I'd rather write it all in one go", value=(ss["mode"] == "free"), key="free_toggle")
    ss["mode"] = "free" if free else "guided"

    if ss["mode"] == "guided":
        for key, q, hint, req, h in GUIDED:
            md(f"""<p class="k-q">{esc(q)}{'' if req else '<small>optional</small>'}</p>""")
            st.text_area(q, key=wkey(key), value=ss.get("_keep_" + key, ""), height=h,
                         placeholder=hint, label_visibility="collapsed")
    else:
        md("""<p class="k-q">Your day, in your own words</p>
        <p class="k-hint">If you get stuck, these help:</p>
        <ul class="k-ideas">
        <li>What did you actually spend your time on?</li>
        <li>What decision did only you make?</li>
        <li>What felt mechanical, something a tool could have done?</li>
        <li>When did you feel most irreplaceable?</li>
        <li>What would have broken if you weren't there?</li>
        <li>What gave you energy, and what drained it?</li></ul>""")
        st.text_area("Your day", key=wkey("free_text"), value=ss.get("_keep_free_text", ""), height=300,
                     label_visibility="collapsed",
                     placeholder="Start anywhere. There is no wrong way to begin.")

    for _k in [g[0] for g in GUIDED] + ["free_text"]:
        if wkey(_k) in ss:
            ss["_keep_" + _k] = ss[wkey(_k)]
    text = compose_transcript()
    answers = (answer("free_text") if ss["mode"] == "free"
               else " ".join(answer(g[0]) for g in GUIDED)).strip()
    n = words_in(answers)
    pct = min(100, int(n / 60 * 100))
    label = ("Start with the first question." if n == 0 else
             f"{n} words · keep going, about forty is enough" if n < 40 else
             f"{n} words · plenty for a good read" if n < 150 else
             f"{n} words · rich detail, ready when you are")
    md(f"""<div class="k-meter"><div class="bar"><div class="fill" style="width:{pct}%"></div></div>
    <div class="lbl">{label} <span style="opacity:.7">(updates when you click outside a box)</span></div></div>""")

    a1, a2 = st.columns([2, 1])
    with a1:
        go = st.button("Read my day", type="primary", use_container_width=True)
    with a2:
        if st.button("Back", use_container_width=True):
            ss["stage"] = "intro"
            st.rerun()
    md("""<p class="k-trust" style="text-align:left">Kairos does not save what you write.
    Your text goes to Claude (Anthropic's AI) only to produce your read.</p>""")

    if go:
        ok, msg = validate(answers)
        if not ok:
            st.warning(msg)
        else:
            with st.spinner("Reading your day through the four quadrants. This takes about ten seconds..."):
                ss["result"] = analyzer.analyze(text)
            ss["stage"] = "result"
            st.rerun()

# --------------------------------------------------------------------------- result
elif stage == "result":
    result = ss["result"]
    md("""<div class="k-steps"><span>1 · Describe your day</span><span class="on">2 · Your read</span></div>""")

    if result.get("_fallback"):
        md("""<div class="k-card"><h3>Kairos couldn't read your day just now</h3>
        <p>Something went wrong on our side, not yours. Your words are still here: go back and try again in a minute.</p></div>""")
        with st.expander("Technical detail"):
            st.code(str(result.get("insight", "")))
        if st.button("Go back and try again", type="primary"):
            go_write()
            st.rerun()
        st.stop()

    if result.get("_wellbeing"):
        md("""<div class="k-card k-care"><h3>Before anything else</h3>
        <p>Some of what you wrote sounds heavy. If you are struggling, you don't have to carry it alone.
        Talking to someone you trust can help, and if you are in the US you can call or text <b>988</b> any time
        to reach the Suicide &amp; Crisis Lifeline. Outside the US, local helplines are listed at
        <a href="https://findahelpline.com" target="_blank">findahelpline.com</a>.</p></div>""")

    name = result["dominant_persona"]
    p = fw.persona_by_name(name)
    risk = p["risk"] if p else "Medium"
    idx = fw.PERSONA_NAMES.index(p["name"]) if p else 3
    dots = "".join(f'<span class="dot{" on" if i == idx else ""}" title="{esc(n_)}"></span>'
                   for i, n_ in enumerate(fw.PERSONA_NAMES))
    md(f"""<div class="k-card k-persona"><p class="pre">Today, you read mostly as</p>
    <h2>{esc(name)}</h2>
    <span class="k-pill" style="background:{RISK_COLORS.get(risk, '#6d7275')}">{esc(risk)} displacement risk</span>
    <p class="desc">{esc(p['desc'] if p else '')}</p>
    <div class="k-ladder"><div class="dots">{dots}</div>
    <div class="ends"><span>Most exposed to AI</span><span>Least exposed</span></div></div>
    <p class="note">This is one day. Run it on another day and it may read differently, because your days differ.</p></div>""")

    blend = result["quadrant_blend"]
    top = max(QUAD_ORDER, key=lambda k: blend.get(k, 0))

    def cell(k):
        a = 0.06 + 0.5 * blend.get(k, 0) / 100
        tint = "212,180,102" if ss["theme"] == "night" else "138,106,28"
        q = fw.QUADRANTS[k]
        return (f'<div class="k-cell{" top" if k == top else ""}" style="background:rgba({tint},{a:.2f})">'
                f'<div class="pct">{blend.get(k, 0)}%</div><div class="nm">{esc(q["label"])}</div>'
                f'<div class="ax2">{esc(q["axes"])}</div></div>')

    md(f"""<div class="k-card"><h3>Where your day sat</h3>
    <p class="k-hint">How today's work split across the four quadrants. The outlined box is where you spent most of it.</p>
    <div class="k-grid"><div></div><div class="ax">Accuracy</div><div class="ax">Originality</div>
    <div class="ay">Explicit</div>{cell('doctor')}{cell('builder')}
    <div class="ay">Tacit</div>{cell('general')}{cell('creator')}</div></div>""")

    if result.get("insight"):
        md(f"""<div class="k-card"><div class="k-eyebrow">What your words reveal</div>
        <p class="k-insight">{esc(analyzer.enforce_second_person(result['insight']))}</p></div>""")

    en = [analyzer.enforce_second_person(e) for e in (result.get("energizing") or [])] or ["Nothing clear."]
    dr = [analyzer.enforce_second_person(d) for d in (result.get("draining") or [])] or ["Nothing clear."]
    md(f"""<div class="k-card"><div class="k-two">
    <div><h4>Gave you energy</h4><ul>{''.join(f'<li>{esc(x)}</li>' for x in en)}</ul></div>
    <div><h4>Drained you</h4><ul>{''.join(f'<li>{esc(x)}</li>' for x in dr)}</ul></div></div></div>""")

    sigs = result.get("displacement_signals") or []
    if sigs:
        items = "".join(f'<li><span class="ph">&ldquo;{esc(s.get("phrase", ""))}&rdquo;</span>'
                        f'<span class="why">{esc(s.get("why", ""))}</span></li>' for s in sigs)
        md(f"""<div class="k-card"><h3>Tasks a tool could handle</h3>
        <p class="k-hint">In your own words, the parts of today an AI agent could already take on.</p>
        <ul class="k-sig">{items}</ul></div>""")

    presume = ("that issue", "you're designing", "The call you made", "The idea you're sitting", "that perspective")
    probes = [q for q in _pick_probe_questions(blend, name) if not any(x in q for x in presume)]
    big = analyzer.enforce_second_person(result.get("honest_question") or "")
    extra = "".join(f"<li>{esc(q)}</li>" for q in probes)
    md(f"""<div class="k-card k-ask"><div class="k-eyebrow">One question to sit with</div>
    <p class="big">{esc(big)}</p>
    {'<p class="k-hint" style="margin-top:6px">And if you have a minute more:</p><ol>' + extra + '</ol>' if extra else ''}
    </div>""")

    r1, r2 = st.columns(2)
    with r1:
        st.download_button("Download my read", data=build_summary_text(result, token),
                           file_name=f"kairos_{dt.date.today().isoformat()}.txt", mime="text/plain",
                           use_container_width=True)
    with r2:
        if st.button("Read another day", use_container_width=True):
            reset()
            st.rerun()

    if emailer.email_configured():
        with st.expander("Email this read to myself"):
            to = st.text_input("Your email address")
            if st.button("Send"):
                ok, msg = emailer.send_summary(to, f"Kairos: your read, {dt.date.today()}",
                                               build_summary_text(result, token))
                (st.success if ok else st.error)(msg)

    md("""<div class="k-card"><h3>How did this land?</h3>
    <p class="k-hint">Kairos is in beta. Your honest reaction goes straight to Puneet and shapes what comes next.</p></div>""")
    rating = st.radio("How accurate was your read?", ["Nailed it", "Close", "Missed the mark"],
                      horizontal=True, index=None, key="fb_rating")
    note = st.text_input("Anything that felt off, or especially right? (optional)", key="fb_note")
    body = (f"Rating: {rating or '-'}\nPersona: {name}\nReference: {token}\n\n{note or ''}")
    mailto = ("mailto:kairos@puneetsrivastava.com?subject=" + urllib.parse.quote("Kairos feedback")
              + "&body=" + urllib.parse.quote(body))
    st.link_button("Send feedback by email", mailto, use_container_width=True)

    md(f"""<div class="k-card" style="text-align:center"><h3>Go deeper</h3>
    <p>Kairos is built on the Knowledge Quadrant Framework. Read the thinking behind it, or get the next
    essay in your inbox every two weeks.</p>
    <p><a href="{SITE}/#framework" target="_blank">Read about the framework</a> &nbsp;·&nbsp;
    <a href="https://whatitsworthletter.substack.com/subscribe" target="_blank">Sign up free for the newsletter</a></p></div>""")

md(f"""<div class="k-foot">Kairos · built on the Knowledge Quadrant Framework by
<a href="{SITE}" target="_blank">Puneet Srivastava</a> · Powered by Claude (Anthropic)</div>""")
