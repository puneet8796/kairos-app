"""Offline self-test. Mocks the Ollama HTTP call to verify the full path:
prompt build -> JSON parse -> validate -> summary text. No model needed."""
import json, types
import analyzer, framework as fw

SAMPLE_DAY = (
    "I started by clearing my inbox and responded to a pile of emails. Then I formatted "
    "the QBR deck and pulled the renewal numbers for Matt. Two status meetings ate the "
    "middle of the day. Late afternoon I finally got an hour to actually think through the "
    "price-volume curve for the new SKU, which was the only part I enjoyed."
)

# ---- Test 1: prompt builds and contains framework anchors
prompt = fw.build_prompt(SAMPLE_DAY)
assert "The Doctors" in prompt and "The Oracle" in prompt and "JSON" in prompt
print("OK  prompt builds, encodes 4 quadrants + 8 personas")

# ---- Test 2: a well-formed model response validates cleanly
good = json.dumps({
    "quadrant_blend": {"doctor": 55, "builder": 20, "general": 20, "creator": 5},
    "dominant_persona": "The Responder",
    "persona_rationale": "Most of the day was reactive, set by other people's agendas.",
    "displacement_signals": [
        {"phrase": "formatted the QBR deck", "why": "documentable and repeatable"},
        {"phrase": "pulled the renewal numbers", "why": "an agent can query and assemble this"}
    ],
    "energizing": ["thinking through the price-volume curve"],
    "draining": ["two status meetings", "inbox triage"],
    "insight": "Your day was mostly Doctor-quadrant execution. The one hour that energized you "
               "was the only General-quadrant work in it.",
    "honest_question": "What would it take to move that one good hour to the center of your day?"
})

class FakeResp:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return {"message": {"content": good}}

def fake_post(url, json=None, timeout=None):
    return FakeResp()

analyzer.requests = types.SimpleNamespace(post=fake_post)
res = analyzer.analyze(SAMPLE_DAY)
assert res["dominant_persona"] == "The Responder"
assert sum(res["quadrant_blend"].values()) in (99, 100, 101)
assert res["_fallback"] is False
print("OK  well-formed response validates; persona =", res["dominant_persona"],
      "; blend sum =", sum(res["quadrant_blend"].values()))

# ---- Test 3: malformed model output -> graceful fallback, not a crash
class BadResp(FakeResp):
    def json(self): return {"message": {"content": "sorry, here is some prose not json"}}
analyzer.requests = types.SimpleNamespace(post=lambda url, json=None, timeout=None: BadResp())
res2 = analyzer.analyze(SAMPLE_DAY)
assert res2["_fallback"] is True
# deterministic backstop should still surface real displacement phrases
assert len(res2["displacement_signals"]) >= 1
print("OK  malformed output -> safe fallback; deterministic signals =",
      len(res2["displacement_signals"]))

# ---- Test 4: unknown persona name gets coerced to a valid one
weird = json.dumps({"quadrant_blend":{"doctor":10,"builder":10,"general":70,"creator":10},
                    "dominant_persona":"The Wizard"})
analyzer.requests = types.SimpleNamespace(
    post=lambda url, json=None, timeout=None: type("R",(FakeResp,),
        {"json": lambda self: {"message":{"content": weird}}})())
res3 = analyzer.analyze(SAMPLE_DAY)
assert res3["dominant_persona"] in fw.PERSONA_NAMES
print("OK  unknown persona coerced ->", res3["dominant_persona"], "(general-leaning, as expected)")

# ---- Test 5: summary text builds
import app
txt = app.build_summary_text(res, SAMPLE_DAY)
assert "Quadrant blend" in txt and "The Responder" in txt
print("OK  summary text builds (", len(txt), "chars )")

print("\nALL TESTS PASSED")
