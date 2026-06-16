"""
analyzer.py
Talks to the local Ollama model, validates the structured result, and degrades
gracefully if the model returns malformed output. Nothing leaves the machine.
"""

import json
import os
import re

import requests

import anthropic

import framework as fw

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))


def _extract_json(text: str):
    """Pull the first balanced JSON object out of a model response."""
    if not text:
        return None
    # Fast path
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find the first {...} block, brace-balanced
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    return None
    return None


def _normalize_blend(blend):
    keys = ["doctor", "builder", "general", "creator"]
    clean = {}
    for k in keys:
        try:
            clean[k] = max(0.0, float(blend.get(k, 0)))
        except Exception:
            clean[k] = 0.0
    total = sum(clean.values())
    if total <= 0:
        return {k: 25 for k in keys}
    return {k: round(v / total * 100) for k, v in clean.items()}


def _deterministic_displacement(transcript: str):
    """Cheap backstop: surface displacement verbs the person actually used."""
    found = []
    low = transcript.lower()
    for verb in fw.DISPLACEMENT_VERBS:
        idx = low.find(verb)
        if idx != -1:
            # grab a little context around the hit
            s = max(0, idx - 15)
            e = min(len(transcript), idx + len(verb) + 20)
            snippet = transcript[s:e].strip()
            found.append({"phrase": snippet, "why": "Documentable, repeatable, agent-ready."})
        if len(found) >= 5:
            break
    return found


def enforce_second_person(text):
    if not text:
        return text
    replacements = [
        ("Their day", "Your day"),
        ("their day", "your day"),
        ("They spend", "You spend"),
        ("They spent", "You spent"),
        ("They make", "You make"),
        ("They made", "You made"),
        ("They are", "You are"),
        ("They were", "You were"),
        ("They have", "You have"),
        ("They had", "You had"),
        ("They do", "You do"),
        ("They did", "You did"),
        ("They feel", "You feel"),
        ("They felt", "You felt"),
        ("They recognize", "You recognize"),
        ("They connect", "You connect"),
        ("They design", "You design"),
        ("They rely", "You rely"),
        ("They work", "You work"),
        ("their work", "your work"),
        ("their role", "your role"),
        ("their judgment", "your judgment"),
        ("their time", "your time"),
        ("their skills", "your skills"),
        ("their ability", "your ability"),
        ("their focus", "your focus"),
        ("their day", "your day"),
        ("the person", "you"),
        ("The person", "You"),
        ("How do they", "How do you"),
        ("How can they", "How can you"),
        ("How much of their", "How much of your"),
        ("How much of the person", "How much of your"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _validate(result, transcript):
    """Coerce a raw dict into a safe, complete result the UI can render."""
    result = result or {}

    blend = _normalize_blend(result.get("quadrant_blend", {}))

    persona = result.get("dominant_persona", "")
    if not fw.persona_by_name(persona):
        # fall back to the persona implied by the dominant quadrant
        dominant_quad = max(blend, key=blend.get)
        match = next((p for p in fw.PERSONAS if p["lean"] == dominant_quad), fw.PERSONAS[3])
        persona = match["name"]

    signals = result.get("displacement_signals") or []
    if not isinstance(signals, list) or not signals:
        signals = _deterministic_displacement(transcript)

    def _as_list(v):
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    return {
        "quadrant_blend": blend,
        "dominant_persona": persona,
        "displacement_signals": signals[:6],
        "energizing": [enforce_second_person(x) for x in _as_list(result.get("energizing"))],
        "draining": [enforce_second_person(x) for x in _as_list(result.get("draining"))],
        "insight": enforce_second_person(str(result.get("insight", "")).strip()),
        "honest_question": enforce_second_person(str(result.get("honest_question", "")).strip()),
        "_model": OLLAMA_MODEL,
        "_fallback": result.get("_fallback", False),
    }


def analyze_via_claude(transcript: str):
    """Use Claude Haiku when ANTHROPIC_API_KEY is available."""
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"]
    )
    prompt = fw.build_prompt(transcript)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    content = message.content[0].text
    parsed = _extract_json(content)
    if parsed is None:
        raise ValueError(
            "Claude did not return valid JSON"
        )
    return _validate(parsed, transcript)


def analyze_student_via_claude(transcript: str):
    """Student analysis via Claude API."""
    import student_framework as sf
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"]
    )
    prompt = sf.build_student_prompt(transcript)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    content = message.content[0].text
    parsed = _extract_json(content)
    if parsed is None:
        raise ValueError(
            "Claude did not return valid JSON"
        )
    return _validate_student(parsed, transcript)


def _validate_student(result, transcript):
    """Validate and clean student result."""
    result = result or {}

    keys = [
        "wave_rider", "main_attraction",
        "the_learned", "the_builder",
    ]
    blend = {}
    for k in keys:
        try:
            blend[k] = max(
                0.0,
                float(result.get("mode_blend", {}).get(k, 0))
            )
        except Exception:
            blend[k] = 0.0
    total = sum(blend.values())
    if total <= 0:
        blend = {k: 25 for k in keys}
    else:
        blend = {k: round(v / total * 100) for k, v in blend.items()}

    persona = result.get("dominant_persona", "")
    import student_framework as sf
    if not sf.student_persona_by_name(persona):
        dominant = max(blend, key=blend.get)
        mapping = {
            "wave_rider": "The Wave Rider",
            "main_attraction": "The Main Attraction",
            "the_learned": "The Learned",
            "the_builder": "The Builder",
        }
        persona = mapping.get(dominant, "The Wave Rider")

    def _as_list(v):
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    return {
        "mode_blend": blend,
        "dominant_persona": persona,
        "what_is_working": _as_list(result.get("what_is_working")),
        "growth_observations": _as_list(result.get("growth_observations")),
        "insight": str(result.get("insight", "")).strip(),
        "honest_question": str(result.get("honest_question", "")).strip(),
        "_mode": "student",
    }


def analyze_student(transcript: str):
    """Entry point for student analysis."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return analyze_student_via_claude(transcript)
        except Exception:
            pass
    return {
        "mode_blend": {
            "wave_rider": 25,
            "main_attraction": 25,
            "the_learned": 25,
            "the_builder": 25,
        },
        "dominant_persona": "The Learned",
        "what_is_working": [
            "You showed up and reflected.",
            "That alone puts you ahead.",
        ],
        "growth_observations": [
            "The model was unavailable.",
            "Try again in a moment.",
        ],
        "insight": "Analysis unavailable.",
        "honest_question": "",
        "_mode": "student",
        "_fallback": True,
    }


def analyze(transcript: str):
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return analyze_via_claude(
                transcript
            )
        except Exception as e:
            st_fallback = {
                "quadrant_blend": {
                    "doctor": 25,
                    "builder": 25,
                    "general": 25,
                    "creator": 25
                },
                "dominant_persona":
                    "The Utility Player",
                "persona_rationale":
                    "API error — neutral placeholder.",
                "displacement_signals":
                    _deterministic_displacement(
                        transcript
                    ),
                "energizing": [],
                "draining": [],
                "insight":
                    f"API error: {e}",
                "honest_question": "",
                "_fallback": True,
            }
            return _validate(
                st_fallback, transcript
            )

    # Original Ollama path follows
    # — leave everything below unchanged
    prompt = fw.build_prompt(transcript)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",          # Ollama: force valid JSON
        "options": {"temperature": 0.3},
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        r.raise_for_status()
        body = r.json()
        content = body.get("message", {}).get("content", "")
        parsed = _extract_json(content)
        if parsed is None:
            raise ValueError("Model did not return parseable JSON.")
        return _validate(parsed, transcript)
    except Exception as e:
        # Honest degraded mode: deterministic signals + a clear note.
        fallback = {
            "quadrant_blend": {"doctor": 25, "builder": 25, "general": 25, "creator": 25},
            "dominant_persona": "The Utility Player",
            "persona_rationale": "Model output was unavailable, so this is a neutral placeholder.",
            "displacement_signals": _deterministic_displacement(transcript),
            "energizing": [],
            "draining": [],
            "insight": f"The local model could not be reached or returned bad output ({e}). "
                       "Check that Ollama is running and the model is pulled.",
            "honest_question": "",
            "_fallback": True,
        }
        return _validate(fallback, transcript)
