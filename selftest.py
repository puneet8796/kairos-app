"""
Offline self-test. Mocks the Ollama HTTP call to verify the full path:
prompt build -> JSON parse -> validate -> summary text.
No model needed. No network required.
"""

import json
import os
import tempfile
import types

# Force SQLite (no Postgres) and a throwaway db for storage tests
_tmp_db = tempfile.mktemp(suffix=".db")
os.environ["KAIROS_DB_PATH"] = _tmp_db
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ANTHROPIC_API_KEY", None)  # ensure Ollama path is used in analyze()

import analyzer
import framework as fw
import storage

SAMPLE_DAY = (
    "I started by clearing my inbox and responded to a pile of emails. Then I formatted "
    "the QBR deck and pulled the renewal numbers for Matt. Two status meetings ate the "
    "middle of the day. Late afternoon I finally got an hour to actually think through the "
    "price-volume curve for the new SKU, which was the only part I enjoyed."
)

# ---- Test 1: prompt builds and contains framework anchors + next_move ----
prompt = fw.build_prompt(SAMPLE_DAY)
assert "The Doctors" in prompt and "The Oracle" in prompt and "JSON" in prompt
assert "next_move" in prompt, "Prompt must include next_move in the JSON schema"
print("OK  prompt builds, encodes 4 quadrants + 8 personas + next_move")

# ---- Test 2: well-formed response validates cleanly ----
good = json.dumps({
    "quadrant_blend": {"doctor": 55, "builder": 20, "general": 20, "creator": 5},
    "dominant_persona": "The Responder",
    "persona_rationale": "Most of the day was reactive, set by other people's agendas.",
    "displacement_signals": [
        {"phrase": "formatted the QBR deck", "why": "documentable and repeatable"},
        {"phrase": "pulled the renewal numbers", "why": "an agent can query and assemble this"},
        {"phrase": "invented phrase not in transcript at all", "why": "this must be stripped"},
    ],
    "energizing": ["thinking through the price-volume curve"],
    "draining": ["two status meetings", "inbox triage"],
    "insight": "Your day was mostly Doctor-quadrant execution. The one hour that energized you "
               "was the only General-quadrant work in it.",
    "next_move": "Block one hour tomorrow exclusively for General-quadrant work — a decision only you can make.",
    "honest_question": "What would it take to move that one good hour to the center of your day?",
})


class FakeResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": good}}


def fake_post(url, json=None, timeout=None):
    return FakeResp()


analyzer.requests = types.SimpleNamespace(post=fake_post)
res = analyzer.analyze(SAMPLE_DAY)
assert res["dominant_persona"] == "The Responder"
assert res["_fallback"] is False
# Blend values must all be multiples of 5
assert all(v % 5 == 0 for v in res["quadrant_blend"].values()), \
    f"Blend values must be multiples of 5: {res['quadrant_blend']}"
# Sum should be roughly 100
blend_sum = sum(res["quadrant_blend"].values())
assert abs(blend_sum - 100) <= 15, f"Blend sum too far from 100: {blend_sum}"
assert res.get("next_move"), "next_move must be present in validated result"
print("OK  well-formed response validates; persona =", res["dominant_persona"],
      "; blend =", res["quadrant_blend"], "; blend sum =", blend_sum)

# ---- Test 3: grounding — invented quote is stripped ----
phrases = [s["phrase"] for s in res["displacement_signals"]]
assert not any("invented" in p.lower() for p in phrases), \
    f"Grounding check: invented quote should be stripped but found in: {phrases}"
assert any("formatted the QBR deck" in p for p in phrases), \
    "Grounding check: real quote 'formatted the QBR deck' should be kept"
assert any("pulled the renewal numbers" in p for p in phrases), \
    "Grounding check: real quote 'pulled the renewal numbers' should be kept"
print("OK  grounding check: invented quote stripped, real quotes kept;",
      "signals =", [s["phrase"] for s in res["displacement_signals"]])

# ---- Test 4: malformed model output -> graceful fallback ----
class BadResp(FakeResp):
    def json(self):
        return {"message": {"content": "sorry, here is some prose not json"}}


analyzer.requests = types.SimpleNamespace(post=lambda url, json=None, timeout=None: BadResp())
res2 = analyzer.analyze(SAMPLE_DAY)
assert res2["_fallback"] is True
assert len(res2["displacement_signals"]) >= 1
print("OK  malformed output -> safe fallback; deterministic signals =",
      len(res2["displacement_signals"]))

# ---- Test 5: unknown persona name gets coerced to a valid one ----
weird = json.dumps({
    "quadrant_blend": {"doctor": 10, "builder": 10, "general": 70, "creator": 10},
    "dominant_persona": "The Wizard",
    "next_move": "Do something.",
})
analyzer.requests = types.SimpleNamespace(
    post=lambda url, json=None, timeout=None: type("R", (FakeResp,),
        {"json": lambda self: {"message": {"content": weird}}})()
)
res3 = analyzer.analyze(SAMPLE_DAY)
assert res3["dominant_persona"] in fw.PERSONA_NAMES
print("OK  unknown persona coerced ->", res3["dominant_persona"])

# ---- Test 6: wellbeing tripwire fires on distress language ----
distress_day = "I just feel like I want to end my life, everything is pointless today."
normal_day = "I had a busy day with meetings and finished a report."
assert analyzer.check_wellbeing(distress_day), "Wellbeing tripwire should fire on distress language"
assert not analyzer.check_wellbeing(normal_day), "Wellbeing tripwire should NOT fire on normal text"
print("OK  wellbeing tripwire: fires on distress, silent on normal text")

# ---- Test 7: summary text builds with next_move and code ----
import app
txt = app.build_summary_text(res, SAMPLE_DAY, code="KQ-TEST1234")
assert "Quadrant blend" in txt and "The Responder" in txt
assert "KQ-TEST1234" in txt, "Summary must include the session code"
assert "next move" in txt.lower(), "Summary must include next move section"
print("OK  summary text builds (", len(txt), "chars )")

# ---- Test 8: storage round-trip against SQLite ----
try:
    test_code = storage.generate_code()
    assert test_code.startswith("KQ-"), f"Code format wrong: {test_code}"
    assert len(test_code) == 11, f"Code length wrong: {test_code}"  # KQ- + 8 chars

    read_id = storage.save_read(
        test_code,
        mode="professional",
        persona="The Responder",
        blend={"doctor": 55, "builder": 20, "general": 20, "creator": 5},
        signals=[{"phrase": "formatted the QBR deck", "why": "repeatable"}],
        insight="Your day was Doctor-quadrant heavy.",
        next_move="Block time for strategic work tomorrow.",
        honest_question="What would change if you owned your calendar?",
        transcript=SAMPLE_DAY,
        locked=False,
    )
    assert read_id is not None, "save_read should return a read_id"

    # Unlocked reads should not appear in get_thread
    thread = storage.get_thread(test_code)
    assert len(thread) == 0, f"Unlocked read should not appear in thread, got {len(thread)}"

    # Lock it
    ok = storage.lock_read(read_id)
    assert ok, "lock_read should return True"

    # Now it should appear
    thread = storage.get_thread(test_code)
    assert len(thread) == 1, f"Locked read should appear, got {len(thread)}"
    assert thread[0]["persona"] == "The Responder"
    assert thread[0]["locked"] is True

    # Feedback
    ok = storage.record_feedback(read_id, "nailed", "Very accurate.")
    assert ok, "record_feedback should return True"

    row = storage.get_read(read_id)
    assert row is not None, "get_read should return the row"
    assert row["feedback_rating"] == "nailed"
    assert row["feedback_text"] == "Very accurate."
    assert isinstance(row["blend"], dict), "blend should be hydrated to dict"
    assert isinstance(row["signals"], list), "signals should be hydrated to list"

    # Bad code returns empty list (not a crash)
    empty = storage.get_thread("KQ-BADCODE1")
    assert empty == [], f"Bad code should return empty list, got {empty}"

    # Invalid rating is rejected
    rejected = storage.record_feedback(read_id, "great_job")
    assert rejected is False, "Invalid rating should be rejected"

    print("OK  storage round-trip: generate_code, save_read, lock_read, get_thread,",
          "record_feedback, get_read, bad-code safety, invalid-rating rejection")

finally:
    storage._initialized = False
    try:
        os.unlink(_tmp_db)
    except Exception:
        pass

print("\nALL TESTS PASSED")
