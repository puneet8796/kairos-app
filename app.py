"""
app.py
Kairos — Know where you stand.
"""

import base64
import datetime as dt
import hashlib
import io
import os

import streamlit as st

# Transfer Streamlit secrets to env before importing dependent modules.
# storage.py and analyzer.py read DATABASE_URL / ANTHROPIC_API_KEY via os.environ.
for _k in ("DATABASE_URL", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
    if _k not in os.environ:
        try:
            if _k in st.secrets:
                os.environ[_k] = st.secrets[_k]
        except Exception:
            pass

import analyzer
import framework as fw
import storage


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _voice_backend():
    """Return 'groq', 'local', or None.

    'groq'  — GROQ_API_KEY is set; transcribe via Groq Whisper on the cloud.
    'local' — faster-whisper is importable; transcribe on this machine.
    None    — no voice backend available; suppress the entire recorder UI.
    """
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    try:
        import faster_whisper  # noqa: F401
        return "local"
    except Exception:
        return None


def _transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio. Audio bytes are held in a local variable only —
    never written to disk, never stored in session_state, never passed to
    storage. After this function returns the bytes go out of scope.

    Raises RuntimeError on failure so the caller can surface the message
    via st.error() and leave the text box usable.
    """
    backend = _voice_backend()
    if backend == "groq":
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        try:
            response = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("audio.webm", io.BytesIO(audio_bytes), "audio/webm"),
            )
        except Exception as exc:
            raise RuntimeError(f"Groq transcription failed: {exc}") from exc
        return response.text

    if backend == "local":
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        try:
            # Pass a BytesIO so audio never touches disk.
            segments, _ = model.transcribe(io.BytesIO(audio_bytes))
            return " ".join(s.text.strip() for s in segments)
        except Exception as exc:
            raise RuntimeError(f"Local transcription failed: {exc}") from exc

    raise RuntimeError("No transcription backend is available.")


def generate_pdf_from_row(row: dict) -> bytes:
    """Produce a one-to-two page PDF for a locked read. Pure reportlab, no matplotlib."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    gold = colors.HexColor("#c9a84c")
    charcoal = colors.HexColor("#1a1a1a")
    muted = colors.HexColor("#666666")

    title_sty = ParagraphStyle("kt", parent=styles["Heading1"],
                                textColor=gold, fontSize=26, spaceAfter=2, leading=30)
    h2_sty = ParagraphStyle("kh2", parent=styles["Heading2"],
                              textColor=charcoal, fontSize=13, spaceAfter=3)
    body_sty = ParagraphStyle("kb", parent=styles["Normal"],
                               textColor=charcoal, fontSize=10, leading=15, spaceAfter=5)
    label_sty = ParagraphStyle("kl", parent=styles["Normal"],
                                textColor=gold, fontSize=9,
                                fontName="Helvetica-Bold", spaceAfter=1)
    sub_sty = ParagraphStyle("ks", parent=styles["Normal"],
                              textColor=muted, fontSize=9, spaceAfter=2)
    cell_sty = ParagraphStyle("kc", parent=styles["Normal"],
                               textColor=colors.white, fontSize=8,
                               leading=12, alignment=1)

    story = []

    story.append(Paragraph("KAIROS", title_sty))
    date_str = (row.get("created_at") or "")[:10]
    story.append(Paragraph(f"Code: {row.get('code', '')}  |  {date_str}", sub_sty))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=gold))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(f"You showed up mostly as {row.get('persona', '')}", h2_sty))
    story.append(Spacer(1, 4 * mm))

    # 2x2 quadrant matrix as a colored table
    blend = row.get("blend") or {}

    def cell_bg(pct):
        t = min(pct / 100.0, 1.0)
        r = int(0x1a + t * (0xc9 - 0x1a))
        g = int(0x1a + t * (0xa8 - 0x1a))
        b = int(0x1a + t * (0x4c - 0x1a))
        return colors.Color(r / 255, g / 255, b / 255)

    col_w = 80 * mm
    row_h = 32 * mm

    def cell(label, pct):
        return Paragraph(f"{label}<br/>~{pct}%", cell_sty)

    matrix_data = [
        [cell("The Builders\n(Explicit + Original)", blend.get("builder", 0)),
         cell("The Creators\n(Tacit + Original)", blend.get("creator", 0))],
        [cell("The Doctors\n(Explicit + Accurate)", blend.get("doctor", 0)),
         cell("The Generals\n(Tacit + Accurate)", blend.get("general", 0))],
    ]
    matrix = Table(matrix_data, colWidths=[col_w, col_w], rowHeights=[row_h, row_h])
    matrix.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), cell_bg(blend.get("builder", 0))),
        ("BACKGROUND", (1, 0), (1, 0), cell_bg(blend.get("creator", 0))),
        ("BACKGROUND", (0, 1), (0, 1), cell_bg(blend.get("doctor", 0))),
        ("BACKGROUND", (1, 1), (1, 1), cell_bg(blend.get("general", 0))),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#333333")),
    ]))
    story.append(matrix)
    story.append(Spacer(1, 8 * mm))

    for label, key in [
        ("What your words reveal", "insight"),
        ("Your next move", "next_move"),
        ("A question to sit with", "honest_question"),
    ]:
        text = (row.get(key) or "").strip()
        if text:
            story.append(Paragraph(label, label_sty))
            story.append(Paragraph(text, body_sty))
            story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=muted))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Kairos | Knowledge Quadrant Framework | Not a score. Not a verdict. A mirror for one day.",
        sub_sty,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def risk_pill(risk: str):
    RISK_COLORS = {
        "Critical": "#c0392b", "High": "#e67e22", "Medium-High": "#e1a100",
        "Medium": "#7f8c8d", "Medium-Low": "#16a085", "Low": "#27ae60",
        "Very Low": "#2471a3", "Minimal": "#5b2c8d",
    }
    color = RISK_COLORS.get(risk, "#7f8c8d")
    st.markdown(
        f"<span style='background:{color};color:white;padding:3px 12px;"
        f"border-radius:14px;font-size:0.85rem;font-weight:600;'>"
        f"{risk} displacement risk</span>",
        unsafe_allow_html=True,
    )


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
        persona_key = (dominant_persona if dominant_persona in candidates
                       else next((p for p in candidates if p not in used_personas),
                                 candidates[0] if candidates else None))
        if not persona_key:
            continue
        used_personas.append(persona_key)
        q_list = PROBE_QUESTIONS.get(persona_key, [])
        idx = min(used_personas[:-1].count(persona_key), len(q_list) - 1)
        if q_list:
            questions.append(q_list[idx])
    return questions


def _stage1_validate(text: str):
    words = text.strip().split()
    if len(words) < 40:
        return False, (
            f"Just a little more — you've written {len(words)} words so far. "
            "Forty words is enough. No need to organize it, just keep talking."
        )
    unique_ratio = len(set(w.lower() for w in words)) / len(words)
    if unique_ratio < 0.30:
        return False, (
            "Looks like something got repeated. Just write naturally — whatever "
            "comes to mind about your day is exactly right."
        )
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
    if ascii_ratio < 0.90:
        return False, (
            "Kairos works best with an English narrative. Write however you "
            "normally think — no need to be formal."
        )
    return True, ""


def build_summary_text(result, transcript, code="") -> str:
    p = fw.persona_by_name(result["dominant_persona"])
    risk = p["risk"] if p else "unknown"
    lines = ["KAIROS — your day, read back\n"]
    lines.append(f"Date: {dt.date.today().isoformat()}")
    if code:
        lines.append(f"Code: {code}")
    lines.append(f"You showed up mostly as: {result['dominant_persona']} ({risk} displacement risk)")
    lines.append("")
    lines.append("Quadrant blend (approximate):")
    for k in QUAD_ORDER:
        lines.append(f"  {fw.QUADRANTS[k]['label']:<14} ~{result['quadrant_blend'][k]:>3}%")
    lines.append("")
    if result.get("displacement_signals"):
        lines.append("Work an agent could take:")
        for s in result["displacement_signals"]:
            lines.append(f'  - "{s.get("phrase","")}" — {s.get("why","")}')
        lines.append("")
    if result.get("energizing"):
        lines.append("What energized you: " + "; ".join(result["energizing"]))
    if result.get("draining"):
        lines.append("What drained you: " + "; ".join(result["draining"]))
    lines.append("")
    if result.get("insight"):
        lines.append("What your words reveal:")
        lines.append("  " + result["insight"])
    if result.get("next_move"):
        lines.append("")
        lines.append("Your next move:")
        lines.append("  " + result["next_move"])
    if result.get("honest_question"):
        lines.append("")
        lines.append("A question to sit with:")
        lines.append("  " + result["honest_question"])
    lines.append("")
    lines.append("— Kairos | Built on the Knowledge Quadrant Framework by Puneet Srivastava")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# page config + CSS
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Kairos", page_icon="◈", layout="centered")

st.markdown("""
<style>
  .stApp { background-color: #0d0d0d; color: #f0ede8; }
  .stButton > button[kind="primary"] {
    background-color: #c9a84c; color: #0d0d0d; border: none;
    font-weight: 700; border-radius: 6px;
  }
  .stButton > button[kind="primary"]:hover { background-color: #b8973d; }
  .stTextArea textarea {
    background-color: #1a1a1a; color: #f0ede8;
    border: 1px solid #333; border-radius: 6px;
  }
  .stProgress > div > div > div { background-color: #c9a84c; }
  .stProgress > div > div { background-color: #2a2a2a; }
  [data-testid="stProgressBar"] > div > div > div { background-color: #c9a84c; }
  [data-testid="stProgressBar"] > div > div { background-color: #2a2a2a; }
  .stCaption { color: #888; }
  #MainMenu { visibility: hidden; }
  footer { visibility: hidden; }
  .kairos-intro-block {
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 20px 24px; margin-bottom: 12px;
  }
  .kairos-intro-label {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.15em;
    color: #c9a84c; text-transform: uppercase; margin-bottom: 6px;
  }
  .kairos-intro-body { font-size: 0.9rem; color: #aaa; line-height: 1.6; }
  [data-testid="stAudioInput"] {
    background-color: #1a1a1a !important;
    border: 1px solid #c9a84c !important;
    border-radius: 8px !important;
    min-height: 64px !important;
  }
  [data-testid="stAudioInput"] * {
    color: #f0ede8 !important;
  }
  [data-testid="stAudioInput"] svg {
    fill: #c9a84c !important;
    color: #c9a84c !important;
  }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# session init
# ---------------------------------------------------------------------------

if "code" not in st.session_state:
    st.session_state["code"] = storage.generate_code()
if "lookup_misses" not in st.session_state:
    st.session_state["lookup_misses"] = 0

code = st.session_state["code"]

# ---------------------------------------------------------------------------
# logo
# ---------------------------------------------------------------------------

try:
    logo_b64 = load_image_base64("IMG3.jpg")
    st.markdown(
        f"<div style='text-align:center;padding:32px 0 4px 0;'>"
        f"<img src='data:image/jpeg;base64,{logo_b64}' "
        f"style='height:44px;filter:invert(1);opacity:0.92;'/>"
        f"</div>",
        unsafe_allow_html=True,
    )
except Exception:
    st.markdown(
        "<h1 style='text-align:center;color:#c9a84c;letter-spacing:0.15em;'>KAIROS</h1>",
        unsafe_allow_html=True,
    )

st.markdown(
    "<p style='text-align:center;color:#555;font-size:0.75rem;"
    "letter-spacing:0.12em;margin-top:2px;margin-bottom:28px;'>"
    "KNOW WHERE YOU STAND</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# RESULT VIEW
# ---------------------------------------------------------------------------

if "result" in st.session_state:
    result = st.session_state["result"]
    transcript = st.session_state["transcript"]
    read_id = st.session_state.get("read_id")

    if result.get("_fallback"):
        st.error(result["insight"])

    # ── Persona ──
    p = fw.persona_by_name(result["dominant_persona"])
    st.subheader(f"You showed up mostly as {result['dominant_persona']}")
    if p:
        risk_pill(p["risk"])
        st.write("")
        st.write(p["desc"])
        if result.get("persona_rationale"):
            st.markdown(f"*{result['persona_rationale']}*")
        with st.expander("See all eight personas"):
            RISK_COLORS = {
                "Critical": "#c0392b", "High": "#e67e22", "Medium-High": "#e1a100",
                "Medium": "#7f8c8d", "Medium-Low": "#16a085", "Low": "#27ae60",
                "Very Low": "#2471a3", "Minimal": "#5b2c8d",
            }
            for persona in fw.PERSONAS:
                rc = RISK_COLORS.get(persona["risk"], "#7f8c8d")
                st.markdown(
                    f"**{persona['name']}** · "
                    f"<span style='color:{rc};font-size:0.8rem;'>{persona['risk']} displacement risk</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(persona["desc"])
                st.divider()

    why_text = fw.PERSONA_WHY.get(result["dominant_persona"], "")
    if why_text:
        st.markdown(f"*{why_text}*")

    # ── Quadrant blend ──
    st.markdown("#### Your quadrant blend today")
    st.caption("Values are approximate — run it on two different days and they shift.")
    for k in QUAD_ORDER:
        pct = result["quadrant_blend"][k]
        q = fw.QUADRANTS[k]
        st.markdown(
            f"**{q['label']}** &middot; ~{pct}%  \n"
            f"<span style='color:#888;font-size:0.8rem'>{q['axes']}</span>",
            unsafe_allow_html=True,
        )
        st.progress(min(pct, 100) / 100)

    # ── Displacement signals ──
    if result.get("displacement_signals"):
        st.markdown("#### Where an agent could step in")
        for s in result["displacement_signals"]:
            st.markdown(f"- \"{s.get('phrase','')}\" — *{s.get('why','')}*")

    # ── Energized / drained ──
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

    # ── Insight ──
    if result.get("insight"):
        st.markdown("#### What your words reveal")
        st.info(analyzer.enforce_second_person(result["insight"]))

    # ── Next move (Task 3) ──
    if result.get("next_move"):
        st.markdown("#### Your next move")
        st.success(analyzer.enforce_second_person(result["next_move"]))

    # ── Honest question ──
    if result.get("honest_question"):
        st.markdown("#### One question to sit with")
        st.markdown(
            f"<p style='font-size:1.05rem;color:#c9a84c;font-style:italic;'>"
            f"{analyzer.enforce_second_person(result['honest_question'])}</p>",
            unsafe_allow_html=True,
        )

    # ── Wellbeing tripwire (Task 7) ──
    if result.get("_wellbeing"):
        st.markdown("")
        st.markdown(
            "<div style='border-left:3px solid #888;padding:10px 16px;"
            "color:#aaa;font-size:0.9rem;'>"
            "Something in what you wrote suggests you might be carrying a heavy weight right now. "
            "If that's true, you don't have to carry it alone. "
            "Reaching out to someone you trust, or a support line, is a real option."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Probe questions ──
    probe_qs = _pick_probe_questions(result["quadrant_blend"], result["dominant_persona"])
    if probe_qs:
        st.markdown("#### A few things to sit with")
        for q in probe_qs:
            with st.expander("Reflect →", expanded=False):
                st.markdown(f"<p style='font-size:1.05rem'>{q}</p>", unsafe_allow_html=True)
                st.caption("You don't need to answer here. Just let it sit.")

    st.divider()

    # ── Feedback (Task 8) ──
    st.markdown("#### Did this feel accurate?")
    feedback_done = st.session_state.get("feedback_rating")
    if not feedback_done:
        fb_col1, fb_col2, fb_col3 = st.columns(3)
        with fb_col1:
            if st.button("Nailed it", use_container_width=True):
                if read_id:
                    storage.record_feedback(read_id, "nailed")
                st.session_state["feedback_rating"] = "nailed"
                st.rerun()
        with fb_col2:
            if st.button("Partly", use_container_width=True):
                if read_id:
                    storage.record_feedback(read_id, "partly")
                st.session_state["feedback_rating"] = "partly"
                st.rerun()
        with fb_col3:
            if st.button("Missed", use_container_width=True):
                if read_id:
                    storage.record_feedback(read_id, "missed")
                st.session_state["feedback_rating"] = "missed"
                st.rerun()
    else:
        st.caption(f"Thanks for the feedback.")
        fb_note = st.text_area("What did we get wrong? (optional)", key="fb_text",
                               height=80, label_visibility="visible")
        if fb_note and st.button("Send note"):
            if read_id:
                storage.record_feedback(read_id, feedback_done, fb_note)
            st.caption("Got it.")

    st.divider()

    # ── Save to history (Task 10) ──
    if not st.session_state.get("locked"):
        st.markdown(
            f"**Your code: ** `{code}`  \n"
            "<span style='font-size:0.8rem;color:#888;'>"
            "Save this code. You need it to retrieve this read later.</span>",
            unsafe_allow_html=True,
        )
        st.write("")
        if read_id and st.button("Save to my history", type="primary"):
            if storage.lock_read(read_id):
                st.session_state["locked"] = True
                st.rerun()
            else:
                st.error("Could not save. Try again.")
    else:
        st.success(f"Saved. Your code is **{code}** — keep it.")
        # PDF (Task 11)
        if "pdf_bytes" not in st.session_state and read_id:
            row = storage.get_read(read_id)
            if row:
                st.session_state["pdf_bytes"] = generate_pdf_from_row(row)
        if "pdf_bytes" in st.session_state:
            st.download_button(
                "Download as PDF",
                data=st.session_state["pdf_bytes"],
                file_name=f"kairos_{code}.pdf",
                mime="application/pdf",
            )

    # ── Summary download ──
    summary = build_summary_text(result, transcript, code)
    st.download_button(
        "Download summary (text)",
        data=summary,
        file_name=f"kairos_{code}.txt",
        mime="text/plain",
    )

    st.markdown("")
    if st.button("← Reflect on another day"):
        for k in ["result", "transcript", "read_id", "locked",
                  "feedback_rating", "fb_text", "pdf_bytes", "draft_text",
                  "audio_hash", "voice_transcribed"]:
            st.session_state.pop(k, None)
        st.rerun()


# ---------------------------------------------------------------------------
# HISTORY VIEW (Task 10 — code lookup)
# ---------------------------------------------------------------------------

elif "history_thread" in st.session_state:
    thread = st.session_state["history_thread"]
    h_code = st.session_state.get("history_code", "")

    st.markdown(f"#### Saved reads for code `{h_code}`")
    st.caption(f"{len(thread)} saved read(s), oldest first.")
    st.write("")

    for i, row in enumerate(thread):
        date_str = (row.get("created_at") or "")[:10]
        persona = row.get("persona", "unknown")
        blend = row.get("blend") or {}
        top_quad = max(blend, key=blend.get) if blend else "?"
        top_pct = blend.get(top_quad, 0)

        with st.expander(f"{date_str} — {persona}", expanded=(i == len(thread) - 1)):
            st.markdown(f"**You showed up mostly as {persona}**")
            st.caption(f"Strongest quadrant: {fw.QUADRANTS.get(top_quad, {}).get('label', top_quad)} (~{top_pct}%)")
            if row.get("insight"):
                st.info(row["insight"])
            if row.get("next_move"):
                st.success(row["next_move"])
            if row.get("honest_question"):
                st.markdown(f"*{row['honest_question']}*")

            pdf_key = f"pdf_{row['read_id']}"
            if pdf_key not in st.session_state:
                st.session_state[pdf_key] = generate_pdf_from_row(row)
            st.download_button(
                "Download PDF",
                data=st.session_state[pdf_key],
                file_name=f"kairos_{h_code}_{date_str}.pdf",
                mime="application/pdf",
                key=f"dl_{row['read_id']}",
            )

    st.write("")
    if st.button("← Start a new read"):
        for k in list(st.session_state.keys()):
            if k.startswith("pdf_"):
                del st.session_state[k]
        st.session_state.pop("history_thread", None)
        st.session_state.pop("history_code", None)
        st.rerun()


# ---------------------------------------------------------------------------
# INPUT VIEW (landing + entry)
# ---------------------------------------------------------------------------

else:

    # Background watermark
    try:
        bg_b64 = load_image_base64("IMG2.jpg")
        st.markdown(f"""
<style>
.stApp::before {{
    content: '';
    position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 600px; height: 600px;
    background-image: url('data:image/jpeg;base64,{bg_b64}');
    background-size: contain; background-repeat: no-repeat;
    background-position: center;
    opacity: 0.05; z-index: 0; pointer-events: none;
}}
</style>""", unsafe_allow_html=True)
    except Exception:
        pass

    # ── Session code (Task 10) ──
    st.markdown(
        f"<div style='text-align:right;margin-bottom:4px;'>"
        f"<span style='font-size:0.75rem;color:#555;'>Your code: </span>"
        f"<span style='font-family:monospace;color:#c9a84c;font-size:0.85rem;"
        f"background:#1a1a1a;padding:2px 8px;border-radius:4px;'>{code}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if not st.session_state.get("code_warned"):
        st.session_state["code_warned"] = True
        st.info("Save your code. It is the only way to retrieve your reads later. There is no account, no login, no recovery.")

    # ── Have a code? (Task 10) ──
    with st.expander("Have a code from a previous session?"):
        if st.session_state["lookup_misses"] >= 5:
            st.warning("Too many failed lookups this session. Refresh to try again.")
        else:
            entered = st.text_input("Enter your code", placeholder="KQ-XXXXXXXX",
                                    key="code_input")
            if st.button("Load my history"):
                entered = entered.strip().upper()
                if not entered:
                    st.error("Enter a code first.")
                else:
                    try:
                        thread = storage.get_thread(entered)
                        if thread:
                            st.session_state["history_thread"] = thread
                            st.session_state["history_code"] = entered
                            st.rerun()
                        else:
                            st.session_state["lookup_misses"] += 1
                            remaining = 5 - st.session_state["lookup_misses"]
                            st.error(
                                f"No saved reads found for that code. "
                                f"({remaining} attempt(s) remaining this session.)"
                            )
                    except storage.StorageError as e:
                        st.session_state["lookup_misses"] += 1
                        st.error(str(e))

    st.divider()

    # ── Educational blocks (Task 2) ──
    st.markdown(
        "<div class='kairos-intro-block'>"
        "<div class='kairos-intro-label'>What this is</div>"
        "<div class='kairos-intro-body'>"
        "A mirror for one day you describe, read through the Knowledge Quadrant Framework. "
        "It maps where your work sits across four zones defined by two axes: "
        "whether your knowledge is explicit or tacit, and whether your output demands accuracy or originality. "
        "The reading tells you where you spent today and what that means for your relationship with AI displacement."
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='kairos-intro-block'>"
        "<div class='kairos-intro-label'>What this is not</div>"
        "<div class='kairos-intro-body'>"
        "Not a test. Not a score. Not a prediction, and not a verdict on who you are. "
        "Run it on two days and it reads differently, because your days differ. "
        "No number here tells you what you are worth."
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='kairos-intro-block'>"
        "<div class='kairos-intro-label'>How to use it well</div>"
        "<div class='kairos-intro-body'>"
        "Write the messy truth. Name your decisions. Name what drained or energized you. "
        "Do not perform for it. The more honest the input, the sharper the mirror."
        "</div></div>",
        unsafe_allow_html=True,
    )

    st.write("")

    # ── Voice input — only when a backend is available ──
    _vb = _voice_backend()
    if _vb is not None:
        if _vb == "groq":
            _voice_copy = (
                "Your recording is sent to Groq only to transcribe it, then dropped. "
                "Kairos never stores the audio. "
                "The transcript is saved under your code, with no name, email, or IP attached."
            )
        else:
            _voice_copy = "Audio is transcribed on this machine and never leaves it."
        st.markdown(
            "<p style='font-size:1.15rem;font-weight:700;color:#c9a84c;"
            "margin-bottom:4px;'>Record your day</p>"
            f"<p style='font-size:0.8rem;color:#888;margin-top:0;'>{_voice_copy}</p>",
            unsafe_allow_html=True,
        )
        try:
            audio_value = st.audio_input("Record your day", label_visibility="collapsed")
            if audio_value is not None:
                audio_bytes = audio_value.getvalue()
                audio_hash = hashlib.sha256(audio_bytes).hexdigest()
                if audio_hash != st.session_state.get("audio_hash"):
                    with st.spinner("Transcribing..."):
                        try:
                            transcribed = _transcribe(audio_bytes)
                            st.session_state["audio_hash"] = audio_hash
                            st.session_state["draft_text"] = transcribed
                            st.session_state["voice_transcribed"] = True
                            st.rerun()
                        except RuntimeError as _err:
                            st.error(f"Could not transcribe: {_err}. Type your day below instead.")
                        finally:
                            # Let audio_bytes go out of scope immediately.
                            del audio_bytes
        except AttributeError:
            pass  # st.audio_input not available in this Streamlit build

    # ── Chip prompts ──
    CHIPS = [
        "What took the most energy today?",
        "What decision did only you make?",
        "What felt mechanical — something a tool could have done?",
        "When did you feel most irreplaceable today?",
        "What would have broken if you weren't there?",
    ]
    st.caption("Not sure where to start? Pick a prompt:")
    chip_cols = st.columns(len(CHIPS))
    for i, chip in enumerate(CHIPS):
        with chip_cols[i]:
            if st.button(chip, key=f"chip_{i}", use_container_width=True):
                st.session_state["draft_text"] = chip
                st.rerun()

    # ── Text area ──
    if st.session_state.get("voice_transcribed"):
        st.caption(
            "Transcribed. Read it back, fix anything, "
            "cut anything you did not mean to say. Then read your day."
        )
    transcript = st.text_area(
        label="Your day",
        height=260,
        value=st.session_state.get("draft_text", ""),
        placeholder=(
            "Start anywhere. What is on your mind? "
            "It could be your whole day, one moment that stood out, "
            "a decision you made, something that energized you or drained you. "
            "There is no wrong way to begin."
        ),
        label_visibility="collapsed",
        key="transcript_input",
    )
    # Keep draft_text in sync with manual edits so rerun doesn't wipe it
    if transcript:
        st.session_state["draft_text"] = transcript

    word_count = len(transcript.strip().split()) if transcript.strip() else 0
    if word_count == 0:
        pass
    elif word_count < 50:
        st.caption(f"{word_count} words — keep going, the more you share the sharper the insight.")
    elif word_count < 150:
        st.caption(f"{word_count} words — good, you're in the zone.")
    else:
        st.caption(f"{word_count} words — that's plenty. Submit when ready.")

    # ── Submit ──
    go = st.button("Read my day", type="primary", use_container_width=True)
    if go:
        ok, msg = _stage1_validate(transcript)
        if not ok:
            st.warning(msg)
            st.stop()
        with st.spinner("Reading your day through the four quadrants..."):
            result = analyzer.analyze(transcript)
        st.session_state["result"] = result
        st.session_state["transcript"] = transcript
        read_id = storage.save_read(
            code,
            mode="professional",
            persona=result["dominant_persona"],
            blend=result["quadrant_blend"],
            signals=result.get("displacement_signals", []),
            insight=result.get("insight", ""),
            next_move=result.get("next_move", ""),
            honest_question=result.get("honest_question", ""),
            transcript=transcript,
            locked=False,
        )
        st.session_state["read_id"] = read_id
        st.session_state.pop("draft_text", None)
        st.session_state.pop("voice_transcribed", None)
        st.rerun()

    _is_cloud = bool(os.environ.get("DATABASE_URL"))
    _storage_note = (
        "Your transcript is sent to Claude to analyze and stored anonymously under your code. "
        "No name, email, or IP is collected."
        if _is_cloud else
        "Your transcript is analyzed locally and stored on this machine under your code. "
        "Nothing leaves."
    )
    st.markdown(
        f"<p style='text-align:center;color:#444;font-size:0.75rem;margin-top:32px;'>"
        f"No login. No account. {_storage_note}</p>",
        unsafe_allow_html=True,
    )
