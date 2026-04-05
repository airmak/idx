"""
IDx — Interactive Clinical Reasoning Game
Flask backend with pre-stored case database architecture.
"""

import os
import json
import uuid
import random
from datetime import datetime

from flask import Flask, render_template, request, session, jsonify
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

import seed_cases
import feedback_engine

# ---------------------------------------------------------------------------
# Test panel keyword mappings
# Cases store individual component results (e.g. "WBC", "Sodium") but users
# order panels (e.g. "CBC with differential", "BMP"). This maps panel names
# to keywords that identify their components in case result data.
# ---------------------------------------------------------------------------
TEST_PANEL_KEYWORDS = {
    "cbc with differential": ["wbc", "white blood", "hemoglobin", "hgb", "hematocrit", "hct",
                               "platelets", "mcv", "mch", "mchc", "rdw", "neutrophil", "lymphocyte",
                               "eosinophil", "monocyte", "basophil", "band", "cbc", "differential",
                               "red blood cell", "rbc", "reticulocyte"],
    "bmp": ["sodium", "potassium", "chloride", "bicarbonate", "hco3", "bun", "creatinine",
             "glucose", "anion gap", "egfr", "bmp", "basic metabolic"],
    "cmp": ["sodium", "potassium", "chloride", "bicarbonate", "hco3", "bun", "creatinine",
             "glucose", "anion gap", "ast", "alt", "alkaline phosphatase", "alk phos",
             "bilirubin", "albumin", "total protein", "calcium", "egfr", "cmp",
             "comprehensive metabolic"],
    "lfts": ["ast", "alt", "alkaline phosphatase", "alk phos", "bilirubin", "albumin",
              "ggт", "ggt", "total protein", "prothrombin", "lft", "liver function",
              "transaminase", "asat", "alat"],
    "blood cultures x2": ["blood culture", "bacteremia", "bacteraemia", "culture bottle"],
    "ua with microscopy": ["ua", "urinalysis", "urine analysis", "urine dipstick", "specific gravity",
                            "urine protein", "urine glucose", "urine ketone", "urine blood",
                            "urine nitrite", "urine leukocyte", "rbcs", "wbcs", "cast",
                            "bacteria", "urine microscopy", "urine sediment"],
    "urine culture": ["urine culture"],
    "abg": ["abg", "arterial blood gas", "ph", "pco2", "po2", "sao2", "base excess",
             "paco2", "pao2", "fio2"],
    "lactate": ["lactate", "lactic acid"],
    "d-dimer": ["d-dimer", "d dimer", "fibrin degradation"],
    "bnp/nt-probnp": ["bnp", "nt-probnp", "brain natriuretic", "b-type natriuretic", "proBNP"],
    "troponin i/t (serial)": ["troponin", "tnl", "tnt", "cardiac troponin"],
    "beta-hcg": ["hcg", "beta-hcg", "human chorionic", "pregnancy test"],
    "tsh/free t4": ["tsh", "thyroid stimulating", "free t4", "ft4", "thyroxine"],
    "hba1c": ["hba1c", "hemoglobin a1c", "glycated hemoglobin", "a1c"],
    "esr": ["esr", "erythrocyte sedimentation"],
    "crp": ["crp", "c-reactive protein", "c reactive protein"],
    "ana": ["ana", "antinuclear"],
    "rf": ["rheumatoid factor", "rf"],
    "anti-dsdna": ["anti-dsdna", "double stranded dna"],
    "anca": ["anca", "antineutrophil cytoplasmic"],
    "ferritin/iron studies": ["ferritin", "iron", "tibc", "transferrin saturation", "serum iron"],
    "b12/folate": ["b12", "vitamin b12", "cobalamin", "folate", "folic acid"],
    "ldh": ["ldh", "lactate dehydrogenase"],
    "uric acid": ["uric acid", "urate"],
    "blood smear": ["blood smear", "peripheral smear", "peripheral blood"],
    "cxr (pa/lateral)": ["cxr", "chest x-ray", "chest xray", "chest radiograph", "chest x ray"],
    "ct chest (w/ or w/o contrast)": ["ct chest", "chest ct", "ct of the chest", "chest computed"],
    "ct abdomen/pelvis (w/ or w/o contrast)": ["ct abdomen", "ct pelvis", "ct abd", "ct a/p",
                                                 "abdominal ct", "pelvic ct"],
    "ct head (w/ or w/o contrast)": ["ct head", "head ct", "ct brain", "brain ct"],
    "ct angiography (pulmonary/coronary/aortic)": ["ct angiography", "cta", "ct pulmonary", "ctpa",
                                                     "ct coronary", "ct aortic", "pulmonary angiography"],
    "mri brain (w/ or w/o contrast)": ["mri brain", "brain mri", "mri of the brain"],
    "mri spine": ["mri spine", "spine mri"],
    "ultrasound abdomen/pelvis": ["ultrasound abdomen", "abdominal ultrasound", "us abdomen",
                                   "pelvis ultrasound", "pelvic ultrasound"],
    "echocardiogram (transthoracic/transesophageal)": ["echo", "echocardiogram", "echocardiography",
                                                        "transthoracic", "transesophageal", "tte", "tee"],
    "ekg/ecg": ["ekg", "ecg", "electrocardiogram", "electrocardiography", "12-lead"],
    "pulmonary function tests (pfts)": ["pft", "spirometry", "fvc", "fev1", "dlco", "pulmonary function"],
    "lumbar puncture (csf analysis)": ["lumbar puncture", "lp", "csf", "cerebrospinal fluid",
                                        "spinal tap"],
    "bronchoscopy": ["bronchoscopy", "bal", "bronchoalveolar lavage"],
    "nerve conduction study (ncs/emg)": ["nerve conduction", "ncs", "emg", "electromyography",
                                          "repetitive nerve", "single fiber", "jitter"],
    "electroencephalogram (eeg)": ["eeg", "electroencephalogram"],
}

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "idx-dev-fallback-change-me-in-production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "idx.db")

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

with app.app_context():
    seed_cases.init_db(engine)
    seed_cases.seed(verbose=False)  # verbose=False avoids encoding issues on Windows console


# ---------------------------------------------------------------------------
# Global error handlers — always return JSON so the frontend can parse errors
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": f"Not found: {request.path}"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    app.logger.error(traceback.format_exc())
    return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session_id():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def get_active_case():
    case_uid = session.get("active_case_uid")
    if not case_uid:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT case_data FROM cases WHERE case_uid = :uid"),
            {"uid": case_uid}
        ).fetchone()
    if row:
        return json.loads(row[0])
    return None


def _norm(s: str) -> str:
    """Normalize a diagnosis name for fuzzy comparison.

    Strips parenthetical suffixes so 'Pulmonary embolism (PE)' matches
    the case-file entry 'Pulmonary embolism', and hint strings like
    'Pulmonary embolism (long flight, OCP…)' also resolve to the same key.
    """
    return s.split("(")[0].strip().lower() if "(" in s else s.strip().lower()


def _norm_set(iterable) -> set:
    return {_norm(x) for x in iterable}


def compute_score(case_data: dict) -> dict:
    """Compute the per-case score (0–100) based on user performance."""
    ddx_hints = case_data.get("ddx_hints", {})
    stage3 = case_data.get("stage3", {})

    user_ddx = session.get("user_ddx", [])
    user_refinements = session.get("user_refinements", {})
    user_tests = session.get("user_tests", [])
    user_top3 = session.get("user_top3", [])
    user_final = session.get("user_final", "")
    correct_dx = case_data.get("diagnosis", "")

    # DDx Score (25 pts): how many reasonable_ddx did the user include?
    reasonable = ddx_hints.get("reasonable_ddx", [])
    reasonable_norm = _norm_set(reasonable)
    if reasonable:
        ddx_matches = sum(1 for d in user_ddx if _norm(d) in reasonable_norm)
        ddx_score = round((ddx_matches / len(reasonable)) * 25)
    else:
        ddx_score = 25

    # Refinement Score (20 pts): % of Stage 2 refinements matching hints
    more_likely_norm = _norm_set(ddx_hints.get("after_stage2_more_likely", []))
    less_likely_norm = _norm_set(ddx_hints.get("after_stage2_less_likely", []))
    refinement_correct = 0
    refinement_total = len(user_refinements)
    for diag, choice in user_refinements.items():
        d = _norm(diag)
        if choice == "more_likely" and d in more_likely_norm:
            refinement_correct += 1
        elif choice == "less_likely" and d in less_likely_norm:
            refinement_correct += 1
        elif choice == "just_as_likely" and d not in more_likely_norm and d not in less_likely_norm:
            refinement_correct += 1
    refinement_score = round((refinement_correct / refinement_total) * 20) if refinement_total else 20

    # Workup Score (25 pts): high-yield ordered vs low-yield ordered
    key_tests = stage3.get("key_tests", [])
    low_yield_tests = stage3.get("low_yield_tests", [])
    key_ordered = sum(1 for t in user_tests if t in key_tests)
    low_ordered = sum(1 for t in user_tests if t in low_yield_tests)
    if key_tests:
        workup_score = round((key_ordered / len(key_tests)) * 25)
    else:
        workup_score = 25
    workup_score = max(0, workup_score - (low_ordered * 5))

    # Diagnosis Score (30 pts): 30 for #1, 20 for #2, 10 for #3, 0 otherwise
    diag_score = 0
    correct_norm = _norm(correct_dx)
    if _norm(user_final) == correct_norm:
        if len(user_top3) > 0 and _norm(user_top3[0]) == correct_norm:
            diag_score = 30
        elif len(user_top3) > 1 and _norm(user_top3[1]) == correct_norm:
            diag_score = 20
        elif len(user_top3) > 2 and _norm(user_top3[2]) == correct_norm:
            diag_score = 10

    total = ddx_score + refinement_score + workup_score + diag_score
    total = min(100, max(0, total))

    is_correct = _norm(user_final) == correct_norm
    return {
        "ddx_score": ddx_score,
        "ddx_max": 25,
        "refinement_score": refinement_score,
        "refinement_max": 20,
        "workup_score": workup_score,
        "workup_max": 25,
        "diagnosis_score": diag_score,
        "diagnosis_max": 30,
        "total": total,
        "correct": is_correct
    }


def ddx_feedback_for_debrief(case_data: dict) -> list:
    """Generate per-diagnosis DDx review for the debrief screen."""
    user_ddx = session.get("user_ddx", [])
    user_refinements = session.get("user_refinements", {})
    ddx_hints = case_data.get("ddx_hints", {})
    reasonable_norm = _norm_set(ddx_hints.get("reasonable_ddx", []))
    more_likely_norm = _norm_set(ddx_hints.get("after_stage2_more_likely", []))
    less_likely_norm = _norm_set(ddx_hints.get("after_stage2_less_likely", []))

    items = []
    for diag in user_ddx:
        d = _norm(diag)
        reasonable_to_include = d in reasonable_norm
        refinement_choice = user_refinements.get(diag, "not_refined")
        refinement_correct = (
            (refinement_choice == "more_likely" and d in more_likely_norm) or
            (refinement_choice == "less_likely" and d in less_likely_norm) or
            (refinement_choice == "just_as_likely" and d not in more_likely_norm and d not in less_likely_norm)
        )
        items.append({
            "diagnosis": diag,
            "reasonable_to_include": reasonable_to_include,
            "refinement_choice": refinement_choice,
            "refinement_correct": refinement_correct
        })
    return items


# ---------------------------------------------------------------------------
# Routes — Serving the SPA
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — Case Selection
# ---------------------------------------------------------------------------

@app.route("/api/case-counts")
def case_counts():
    try:
        with engine.connect() as conn:
            easy = conn.execute(
                text("SELECT COUNT(*) FROM cases WHERE mode = 'easy'")
            ).scalar()
            attending = conn.execute(
                text("SELECT COUNT(*) FROM cases WHERE mode = 'attending'")
            ).scalar()
        return jsonify({"easy": easy, "attending": attending})
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/new-case")
def new_case():
    mode = request.args.get("mode", "easy").lower()
    specialty = request.args.get("specialty", "any").lower()

    session_id = get_session_id()

    # Clear previous case state
    for key in ["active_case_uid", "user_ddx", "user_refinements",
                 "user_tests", "user_top3", "user_final", "current_stage"]:
        session.pop(key, None)

    try:
        with engine.connect() as conn:
            # Get played cases this session
            played_rows = conn.execute(
                text("SELECT case_uid FROM session_history WHERE session_id = :sid"),
                {"sid": session_id}
            ).fetchall()
            played_uids = {r[0] for r in played_rows}

            # Build query
            params = {"mode": mode}
            query = "SELECT case_uid, case_data FROM cases WHERE mode = :mode"
            if specialty != "any":
                query += " AND LOWER(specialty) LIKE :specialty"
                params["specialty"] = f"%{specialty}%"

            all_cases = conn.execute(text(query), params).fetchall()

            if not all_cases:
                return jsonify({"error": f"No cases found for mode='{mode}' specialty='{specialty}'"}), 404

            reset_session = False
            eligible = [(uid, data) for uid, data in all_cases if uid not in played_uids]
            if not eligible:
                # All cases played — reset session history for this session
                conn.execute(
                    text("DELETE FROM session_history WHERE session_id = :sid"),
                    {"sid": session_id}
                )
                conn.commit()
                eligible = all_cases
                reset_session = True

            chosen_uid, chosen_data_str = random.choice(eligible)
            chosen_data = json.loads(chosen_data_str)

            # Increment times_played
            conn.execute(
                text("UPDATE cases SET times_played = times_played + 1 WHERE case_uid = :uid"),
                {"uid": chosen_uid}
            )
            conn.commit()

        session["active_case_uid"] = chosen_uid
        session["current_stage"] = 1
        session.modified = True

        # Return only Stage 1 data
        return jsonify({
            "case_uid": chosen_uid,
            "mode": chosen_data["mode"],
            "specialty": chosen_data["specialty"],
            "one_liner": chosen_data["one_liner"],
            "reset_session": reset_session
        })

    except Exception as e:
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Failed to load case: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Routes — Progressive Stage Data Revelation
# ---------------------------------------------------------------------------

@app.route("/api/case/stage2")
def get_stage2():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case. Start a new case first."}), 400
    session["current_stage"] = 2
    return jsonify(case_data.get("stage2", {}))


@app.route("/api/case/stage3/results", methods=["POST"])
def get_stage3_results():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case."}), 400

    body = request.get_json() or {}
    ordered_tests = body.get("tests", [])

    if not ordered_tests:
        return jsonify({"error": "No tests provided."}), 400

    # Save ordered tests to session
    session["user_tests"] = ordered_tests
    session["current_stage"] = 3
    session.modified = True

    stage3 = case_data.get("stage3", {})
    all_lab_results = stage3.get("lab_results", [])
    all_imaging_results = stage3.get("imaging_results", [])

    def get_keywords(test_name: str) -> list:
        """Return keyword list for a panel name from the mapping."""
        key = test_name.lower().strip()
        for panel_key, keywords in TEST_PANEL_KEYWORDS.items():
            if key == panel_key or key in panel_key or panel_key in key:
                return keywords
        # Fall back: tokenize the test name itself
        return [w for w in key.split() if len(w) > 2]

    def entry_matches(entry: dict, keywords: list, test_name: str) -> bool:
        """Check if a result entry matches a panel by its test_name field."""
        r_name = entry.get("test_name", "").lower()
        t_lower = test_name.lower()
        # Direct match
        if r_name == t_lower or t_lower in r_name or r_name in t_lower:
            return True
        # Keyword match
        return any(kw.lower() in r_name for kw in keywords)

    def determine_panel_flag(entries: list) -> str:
        """Determine overall flag for a grouped panel result."""
        flags = [e.get("flag", "WNL") for e in entries]
        if "HIGH" in flags: return "HIGH"
        if "ABNORMAL" in flags: return "ABNORMAL"
        if "LOW" in flags: return "LOW"
        return "WNL"

    all_results = all_lab_results + all_imaging_results
    used_indices = set()
    revealed = []

    for test in ordered_tests:
        keywords = get_keywords(test)
        matched = []
        for i, entry in enumerate(all_results):
            if i not in used_indices and entry_matches(entry, keywords, test):
                matched.append((i, entry))

        if matched:
            # Mark these entries as used to avoid double-reporting
            for idx, _ in matched:
                used_indices.add(idx)

            if len(matched) == 1:
                # Single result — return as-is
                entry = dict(matched[0][1])
                entry["test_name"] = test  # normalize name to what user ordered
                revealed.append(entry)
            else:
                # Multiple components — aggregate into one result card
                combined_values = "; ".join(
                    f"{e.get('test_name','')}: {e.get('result','')}" for _, e in matched
                )
                # Collect all clinical significance notes
                sig_notes = list(set(
                    e.get("clinical_significance", "") for _, e in matched
                    if e.get("clinical_significance")
                ))
                overall_sig = " | ".join(sig_notes[:2])  # limit to 2 notes
                panel_flag = determine_panel_flag([e for _, e in matched])
                revealed.append({
                    "test_name": test,
                    "result": combined_values,
                    "flag": panel_flag,
                    "clinical_significance": overall_sig
                })
        else:
            # No matching result in case data
            revealed.append({
                "test_name": test,
                "result": "Within normal limits / Not contributory for this case.",
                "flag": "WNL",
                "clinical_significance": ""
            })

    return jsonify({"results": revealed})


@app.route("/api/case/stage4")
def get_stage4():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case."}), 400
    session["current_stage"] = 4
    # Return user's current DDx for selection
    return jsonify({"user_ddx": session.get("user_ddx", [])})


@app.route("/api/case/stage5")
def get_stage5():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case."}), 400
    session["current_stage"] = 5
    return jsonify(case_data.get("stage5", {}))


@app.route("/api/case/reveal", methods=["POST"])
def reveal():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case."}), 400

    body = request.get_json() or {}
    user_final = body.get("final_diagnosis", "")
    session["user_final"] = user_final
    session["current_stage"] = 6
    session.modified = True

    correct_dx = case_data.get("diagnosis", "")
    is_correct = _norm(user_final) == _norm(correct_dx)

    score = compute_score(case_data)
    ddx_review = ddx_feedback_for_debrief(case_data)

    session_id = get_session_id()
    case_uid = session.get("active_case_uid")

    try:
        with engine.connect() as conn:
            # Record in session history
            conn.execute(
                text("""
                    INSERT INTO session_history (session_id, case_uid, score, correct)
                    VALUES (:sid, :uid, :score, :correct)
                """),
                {
                    "sid": session_id,
                    "uid": case_uid,
                    "score": score["total"],
                    "correct": is_correct
                }
            )
            if is_correct:
                conn.execute(
                    text("UPDATE cases SET times_correct = times_correct + 1 WHERE case_uid = :uid"),
                    {"uid": case_uid}
                )

            # Fetch updated stats
            stats_row = conn.execute(
                text("SELECT times_played, times_correct FROM cases WHERE case_uid = :uid"),
                {"uid": case_uid}
            ).fetchone()
            conn.commit()

        times_played = stats_row[0] if stats_row else 1
        times_correct = stats_row[1] if stats_row else (1 if is_correct else 0)
        correct_rate = round((times_correct / times_played) * 100) if times_played else 0

    except SQLAlchemyError:
        times_played = 1
        times_correct = 1 if is_correct else 0
        correct_rate = 100 if is_correct else 0

    return jsonify({
        "correct": is_correct,
        "correct_diagnosis": correct_dx,
        "icd_category": case_data.get("icd_category", ""),
        "score": score,
        "ddx_review": ddx_review,
        "debrief": case_data.get("debrief", {}),
        "stage3_review": {
            "key_tests": case_data.get("stage3", {}).get("key_tests", []),
            "acceptable_tests": case_data.get("stage3", {}).get("acceptable_tests", []),
            "low_yield_tests": case_data.get("stage3", {}).get("low_yield_tests", []),
            "user_tests": session.get("user_tests", [])
        },
        "case_stats": {
            "times_played": times_played,
            "times_correct": times_correct,
            "correct_rate": correct_rate
        }
    })


# ---------------------------------------------------------------------------
# Routes — Session State Save (called by frontend on user interactions)
# ---------------------------------------------------------------------------

@app.route("/api/session/save-ddx", methods=["POST"])
def save_ddx():
    body = request.get_json() or {}
    session["user_ddx"] = body.get("ddx", [])
    session.modified = True
    return jsonify({"ok": True})


@app.route("/api/session/save-refinements", methods=["POST"])
def save_refinements():
    body = request.get_json() or {}
    session["user_refinements"] = body.get("refinements", {})
    session.modified = True
    return jsonify({"ok": True})


@app.route("/api/session/save-top3", methods=["POST"])
def save_top3():
    body = request.get_json() or {}
    session["user_top3"] = body.get("top3", [])
    session.modified = True
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes — Optional Feedback (live Claude API)
# ---------------------------------------------------------------------------

@app.route("/api/feedback/stage2", methods=["POST"])
def feedback_stage2():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case."}), 400
    body = request.get_json() or {}
    refinements = body.get("refinements", session.get("user_refinements", {}))
    api_key = body.get("api_key") or None
    result = feedback_engine.get_stage2_feedback(case_data, refinements, api_key=api_key)
    return jsonify(result)


@app.route("/api/feedback/stage3", methods=["POST"])
def feedback_stage3():
    case_data = get_active_case()
    if not case_data:
        return jsonify({"error": "No active case."}), 400
    body = request.get_json() or {}
    tests = body.get("tests", session.get("user_tests", []))
    api_key = body.get("api_key") or None
    result = feedback_engine.get_stage3_feedback(case_data, tests, api_key=api_key)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Routes — Case Library & Admin
# ---------------------------------------------------------------------------

@app.route("/api/case-library")
def case_library():
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT case_uid, mode, specialty, diagnosis, times_played, times_correct
                    FROM cases
                    ORDER BY mode, specialty, case_uid
                """)
            ).fetchall()
        items = []
        for row in rows:
            uid, mode, specialty, diagnosis, played, correct = row
            rate = round((correct / played) * 100) if played else 0
            items.append({
                "case_uid": uid,
                "mode": mode,
                "specialty": specialty,
                "diagnosis": diagnosis,
                "times_played": played,
                "times_correct": correct,
                "correct_rate": rate
            })
        return jsonify({"cases": items})
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/reseed", methods=["POST"])
def admin_reseed():
    """Re-run the seeder to pick up any newly added case JSON files."""
    seeded, skipped = seed_cases.seed(verbose=False)
    return jsonify({
        "message": f"Reseeding complete: {seeded} new cases added, {skipped} already existed.",
        "seeded": seeded,
        "skipped": skipped
    })


# ---------------------------------------------------------------------------
# Session stats across cases
# ---------------------------------------------------------------------------

@app.route("/api/session/stats")
def session_stats():
    session_id = get_session_id()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT COUNT(*), SUM(score), SUM(CASE WHEN correct THEN 1 ELSE 0 END)
                    FROM session_history
                    WHERE session_id = :sid
                """),
                {"sid": session_id}
            ).fetchone()
        total_cases = rows[0] or 0
        total_score = rows[1] or 0
        correct_cases = rows[2] or 0
        avg_score = round(total_score / total_cases) if total_cases else 0
        return jsonify({
            "cases_played": total_cases,
            "avg_score": avg_score,
            "correct_diagnoses": correct_cases
        })
    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/disease-library")
def disease_library():
    lib_path = os.path.join(BASE_DIR, "disease_library.json")
    try:
        with open(lib_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, use_debugger=False, use_reloader=debug, host="0.0.0.0", port=port)
