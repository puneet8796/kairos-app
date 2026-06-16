"""
student_framework.py
Kairos Student — framework for self-inquiry
designed for teenagers and early college students.
"""

STUDENT_PERSONAS = [
    {
        "name": "The Wave Rider",
        "mode": "Passive + External",
        "color": "#5B8CCC",
        "desc": (
            "You're moving through the day with the current — doing what's expected, "
            "going where it takes you. That's not failure. But somewhere in you, "
            "there's a direction that's yours alone."
        ),
        "signal_words": [
            "had to", "was supposed to", "just", "because", "had no choice",
            "assigned", "required", "told to",
        ],
        "growth_edge": "Intentionality",
        "expansion": (
            "Tomorrow, choose one moment that's entirely yours — not assigned, "
            "not expected. Even five minutes counts."
        ),
        "celebration": "That's the first ripple you made today. Ripples become waves.",
    },
    {
        "name": "The Main Attraction",
        "mode": "Active + External",
        "color": "#E8A838",
        "desc": (
            "You show up and you show up hard. You know how to perform when it matters "
            "— and it usually shows. The question worth sitting with: whose stage are "
            "you building yourself for?"
        ),
        "signal_words": [
            "grade", "looks good", "GPA", "resume", "college", "they'll see",
            "impressed", "noticed", "ranking",
        ],
        "growth_edge": "Direction",
        "expansion": (
            "Do one thing tonight with zero audience. No grade. No post. "
            "Just you and the thing."
        ),
        "celebration": "You just did something for you. That's a different kind of win.",
    },
    {
        "name": "The Learned",
        "mode": "Passive + Internal",
        "color": "#7B68C8",
        "desc": (
            "You think more than most people realize. You notice things, sit with ideas, "
            "let questions live in your head. The potential here is the highest of all "
            "four zones. The gap is just courage — and that's the smallest gap to close."
        ),
        "signal_words": [
            "interesting", "I wonder", "read about", "thinking about",
            "never tried", "not sure how", "someday", "maybe",
        ],
        "growth_edge": "Courage to create",
        "expansion": (
            "Pick the most interesting thought you had today. Tell one person about it "
            "— a friend, a parent, anyone. Just say it out loud."
        ),
        "celebration": "You turned a thought into an action. That's exactly how it starts.",
    },
    {
        "name": "The Builder",
        "mode": "Active + Internal",
        "color": "#4CAF82",
        "desc": (
            "You follow curiosity into action. You make things, try things, ask things "
            "nobody assigned you to ask. This is the zone that compounds — the things "
            "you build here become the things that define you later."
        ),
        "signal_words": [
            "built", "tried", "asked", "figured out", "wanted to know",
            "decided to", "made", "created", "worked on", "explored",
        ],
        "growth_edge": "Connection",
        "expansion": (
            "Whatever you're thinking about or building — show one person today. "
            "Not for feedback. Just to make it real outside your head."
        ),
        "celebration": "One more thing built. Keep going.",
    },
]

STUDENT_CHIPS = [
    "What's something you learned today that actually surprised you?",
    "Who did you talk to today — and what did you walk away thinking about?",
    "What did you spend time on that nobody asked you to?",
    "When did you feel most alive today — and when most bored?",
    "What question are you carrying around that you haven't answered yet?",
]

STUDENT_AXES = {
    "passive_active": {
        "passive": "Taking in, following, absorbing, reacting",
        "active": "Initiating, creating, questioning, building",
    },
    "external_internal": {
        "external": "Driven by grades, approval, requirements, what others expect",
        "internal": "Driven by curiosity, genuine interest, self-direction",
    },
}

STUDENT_PERSONA_NAMES = [p["name"] for p in STUDENT_PERSONAS]


def student_persona_by_name(name: str):
    for p in STUDENT_PERSONAS:
        if p["name"].lower() == name.lower():
            return p
    return None


def build_student_prompt(transcript: str) -> str:
    persona_lines = "\n".join(
        f"- {p['name']} [{p['mode']}]: {p['desc']}"
        for p in STUDENT_PERSONAS
    )
    signal_lines = "\n".join(
        f"- {p['name']}: " + ", ".join(p["signal_words"])
        for p in STUDENT_PERSONAS
    )

    return f"""You are a warm, honest mentor reading a student's description of their day. Your job is to give them genuine, kind, growth-oriented feedback — not a score. Be encouraging but truthful. Never preachy. Speak like a trusted older friend who sees them clearly.

THE FOUR STUDENT MODES:
{persona_lines}

SIGNAL LANGUAGE TO WATCH FOR:
{signal_lines}

Read the student's account of their day. Then return ONLY a JSON object with this exact shape and nothing else:

{{
  "mode_blend": {{
    "wave_rider": 0-100,
    "main_attraction": 0-100,
    "the_learned": 0-100,
    "the_builder": 0-100
  }},
  "dominant_persona": "<one of the four names exactly>",
  "what_is_working": [
    "<positive observation 1 — specific, from their own words>",
    "<positive observation 2>"
  ],
  "growth_observations": [
    "<kind, honest growth note 1>",
    "<kind, honest growth note 2>"
  ],
  "insight": "<2 sentences, warm and honest, what their day reveals about who they are becoming>",
  "honest_question": "<one question, curious not heavy, to sit with>"
}}

Rules:
- mode_blend must sum to 100
- dominant_persona must be one of the four names exactly as written
- what_is_working must be genuinely positive — find something real, not generic
- growth_observations must be kind and specific — never harsh
- Quote their own words when possible
- No preamble, no markdown, no text outside the JSON

THE STUDENT'S DAY:
\"\"\"{transcript.strip()}\"\"\"
"""
