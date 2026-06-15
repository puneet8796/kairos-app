"""
app.py
Kairos. A non-intrusive AI self-assessment.

You talk through your day. A local model reads it back through the
Knowledge Quadrant Framework and shows you where you actually stand.

No login. No account. One session. Your words never leave this machine.

Run:  streamlit run app.py --server.port 8502 --server.address 0.0.0.0
"""

import datetime as dt
import random
import string

import streamlit as st

import analyzer
import emailer
import framework as fw

st.set_page_config(page_title="Kairos", page_icon="◈", layout="centered")

st.markdown("""
<style>
  /* Dark background */
  .stApp { background-color: #0d0d0d; color: #f0ede8; }

  /* Gold accent on primary button */
  .stButton > button[kind="primary"] {
    background-color: #c9a84c;
    color: #0d0d0d;
    border: none;
    font-weight: 700;
    border-radius: 6px;
  }
  .stButton > button[kind="primary"]:hover {
    background-color: #b8973d;
  }

  /* Text area */
  .stTextArea textarea {
    background-color: #1a1a1a;
    color: #f0ede8;
    border: 1px solid #333;
    border-radius: 6px;
  }

  /* Progress bars gold */
  .stProgress > div > div {
    background-color: #c9a84c;
  }

  /* Muted captions */
  .stCaption { color: #888; }

  /* Hide Streamlit footer and menu */
  #MainMenu { visibility: hidden; }
  footer { visibility: hidden; }

  /* Session token display */
  .kairos-token {
    font-family: monospace;
    font-size: 0.8rem;
    color: #c9a84c;
    text-align: right;
    padding: 4px 0;
  }
</style>
""", unsafe_allow_html=True)

if "session_token" not in st.session_state:
    chars = string.ascii_uppercase + string.digits
    st.session_state["session_token"] = "KQ-" + "".join(
        random.choices(chars, k=4)
    )
token = st.session_state["session_token"]
st.markdown(
    f"<div class='kairos-token'>Session ID: {token} "
    f"— save this</div>",
    unsafe_allow_html=True
)

RISK_COLORS = {
    "Critical": "#c0392b",
    "High": "#e67e22",
    "Medium-High": "#e1a100",
    "Medium": "#7f8c8d",
    "Medium-Low": "#16a085",
    "Low": "#27ae60",
    "Very Low": "#2471a3",
    "Minimal": "#5b2c8d",
}

QUAD_ORDER = ["doctor", "builder", "general", "creator"]

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
        "The system you're designing — who owns it after you hand it off?",
        "What breaks first if you step away for two weeks?",
        "Do the people you're aligning today understand why the structure matters, or just that it does?",
    ],
    "The Strategist": [
        "The call you made today — could you explain the reasoning to someone junior in a way that teaches them to make it themselves next time?",
        "Is your judgment being used at the right altitude, or are you solving problems a level below where you should be operating?",
        "What are you the last line of defense for?",
    ],
    "The Visionary": [
        "The idea you're sitting with — does anyone else in your organization see it yet?",
        "What would have to be true for that thinking to become a decision in the next 90 days?",
        "Who do you have these kinds of conversations with regularly?",
    ],
    "The Oracle": [
        "When you shared that perspective today, was it heard as insight or as opinion?",
        "How much of what you know is written down somewhere accessible to others?",
        "Are you building something that carries your thinking forward, or is it still mostly in your head?",
    ],
}

# Maps each quadrant to the personas whose questions probe that quadrant's themes.
# Tie-break priority: creator > general > builder > doctor.
_QUAD_PROBE_PRIORITY = ["creator", "general", "builder", "doctor"]
_QUAD_PERSONAS = {
    "doctor":  ["The Doer", "The Responder"],
    "builder": ["The Craftsman", "The Architect"],
    "general": ["The Strategist"],
    "creator": ["The Visionary", "The Oracle"],
}


def _pick_probe_questions(blend, dominant_persona):
    """Return 2 probe question strings driven by the lowest-weighted quadrants."""
    priority = _QUAD_PROBE_PRIORITY

    zero_quads = [q for q in priority if blend.get(q, 0) == 0]
    non_zero = sorted(
        [(q, blend[q]) for q in priority if blend.get(q, 0) > 0],
        key=lambda x: (x[1], priority.index(x[0])),
    )

    if len(zero_quads) >= 2:
        probe_quads = zero_quads[:2]
    elif len(zero_quads) == 1:
        probe_quads = [zero_quads[0], non_zero[0][0]] if non_zero else zero_quads[:1]
    else:
        probe_quads = [non_zero[0][0], non_zero[1][0]] if len(non_zero) >= 2 else [non_zero[0][0]]

    questions = []
    used_personas = []
    for quad in probe_quads:
        candidates = _QUAD_PERSONAS.get(quad, [])
        if dominant_persona in candidates:
            persona_key = dominant_persona
        else:
            persona_key = next((p for p in candidates if p not in used_personas), candidates[0] if candidates else None)
        if not persona_key:
            continue
        used_personas.append(persona_key)
        q_list = PROBE_QUESTIONS.get(persona_key, [])
        same_count = used_personas[:-1].count(persona_key)
        idx = min(same_count, len(q_list) - 1)
        if q_list:
            questions.append(q_list[idx])

    return questions


def build_summary_text(result, transcript, token="") -> str:
    p = fw.persona_by_name(result["dominant_persona"])
    risk = p["risk"] if p else "unknown"
    lines = []
    lines.append("KAIROS — your day, read back\n")
    lines.append(f"Date: {dt.date.today().isoformat()}")
    lines.append(f"Session ID: {token}")
    lines.append(f"Dominant persona: {result['dominant_persona']} ({risk} displacement risk)")
    why_text = fw.PERSONA_WHY.get(result["dominant_persona"], "")
    if why_text:
        lines.append(f"Why: {why_text}")
    lines.append("")
    lines.append("Quadrant blend:")
    for k in QUAD_ORDER:
        lines.append(f"  {fw.QUADRANTS[k]['label']:<14} {result['quadrant_blend'][k]:>3}%")
    lines.append("")
    if result.get("displacement_signals"):
        lines.append("Displacement signals (work an agent could take):")
        for s in result["displacement_signals"]:
            lines.append(f"  - \"{s.get('phrase','')}\" — {s.get('why','')}")
        lines.append("")
    if result.get("energizing"):
        lines.append("What energized you: " + "; ".join(result["energizing"]))
    if result.get("draining"):
        lines.append("What drained you: " + "; ".join(result["draining"]))
    lines.append("")
    if result.get("insight"):
        lines.append("Insight:")
        lines.append("  " + result["insight"])
    if result.get("honest_question"):
        lines.append("")
        lines.append("A question to sit with:")
        lines.append("  " + result["honest_question"])
    lines.append("")
    lines.append("— Kairos | Built on the Knowledge Quadrant Framework by Puneet Srivastava")
    return "\n".join(lines)


def risk_pill(risk: str):
    color = RISK_COLORS.get(risk, "#7f8c8d")
    st.markdown(
        f"<span style='background:{color};color:white;padding:3px 12px;"
        f"border-radius:14px;font-size:0.85rem;font-weight:600;'>"
        f"{risk} displacement risk</span>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- UI
st.title("Kairos")
st.caption(
    "The moment of reckoning. Speak freely. "
    "Know where you stand."
)
st.caption(
    "No login. One session. Your words never leave "
    "this machine. This is a mirror, not a quiz."
)

# Inspiration chips
CHIPS = [
    "What took the most energy today?",
    "What decision did only you make?",
    "What felt mechanical — something a tool could have done?",
    "When did you feel most irreplaceable today?",
    "What would have broken if you weren't there?",
]

if "chip_seed" not in st.session_state:
    st.session_state["chip_seed"] = random.randint(0, 99)

random.seed(st.session_state["chip_seed"])
shuffled = random.sample(CHIPS, len(CHIPS))

st.caption("Not sure where to start? Pick a prompt:")
chip_cols = st.columns(len(shuffled))

if "chip_text" not in st.session_state:
    st.session_state["chip_text"] = ""

for i, chip in enumerate(shuffled):
    with chip_cols[i]:
        if st.button(chip, key=f"chip_{i}",
                     use_container_width=True):
            st.session_state["chip_text"] = chip

transcript = st.text_area(
    label="Your day",
    height=260,
    value=st.session_state.get("chip_text", ""),
    placeholder="Start anywhere. What is on your mind? "
                "It could be your whole day, one moment "
                "that stood out, a decision you made, "
                "something that energized you or drained "
                "you. There is no wrong way to begin.",
    label_visibility="collapsed",
    key="transcript_input",
)

# Live word count feedback
word_count = len(transcript.strip().split()) \
             if transcript.strip() else 0
if word_count == 0:
    pass
elif word_count < 50:
    st.caption(
        f"{word_count} words — keep going, "
        f"the more you share the sharper the insight."
    )
elif word_count < 150:
    st.caption(f"{word_count} words — good, you're in the zone.")
else:
    st.caption(
        f"{word_count} words — that's plenty. "
        f"Submit when ready."
    )

col_a, col_b = st.columns([1, 3])
with col_a:
    go = st.button("Read my day", type="primary", use_container_width=True)
with col_b:
    st.caption(f"Local model: `{analyzer.OLLAMA_MODEL}` via Ollama")


def _stage1_validate(text: str):
    words = text.strip().split()
    if len(words) < 40:
        return False, (
            f"Just a little more — you've written {len(words)} "
            f"words so far. Forty words is enough. No need to "
            f"organize it, just keep talking."
        )
    unique_ratio = len(set(w.lower() for w in words)) \
                   / len(words)
    if unique_ratio < 0.30:
        return False, (
            "Looks like something got repeated. Just write "
            "naturally — whatever comes to mind about your day "
            "is exactly right."
        )
    ascii_ratio = sum(
        1 for c in text if ord(c) < 128
    ) / len(text)
    if ascii_ratio < 0.90:
        return False, (
            "Kairos works best with an English narrative. "
            "Write however you normally think — no need to "
            "be formal."
        )
    return True, ""


if go:
    ok, msg = _stage1_validate(transcript)
    if not ok:
        st.warning(msg)
        st.stop()
    with st.spinner(
        "Reading your day through the four quadrants..."
    ):
        result = analyzer.analyze(transcript)
    st.session_state["result"] = result
    st.session_state["transcript"] = transcript

# ----------------------------------------------------------------------- Results
if "result" in st.session_state:
    result = st.session_state["result"]
    transcript = st.session_state["transcript"]

    if result.get("_fallback"):
        st.error(result["insight"])

    st.divider()

    # Persona
    p = fw.persona_by_name(result["dominant_persona"])
    st.subheader(f"You read mostly as {result['dominant_persona']}")
    if p:
        risk_pill(p["risk"])
        st.write("")
        st.write(p["desc"])
    why_text = fw.PERSONA_WHY.get(result["dominant_persona"], "")
    if why_text:
        st.markdown(f"*{why_text}*")

    # Quadrant blend
    st.markdown("#### Your quadrant blend today")
    for k in QUAD_ORDER:
        pct = result["quadrant_blend"][k]
        q = fw.QUADRANTS[k]
        st.markdown(f"**{q['label']}** &middot; {pct}%  \n<span style='color:#888;font-size:0.8rem'>{q['axes']}</span>",
                    unsafe_allow_html=True)
        st.progress(min(pct, 100) / 100)

    # Flip-card reflection probes
    st.markdown("#### A few things to sit with")
    probe_qs = _pick_probe_questions(result["quadrant_blend"], result["dominant_persona"])
    for q in probe_qs:
        with st.expander("Reflect →", expanded=False):
            st.markdown(f"<p style='font-size:1.1rem'>{q}</p>", unsafe_allow_html=True)
            st.caption("You don't need to answer here. Just let it sit.")

    # Displacement signals
    if result.get("displacement_signals"):
        st.markdown("#### Where an agent could step in")
        for s in result["displacement_signals"]:
            st.markdown(f"- “{s.get('phrase','')}” — *{s.get('why','')}*")

    # Energy
    if result.get("energizing") or result.get("draining"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Energized you")
            for e in result.get("energizing", []) or ["—"]:
                st.markdown(f"- {analyzer.enforce_second_person(e)}")
        with c2:
            st.markdown("#### Drained you")
            for d in result.get("draining", []) or ["—"]:
                st.markdown(f"- {analyzer.enforce_second_person(d)}")

    # Insight + question
    if result.get("insight"):
        st.markdown("#### What your words reveal")
        st.info(analyzer.enforce_second_person(result["insight"]))
    if result.get("honest_question"):
        st.markdown("#### One question to sit with")
        st.success(analyzer.enforce_second_person(result["honest_question"]))

    # Delivery
    st.divider()
    summary = build_summary_text(result, transcript, token)
    st.download_button(
        "Download this summary",
        data=summary,
        file_name=f"kairos_{token}.txt",
        mime="text/plain",
    )

    if emailer.email_configured():
        with st.expander("Email this summary to myself"):
            to = st.text_input("Your email address")
            st.caption(
                "Sent from kairos.puneet@gmail.com — "
                "configure SMTP_* env vars to activate."
            )
            if st.button("Send"):
                ok, msg = emailer.send_summary(
                    to,
                    f"Kairos — your honest picture, {dt.date.today()}",
                    summary,
                )
                (st.success if ok else st.error)(msg)
    else:
        st.caption("Email delivery is off. Set the SMTP_* env vars to turn it on.")

    with st.expander("What this tool looked at"):
        st.write(
            "It mapped your time across the four quadrants, flagged language that signals "
            "documentable work, and noted what energized versus drained you. It runs entirely "
            "on this machine. Nothing was sent anywhere."
        )
