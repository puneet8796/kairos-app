"""
app.py
Kairos — Know where you stand.

Run:  streamlit run app.py --server.port 8502 --server.address 0.0.0.0
"""

import base64
import datetime as dt
import random
import string

import streamlit as st

import analyzer
import emailer
import framework as fw
import student_framework as sf
import storage

def load_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


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

  /* Progress bars gold (default; overridden per-persona in student mode) */
  .stProgress > div > div > div {
    background-color: #c9a84c;
  }
  .stProgress > div > div {
    background-color: #2a2a2a;
  }
  [data-testid="stProgressBar"] > div > div > div {
    background-color: #c9a84c;
  }
  [data-testid="stProgressBar"] > div > div {
    background-color: #2a2a2a;
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

  /* Landing page */
  .kairos-landing-header {
    text-align: center;
    color: #c9a84c;
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    margin-bottom: 4px;
  }
  .kairos-landing-sub {
    text-align: center;
    color: #888;
    font-size: 0.9rem;
    letter-spacing: 0.1em;
    margin-bottom: 40px;
  }
  .kairos-card {
    background: #1a1a1a;
    padding: 32px;
    border-radius: 8px;
    border: 1px solid #2a2a2a;
    text-align: center;
    margin-bottom: 16px;
  }
  .kairos-card:hover { border-color: #c9a84c; }
  .kairos-card-icon {
    font-size: 2rem;
    color: #c9a84c;
    display: block;
    margin-bottom: 12px;
  }
  .kairos-card-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #f0ede8;
    margin-bottom: 10px;
  }
  .kairos-card-body {
    font-size: 0.9rem;
    color: #aaa;
    margin-bottom: 8px;
  }
  .kairos-card-sub {
    font-size: 0.78rem;
    color: #666;
    margin-bottom: 20px;
  }
  .kairos-landing-footer {
    text-align: center;
    color: #555;
    font-size: 0.78rem;
    margin-top: 48px;
  }
</style>
""", unsafe_allow_html=True)

# ─── SESSION TOKEN ───
if "session_token" not in st.session_state:
    chars = string.ascii_uppercase + string.digits
    st.session_state["session_token"] = "KQ-" + "".join(
        random.choices(chars, k=4)
    )
token = st.session_state["session_token"]

# ─── CONSTANTS ───
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
            persona_key = next(
                (p for p in candidates if p not in used_personas),
                candidates[0] if candidates else None,
            )
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


def _stage1_validate(text: str):
    words = text.strip().split()
    if len(words) < 40:
        return False, (
            f"Just a little more — you've written {len(words)} "
            f"words so far. Forty words is enough. No need to "
            f"organize it, just keep talking."
        )
    unique_ratio = len(set(w.lower() for w in words)) / len(words)
    if unique_ratio < 0.30:
        return False, (
            "Looks like something got repeated. Just write "
            "naturally — whatever comes to mind about your day "
            "is exactly right."
        )
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
    if ascii_ratio < 0.90:
        return False, (
            "Kairos works best with an English narrative. "
            "Write however you normally think — no need to "
            "be formal."
        )
    return True, ""


# ═══════════════════════════════════════
# LANDING PAGE
# ═══════════════════════════════════════
if "mode" not in st.session_state:

    try:
        bg_b64 = load_image_base64("IMG2.jpg")
        has_bg = True
    except Exception:
        has_bg = False

    try:
        logo_b64 = load_image_base64("IMG3.jpg")
        has_logo = True
    except Exception:
        has_logo = False

    if has_bg:
        st.markdown(f"""
<style>
.stApp::before {{
    content: '';
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 700px;
    height: 700px;
    background-image: url('data:image/jpeg;base64,{bg_b64}');
    background-size: contain;
    background-repeat: no-repeat;
    background-position: center;
    opacity: 0.07;
    z-index: 0;
    pointer-events: none;
}}
[data-testid="column"] {{
    display: flex;
    flex-direction: column;
}}
.stButton > button {{
    width: 100%;
}}
</style>
""", unsafe_allow_html=True)

    if has_logo:
        st.markdown(
            f"<div style='text-align:center;padding:48px 0 8px 0;'>"
            f"<img src='data:image/jpeg;base64,{logo_b64}' "
            f"style='height:52px;filter:invert(1);opacity:0.92;'/>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<h1 style='text-align:center;color:#c9a84c;"
            "letter-spacing:0.15em;'>KAIROS</h1>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<p style='text-align:center;color:#666;font-size:0.8rem;"
        "letter-spacing:0.12em;margin-top:4px;margin-bottom:40px;'>"
        "KNOW WHERE YOU STAND</p>",
        unsafe_allow_html=True,
    )

    card_style = (
        "background:#1a1a1a;"
        "border:1px solid #2a2a2a;"
        "border-radius:12px;"
        "padding:40px 32px 32px 32px;"
        "text-align:center;"
        "min-height:280px;"
        "display:flex;"
        "flex-direction:column;"
        "justify-content:space-between;"
    )

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown(f"""
        <div style='{card_style}'>
          <div>
            <div style='font-size:2rem;color:#c9a84c;margin-bottom:16px;'>◈</div>
            <div style='font-size:1.15rem;font-weight:700;color:#f0ede8;
              margin-bottom:12px;'>For Professionals</div>
            <div style='font-size:0.9rem;color:#aaa;margin-bottom:8px;'>
              Where does your work stand in the age of AI?</div>
            <div style='font-size:0.75rem;color:#555;'>
              10 minutes · Local analysis · No account</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Enter →", key="pro_enter", type="primary", use_container_width=True):
            st.session_state["mode"] = "professional"
            st.rerun()

    with col2:
        st.markdown(f"""
        <div style='{card_style}'>
          <div>
            <div style='font-size:2rem;color:#c9a84c;margin-bottom:16px;'>◎</div>
            <div style='font-size:1.15rem;font-weight:700;color:#f0ede8;
              margin-bottom:12px;'>Kairos Student</div>
            <div style='font-size:0.9rem;color:#aaa;margin-bottom:8px;'>
              Are you spending your energy on the things that matter to you?</div>
            <div style='font-size:0.75rem;color:#555;'>
              10 minutes · Honest feedback · Just for you</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Enter →", key="student_enter", type="primary", use_container_width=True):
            st.session_state["mode"] = "student"
            st.rerun()

    st.markdown(
        "<p style='text-align:center;color:#444;font-size:0.75rem;"
        "margin-top:48px;'>No login. No account. Your words stay yours.</p>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════
# PROFESSIONAL MODE
# ═══════════════════════════════════════
elif st.session_state["mode"] == "professional":

    if st.button("← Change mode", key="change_mode_pro"):
        st.session_state.clear()
        st.rerun()

    st.markdown(
        f"<div class='kairos-token'>Session ID: {token} — save this</div>",
        unsafe_allow_html=True,
    )

    st.title("Kairos")
    st.caption(
        "The moment of reckoning. Speak freely. "
        "Know where you stand."
    )
    st.caption(
        "No login. One session. Your words never leave "
        "this machine. This is a mirror, not a quiz."
    )

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
            if st.button(chip, key=f"chip_{i}", use_container_width=True):
                st.session_state["chip_text"] = chip

    transcript = st.text_area(
        label="Your day",
        height=260,
        value=st.session_state.get("chip_text", ""),
        placeholder=(
            "Start anywhere. What is on your mind? "
            "It could be your whole day, one moment "
            "that stood out, a decision you made, "
            "something that energized you or drained "
            "you. There is no wrong way to begin."
        ),
        label_visibility="collapsed",
        key="transcript_input",
    )

    word_count = len(transcript.strip().split()) if transcript.strip() else 0
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
        st.caption(f"{word_count} words — that's plenty. Submit when ready.")

    col_a, col_b = st.columns([1, 3])
    with col_a:
        go = st.button("Read my day", type="primary", use_container_width=True)
    with col_b:
        st.caption(f"Local model: `{analyzer.OLLAMA_MODEL}` via Ollama")

    if go:
        ok, msg = _stage1_validate(transcript)
        if not ok:
            st.warning(msg)
            st.stop()
        with st.spinner("Reading your day through the four quadrants..."):
            result = analyzer.analyze(transcript)
        st.session_state["result"] = result
        st.session_state["transcript"] = transcript
        storage.save_session(
            token=token,
            mode="professional",
            persona=result["dominant_persona"],
            blend=result["quadrant_blend"],
            transcript=transcript,
            insight=result.get("insight", ""),
        )

    if "result" in st.session_state:
        result = st.session_state["result"]
        transcript = st.session_state["transcript"]

        if result.get("_fallback"):
            st.error(result["insight"])

        st.divider()

        p = fw.persona_by_name(result["dominant_persona"])
        st.subheader(f"You read mostly as {result['dominant_persona']}")
        if p:
            risk_pill(p["risk"])
            st.write("")
            st.write(p["desc"])
            if result.get("persona_rationale"):
                st.markdown(f"*{result['persona_rationale']}*")

            with st.expander("ℹ️ What does this mean? See all eight personas"):
                for persona in fw.PERSONAS:
                    risk = persona["risk"]
                    color = RISK_COLORS.get(risk, "#7f8c8d")
                    st.markdown(
                        f"**{persona['name']}** · "
                        f"<span style='color:{color};font-size:0.8rem;'>"
                        f"{risk} displacement risk</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(persona["desc"])
                    st.divider()
        why_text = fw.PERSONA_WHY.get(result["dominant_persona"], "")
        if why_text:
            st.markdown(f"*{why_text}*")

        st.markdown("#### Your quadrant blend today")
        for k in QUAD_ORDER:
            pct = result["quadrant_blend"][k]
            q = fw.QUADRANTS[k]
            st.markdown(
                f"**{q['label']}** &middot; {pct}%  \n"
                f"<span style='color:#888;font-size:0.8rem'>{q['axes']}</span>",
                unsafe_allow_html=True,
            )
            st.progress(min(pct, 100) / 100)

        st.markdown("#### A few things to sit with")
        probe_qs = _pick_probe_questions(
            result["quadrant_blend"], result["dominant_persona"]
        )
        for q in probe_qs:
            with st.expander("Reflect →", expanded=False):
                st.markdown(
                    f"<p style='font-size:1.1rem'>{q}</p>",
                    unsafe_allow_html=True,
                )
                st.caption("You don't need to answer here. Just let it sit.")

        if result.get("displacement_signals"):
            st.markdown("#### Where an agent could step in")
            for s in result["displacement_signals"]:
                st.markdown(f"- “{s.get('phrase','')}” — *{s.get('why','')}*")

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

        if result.get("insight"):
            st.markdown("#### What your words reveal")
            st.info(analyzer.enforce_second_person(result["insight"]))
        if result.get("honest_question"):
            st.markdown("#### One question to sit with")
            st.success(analyzer.enforce_second_person(result["honest_question"]))

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

        st.markdown(
            f"<p style='color:#555;font-size:0.72rem;'>Session {token} stored anonymously "
            f"to help improve Kairos.</p>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════
# STUDENT MODE
# ═══════════════════════════════════════
elif st.session_state["mode"] == "student":

    if st.button("← Change mode", key="change_mode_student"):
        st.session_state.clear()
        st.rerun()

    st.markdown(
        f"<div class='kairos-token'>Session ID: {token} — save this</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<h2 style='color:#c9a84c;font-size:1.5rem;margin-bottom:4px;'>Kairos Student</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Ten minutes. Talk about your day. Get honest feedback on what you're building "
        "— and what you might be missing."
    )

    # ─── INPUT SECTION ───
    if "student_result" not in st.session_state:

        st.caption("Not sure where to start? Pick a prompt:")

        if "student_chip_seed" not in st.session_state:
            st.session_state["student_chip_seed"] = random.randint(0, 99)

        random.seed(st.session_state["student_chip_seed"])
        chips_shuffled = random.sample(sf.STUDENT_CHIPS, len(sf.STUDENT_CHIPS))

        chip_cols = st.columns(len(chips_shuffled))

        if "student_chip_text" not in st.session_state:
            st.session_state["student_chip_text"] = ""

        for i, chip in enumerate(chips_shuffled):
            with chip_cols[i]:
                if st.button(chip, key=f"s_chip_{i}", use_container_width=True):
                    st.session_state["student_chip_text"] = chip

        student_transcript = st.text_area(
            label="Your day",
            height=260,
            value=st.session_state.get("student_chip_text", ""),
            placeholder=(
                "Start anywhere. What happened today? What did you think about? "
                "Who did you talk to? There's no wrong way to begin."
            ),
            label_visibility="collapsed",
            key="student_transcript_input",
        )

        s_words = len(student_transcript.strip().split()) if student_transcript.strip() else 0
        if s_words == 0:
            pass
        elif s_words < 30:
            st.caption(
                f"{s_words} words — keep going, "
                f"a little more and we can really see something."
            )
        elif s_words < 100:
            st.caption(f"{s_words} words — good, you're in the zone.")
        else:
            st.caption(f"{s_words} words — that's plenty.")

        go_student = st.button("Read my day →", type="primary")
        if go_student:
            if len(student_transcript.strip().split()) < 30:
                st.warning(
                    "Just a little more — even 30 words gives us something real to work with."
                )
                st.stop()
            with st.spinner("Reading your day..."):
                s_result = analyzer.analyze_student(student_transcript)
            st.session_state["student_result"] = s_result
            st.session_state["student_transcript"] = student_transcript
            storage.save_session(
                token=token,
                mode="student",
                persona=s_result["dominant_persona"],
                blend=s_result["mode_blend"],
                transcript=student_transcript,
                insight=s_result.get("insight", ""),
            )
            st.rerun()

    # ─── RESULTS SECTION ───
    else:
        result = st.session_state["student_result"]
        transcript = st.session_state["student_transcript"]

        p = sf.student_persona_by_name(result["dominant_persona"])
        persona_color = p["color"] if p else "#c9a84c"

        st.markdown(f"""
<style>
[data-testid="stProgressBar"] > div > div > div {{
    background-color: {persona_color} !important;
}}
[data-testid="stProgressBar"] > div > div {{
    background-color: #2a2a2a !important;
}}
.stProgress > div > div > div {{
    background-color: {persona_color} !important;
}}
.stProgress > div > div {{
    background-color: #2a2a2a !important;
}}
.persona-color {{ color: {persona_color}; }}
.persona-border {{
    border-left: 4px solid {persona_color};
    padding-left: 16px;
}}
</style>
""", unsafe_allow_html=True)

        # BLOCK 1 — WHAT IS WORKING
        st.markdown("#### What today said about you")
        for item in result.get("what_is_working", []):
            st.success(item)

        # BLOCK 2 — PERSONA
        st.divider()
        st.markdown(
            f"<h3 style='color:{persona_color};'>"
            f"You showed up today as {result['dominant_persona']}</h3>",
            unsafe_allow_html=True,
        )
        if p:
            st.write(p["desc"])

            with st.expander("ℹ️ What does this mean? See all four modes"):
                for sp in sf.STUDENT_PERSONAS:
                    color = sp["color"]
                    st.markdown(f"**{sp['name']}** · *{sp['mode']}*")
                    st.markdown(sp["desc"])
                    st.markdown(
                        f"<span style='color:{color};font-size:0.8rem;'>"
                        f"Growth edge: {sp['growth_edge']}</span>",
                        unsafe_allow_html=True,
                    )
                    st.divider()

        # BLOCK 3 — MODE BLEND
        st.markdown("#### Your energy map today")
        mode_labels = {
            "wave_rider": "Wave Rider",
            "main_attraction": "Main Attraction",
            "the_learned": "The Learned",
            "the_builder": "The Builder",
        }
        for key, label in mode_labels.items():
            pct = result["mode_blend"].get(key, 0)
            st.markdown(f"**{label}** &middot; {pct}%")
            st.progress(min(pct, 100) / 100)

        # BLOCK 4 — GROWTH
        st.divider()
        st.markdown("#### Something worth exploring")
        for item in result.get("growth_observations", []):
            st.info(item)

        # BLOCK 5 — EXPANSION SUGGESTION
        st.divider()
        if p:
            st.markdown(
                f"<div class='persona-border'>"
                f"<h4>One thing to try tomorrow</h4>"
                f"<p>{p['expansion']}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # BLOCK 6 — INSIGHT + QUESTION
        st.divider()
        if result.get("insight"):
            st.markdown("#### What your day reveals")
            st.info(result["insight"])
        if result.get("honest_question"):
            st.markdown("#### A question to sit with")
            st.success(result["honest_question"])

        # BLOCK 7 — CELEBRATION
        st.divider()
        if p:
            st.markdown(f"*{p['celebration']}*")

        # BLOCK 8 — STORAGE NOTE + RESET
        st.markdown(
            f"<p style='color:#555;font-size:0.72rem;margin-top:24px;'>"
            f"Session {token} stored anonymously to help improve Kairos Student. "
            f"No names. No contact info. Just this.</p>",
            unsafe_allow_html=True,
        )

        if st.button("Reflect on another day →"):
            del st.session_state["student_result"]
            del st.session_state["student_transcript"]
            st.rerun()
