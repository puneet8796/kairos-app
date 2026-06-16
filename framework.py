"""
framework.py
The Knowledge Quadrant Framework, encoded.
"""

AXES = {
    "knowledge": {
        "explicit": "Documented, trainable, searchable. The kind AI can replicate.",
        "tacit": "Judgment, pattern recognition, contextual instinct earned by living "
                 "through real situations. You cannot Google it or prompt for it.",
    },
    "output": {
        "accuracy": "There is a right answer. The standard is verifiable. Being wrong "
                    "has real consequences.",
        "originality": "There is no right answer. The value lives entirely in the "
                       "freshness of what you produce.",
    },
}

QUADRANTS = {
    "doctor": {
        "label": "The Doctors",
        "axes": "Explicit knowledge, accuracy required",
        "desc": "Surgeons, lawyers, analysts, engineers writing production code. "
                "High stakes, verifiable output. AI is entering this room fastest.",
    },
    "builder": {
        "label": "The Builders",
        "axes": "Explicit knowledge, originality required",
        "desc": "Marketers, designers, copywriters, product communicators. "
                "Pattern-based creativity at scale. AI is displacing the volume tier first.",
    },
    "general": {
        "label": "The Generals",
        "axes": "Tacit knowledge, accuracy required",
        "desc": "Strategists, senior leaders, negotiators, advisors. Consequential calls "
                "on incomplete information. The human premium zone, and it is growing.",
    },
    "creator": {
        "label": "The Creators",
        "axes": "Tacit knowledge, originality required",
        "desc": "Beethoven deaf at the Ninth. Einstein and his thought experiments. "
                "This quadrant creates history. AI can assist but cannot originate.",
    },
}

PERSONAS = [
    {
        "name": "The Doer",
        "risk": "Critical",
        "lean": "doctor",
        "desc": "Executes reliably on defined tasks. The agenda is always set by someone else.",
    },
    {
        "name": "The Responder",
        "risk": "High",
        "lean": "doctor",
        "desc": "Responds to what lands in front of them. Fast and accurate, but reactive by design.",
    },
    {
        "name": "The Craftsman",
        "risk": "Medium-High",
        "lean": "builder",
        "desc": "Deep technical skill and genuine craft, but mostly in execution mode. "
                "Disconnected from the judgment layer.",
    },
    {
        "name": "The Utility Player",
        "risk": "Medium",
        "lean": "mixed",
        "desc": "Reliable across many domains but rarely the deepest expert in any one of them.",
    },
    {
        "name": "The Architect",
        "risk": "Medium-Low",
        "lean": "builder",
        "desc": "Designs systems and builds consensus. Works across teams to make things hold together.",
    },
    {
        "name": "The Strategist",
        "risk": "Low",
        "lean": "general",
        "desc": "Makes consequential calls on incomplete information using judgment earned over years.",
    },
    {
        "name": "The Visionary",
        "risk": "Very Low",
        "lean": "creator",
        "desc": "Thinks in futures and patterns. Generates ideas that others eventually catch up to.",
    },
    {
        "name": "The Oracle",
        "risk": "Minimal",
        "lean": "creator",
        "desc": "The institutional memory and interpretive lens that others rely on without always knowing it.",
    },
]

PERSONA_NAMES = [p["name"] for p in PERSONAS]

PERSONA_WHY = {
    "The Doer":           "Executes reliably on defined tasks. The agenda is always set by someone else.",
    "The Responder":      "Responds to what lands in front of them. Fast and accurate, but reactive by design.",
    "The Craftsman":      "Deep technical skill and genuine craft, but mostly in execution mode. Disconnected from the judgment layer.",
    "The Utility Player": "Reliable across many domains but rarely the deepest expert in any one of them.",
    "The Architect":      "Designs systems and builds consensus. Works across teams to make things hold together.",
    "The Strategist":     "Makes consequential calls on incomplete information using judgment earned over years.",
    "The Visionary":      "Thinks in futures and patterns. Generates ideas that others eventually catch up to.",
    "The Oracle":         "The institutional memory and interpretive lens that others rely on without always knowing it.",
}

DISPLACEMENT_VERBS = [
    "formatted", "pulled", "compiled", "collated", "responded to", "replied",
    "updated the", "copied", "pasted", "filled in", "logged", "entered",
    "summarized", "scheduled", "forwarded", "cleaned up", "reformatted",
    "transcribed", "sorted", "tagged", "uploaded", "downloaded", "exported",
    "reconciled", "checked the box", "followed up", "chased", "status update",
]


def persona_by_name(name: str):
    for p in PERSONAS:
        if p["name"].lower() == str(name).lower():
            return p
    return None


def build_prompt(transcript: str) -> str:
    """Build the analysis instruction sent to the model."""
    quad_lines = "\n".join(
        f"- {v['label']} ({k}): {v['axes']}. {v['desc']}"
        for k, v in QUADRANTS.items()
    )
    persona_lines = "\n".join(
        f"- {p['name']} [{p['risk']} risk]: {p['desc']}" for p in PERSONAS
    )
    verbs = ", ".join(DISPLACEMENT_VERBS)

    return f"""You are an analyst applying the Knowledge Quadrant Framework to a person's
description of their actual workday. Be honest, not flattering. The point of this tool
is an accurate mirror, not encouragement.

THE FOUR QUADRANTS:
{quad_lines}

THE EIGHT PERSONAS (highest to lowest AI displacement risk):
{persona_lines}

DISPLACEMENT-LANGUAGE SIGNALS (work that is documentable and delegable to an AI agent):
{verbs}

IMPORTANT: Write ALL text fields in second person. Address the user directly as "you". Never use "they", "their", "the person", or any third-person reference. The insight field must begin with "Your" or "You". The question field must begin with "How" or "What" or "Are" and address "you" directly.

Read the person's account of their day below. Then return ONLY a JSON object with this
exact shape and nothing else:

{{
  "quadrant_blend": {{"doctor": 0-100, "builder": 0-100, "general": 0-100, "creator": 0-100}},
  "dominant_persona": "<one of the eight persona names, exactly as written>",
  "displacement_signals": [
    {{"phrase": "<short quote copied exactly from the person's words>", "why": "<why an agent could do this>"}}
  ],
  "energizing": ["<explicit emotional signal only — satisfaction, excitement, meaning. If none exists: 'No clear energizer mentioned.'>"],
  "draining": ["<explicit emotional signal only — frustration, tedium, obligation. If none exists: 'No clear drain mentioned.'>"],
  "insight": "<2 to 3 sentences in second person, addressing the user directly — use 'you' and 'your', never 'they' or 'their'>",
  "next_move": "<one short, concrete action tied to the user's lowest-present quadrant — specific, actionable, starts with a verb>",
  "honest_question": "<one direct question for the user — use 'you', never 'they'>"
}}

Rules:
- quadrant_blend percentages must sum to 100.
- dominant_persona must be one of the eight names exactly.
- Quote the person's own words verbatim in displacement_signals; do not invent or paraphrase. Only include a signal if the exact phrase appears in their text.
- If the day is light on displacement signals, say so honestly with an empty or short list.
- next_move must name the quadrant the user is thinnest in and give one concrete thing they could do — not advice about being more strategic in general.
- Write all insight copy, energized/drained observations, and the closing question directly to the user in second person. Use "you" and "your" throughout. Never use "they", "their", or "the person".
- Identify what energized and what drained the user today based only on emotional or evaluative language in the narrative. Do NOT infer energy from neutral activity descriptions. If no explicit emotional signal exists, return "No clear energizer mentioned." or "No clear drain mentioned."
- No preamble, no markdown, no text outside the JSON.

THE PERSON'S DAY:
\"\"\"{transcript.strip()}\"\"\"
"""
