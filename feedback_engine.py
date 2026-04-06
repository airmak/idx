"""
IDx Feedback Engine
Handles feedback for Stage 2 and Stage 3.
- Rule-based feedback works without any API key.
- If an Anthropic API key is available (env or passed at runtime), Claude provides richer explanations.
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()


def _get_client(api_key: str | None = None):
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def _api_available(api_key: str | None = None) -> bool:
    return bool(api_key or os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Helpers for rule-based feedback
# ---------------------------------------------------------------------------

def _hint_name(hint: str) -> str:
    """Extract the core diagnosis name from a hint string like 'PE (long flight, OCP…)'."""
    return hint.split("(")[0].strip() if "(" in hint else hint.strip()


def _hint_explanation(hint: str) -> str:
    """Extract the parenthetical explanation from a hint string, if present."""
    if "(" in hint:
        return hint[hint.index("(") + 1:].rstrip(")")
    return ""


def _diag_matches_hint(diag: str, hint: str) -> bool:
    """Fuzzy match between a user-selected diagnosis and a hint entry name."""
    d = diag.lower()
    h_name = _hint_name(hint).lower()
    return h_name in d or d in h_name


def _test_category(test: str, key_tests: list, acceptable_tests: list, low_yield_tests: list) -> str:
    t = test.lower()
    if any(t in k.lower() or k.lower() in t for k in key_tests):
        return "key"
    if any(t in a.lower() or a.lower() in t for a in acceptable_tests):
        return "acceptable"
    if any(t in lw.lower() or lw.lower() in t for lw in low_yield_tests):
        return "low_yield"
    return "unknown"


# ---------------------------------------------------------------------------
# Rule-based feedback (no API key required)
# ---------------------------------------------------------------------------

def get_stage2_feedback_rulebased(case_data: dict, user_refinements: dict) -> dict:
    """Generate feedback on DDx refinements using hint data — no API needed."""
    ddx_hints = case_data.get("ddx_hints", {})
    more_likely_hints = ddx_hints.get("after_stage2_more_likely", [])
    less_likely_hints = ddx_hints.get("after_stage2_less_likely", [])

    items = []
    for diag, choice in user_refinements.items():
        matched_more = next((h for h in more_likely_hints if _diag_matches_hint(diag, h)), None)
        matched_less = next((h for h in less_likely_hints if _diag_matches_hint(diag, h)), None)

        if choice == "more_likely" and matched_more:
            verdict = "correct"
            reason = _hint_explanation(matched_more)
            explanation = f"Good reasoning — the clinical findings support moving this up. Key factors: {reason}." if reason else "The clinical information supports prioritizing this diagnosis."
        elif choice == "less_likely" and matched_less:
            verdict = "correct"
            reason = _hint_explanation(matched_less)
            explanation = f"Correct — the new information makes this less likely. Reasoning: {reason}." if reason else "The clinical findings make this diagnosis less likely at this stage."
        elif choice == "just_as_likely" and not matched_more and not matched_less:
            verdict = "correct"
            explanation = "The new information does not significantly shift the probability of this diagnosis — reasonable to keep it where it is."
        elif choice == "more_likely" and matched_less:
            verdict = "incorrect"
            reason = _hint_explanation(matched_less)
            explanation = f"Reconsider — the clinical findings actually make this less likely. {reason}." if reason else "The clinical findings do not support moving this diagnosis up."
        elif choice == "less_likely" and matched_more:
            verdict = "incorrect"
            reason = _hint_explanation(matched_more)
            explanation = f"Reconsider — the clinical data actually supports moving this up. {reason}." if reason else "The clinical information actually supports this diagnosis more at this stage."
        elif choice == "more_likely":
            verdict = "reasonable"
            explanation = "This is a reasonable choice, though the available clinical information does not strongly favor or disfavor it."
        elif choice == "less_likely":
            verdict = "reasonable"
            explanation = "Reasonable, though the clinical information does not definitively rule this out at this stage."
        else:
            verdict = "reasonable"
            explanation = "Reasonable to keep this in the differential without major adjustment based on the information so far."

        items.append({"name": diag, "verdict": verdict, "explanation": explanation})

    return {"items": items, "source": "rule-based"}


def get_stage3_feedback_rulebased(case_data: dict, ordered_tests: list) -> dict:
    """Generate feedback on test ordering using case hint data — no API needed."""
    stage3 = case_data.get("stage3", {})
    key_tests = stage3.get("key_tests", [])
    acceptable_tests = stage3.get("acceptable_tests", [])
    low_yield_tests = stage3.get("low_yield_tests", [])

    items = []
    for test in ordered_tests:
        cat = _test_category(test, key_tests, acceptable_tests, low_yield_tests)
        if cat == "key":
            verdict = "correct"
            explanation = "High-yield choice — this test directly narrows the differential and guides management."
        elif cat == "acceptable":
            verdict = "reasonable"
            explanation = "Reasonable test that can provide supportive information, though not the highest priority for this presentation."
        elif cat == "low_yield":
            verdict = "incorrect"
            explanation = "Low-yield for this clinical picture — unlikely to change the diagnosis or management here."
        else:
            verdict = "reasonable"
            explanation = "This test may provide useful context, though it is not a top priority for this presentation."
        items.append({"name": test, "verdict": verdict, "explanation": explanation})

    missed_key = [t for t in key_tests if not any(
        t.lower() in ot.lower() or ot.lower() in t.lower() for ot in ordered_tests
    )]
    missed_str = f"Key tests not ordered: {', '.join(missed_key[:3])}." if missed_key else ""

    return {"items": items, "missed_critical": missed_str, "source": "rule-based"}


def get_stage2_feedback(case_data: dict, user_refinements: dict, api_key: str | None = None) -> dict:
    """
    Evaluate user's DDx refinement choices against Stage 2 clinical info.

    user_refinements: { "Diagnosis Name": "more_likely" | "just_as_likely" | "less_likely" }
    Returns: { "items": [ { "name": str, "verdict": "correct"|"reasonable"|"incorrect", "explanation": str } ] }
    """
    if not _api_available(api_key):
        return get_stage2_feedback_rulebased(case_data, user_refinements)

    client = _get_client(api_key)
    if not client:
        return get_stage2_feedback_rulebased(case_data, user_refinements)

    ddx_hints = case_data.get("ddx_hints", {})
    more_likely_hints = ddx_hints.get("after_stage2_more_likely", [])
    less_likely_hints = ddx_hints.get("after_stage2_less_likely", [])
    stage2 = case_data.get("stage2", {})

    refinements_text = "\n".join(
        f"- {diag}: {choice}" for diag, choice in user_refinements.items()
    )

    prompt = f"""You are a medical education evaluator for the IDx clinical reasoning game.

CASE CONTEXT:
One-liner: {case_data.get('one_liner', '')}

Stage 2 Clinical Information:
- HPI Extension: {stage2.get('hpi_extension', '')}
- PMH: {stage2.get('pmh', '')}
- Medications: {stage2.get('medications', '')}
- Vitals: Temp {stage2.get('vitals', {}).get('temp', '')}, HR {stage2.get('vitals', {}).get('hr', '')}, BP {stage2.get('vitals', {}).get('bp', '')}, RR {stage2.get('vitals', {}).get('rr', '')}, SpO2 {stage2.get('vitals', {}).get('spo2', '')}
- Physical Exam: {stage2.get('physical_exam', '')}

INSTRUCTOR HINTS (not shown to student):
- Diagnoses that should move UP after Stage 2: {json.dumps(more_likely_hints)}
- Diagnoses that should move DOWN after Stage 2: {json.dumps(less_likely_hints)}

STUDENT'S DDx REFINEMENTS:
{refinements_text}

TASK: Evaluate each of the student's refinement choices. Do NOT reveal the final diagnosis.
Be educational and specific. Explain WHY each choice is correct, reasonable, or incorrect based on the clinical information presented.
Keep each explanation to 1-2 sentences. Be encouraging but accurate.

Return ONLY valid JSON in this exact format:
{{
  "items": [
    {{
      "name": "Diagnosis name",
      "verdict": "correct" or "reasonable" or "incorrect",
      "explanation": "Brief educational explanation"
    }}
  ]
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        return json.loads(response_text)
    except (json.JSONDecodeError, anthropic.APIError, Exception):
        # Fall back to rule-based on any API failure
        return get_stage2_feedback_rulebased(case_data, user_refinements)


def get_stage3_feedback(case_data: dict, ordered_tests: list, api_key: str | None = None) -> dict:
    """
    Evaluate user's test ordering choices.

    ordered_tests: list of test name strings the user ordered
    Returns: { "items": [ { "name": str, "verdict": "correct"|"reasonable"|"incorrect", "explanation": str } ] }
    """
    if not _api_available(api_key):
        return get_stage3_feedback_rulebased(case_data, ordered_tests)

    client = _get_client(api_key)
    if not client:
        return get_stage3_feedback_rulebased(case_data, ordered_tests)

    stage3 = case_data.get("stage3", {})
    key_tests = stage3.get("key_tests", [])
    acceptable_tests = stage3.get("acceptable_tests", [])
    low_yield_tests = stage3.get("low_yield_tests", [])

    ordered_text = "\n".join(f"- {t}" for t in ordered_tests)
    missed_key = [t for t in key_tests if t not in ordered_tests]

    prompt = f"""You are a medical education evaluator for the IDx clinical reasoning game.

CASE CONTEXT:
One-liner: {case_data.get('one_liner', '')}
Mode: {case_data.get('mode', '')}

INSTRUCTOR CLASSIFICATIONS (not shown to student):
- Key/essential tests for this diagnosis: {json.dumps(key_tests)}
- Acceptable but not essential tests: {json.dumps(acceptable_tests)}
- Low-yield or inappropriate tests: {json.dumps(low_yield_tests)}
- Key tests the student MISSED: {json.dumps(missed_key)}

STUDENT ORDERED:
{ordered_text}

TASK: Evaluate the student's test ordering choices. For each test they ordered, say whether it was
high-yield (correct), reasonable (acceptable), or low-yield/inappropriate (incorrect).
If they missed critical tests, note that clearly at the end without revealing the diagnosis.
Keep explanations brief (1-2 sentences each). Do NOT reveal the final diagnosis.

Return ONLY valid JSON in this exact format:
{{
  "items": [
    {{
      "name": "Test name",
      "verdict": "correct" or "reasonable" or "incorrect",
      "explanation": "Brief explanation of why this test is/isn't valuable here"
    }}
  ],
  "missed_critical": "String describing any critical missed tests and why they matter (empty string if none missed)"
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        return json.loads(response_text)
    except (json.JSONDecodeError, anthropic.APIError, Exception):
        # Fall back to rule-based on any API failure
        return get_stage3_feedback_rulebased(case_data, ordered_tests)
