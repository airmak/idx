# IDx — Interactive Clinical Reasoning Game

An interactive clinical reasoning game for medical students that simulates diagnostic workup scenarios similar to USMLE Shelf/Board exam questions (UWorld-style) with a multi-stage interactive format.

> ⚠️ **Medical Disclaimer**: All case content is pre-written for educational purposes and draws on established medical knowledge. This tool is intended solely for studying clinical reasoning and **should not be used for clinical decision-making**. Always consult authoritative medical references and clinical judgment for patient care.

---

## Features

- **6-stage game loop**: One-liner → Extended History → Labs & Imaging → Top 3 DDx → Final Clue → Reveal & Debrief
- **Two difficulty modes**: Easy (textbook-classic) and Attending (atypical, UWorld-level)
- **VINDICATE DDx Builder**: Searchable disease library organized by VINDICATE mnemonic (200+ conditions)
- **Live AI Feedback** (optional): Stage 2 DDx refinement feedback and Stage 3 workup feedback via Claude
- **Pre-stored cases**: 10 carefully crafted cases across specialties — no API call needed to start a case
- **Full debrief**: Pathophysiology, treatment, board pearls, sources
- **Scoring system**: DDx quality, refinement accuracy, workup efficiency, diagnosis accuracy
- **Case Library**: Browse all cases with spoiler-blurred diagnoses
- **Dark clinical aesthetic**: Designed to feel like a professional medical learning tool

---

## Setup

### 1. Clone / Download

```bash
cd your-project-folder
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the `idx/` directory:

```env
FLASK_SECRET_KEY=your-random-secret-key-here
ANTHROPIC_API_KEY=sk-ant-...     # Optional — only needed for in-game feedback features
```

**Getting an Anthropic API key** (for optional feedback features only):
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up / log in
3. Navigate to API Keys → Create Key
4. Copy the key into your `.env` file

> The Claude API is **only** used for the optional "Get Feedback" buttons in Stage 2 and Stage 3. If no API key is present, the game works fully — feedback buttons will show a graceful message instead.

### 5. Run the app

```bash
python app.py
```

The app will automatically:
- Create the SQLite database (`idx.db`)
- Seed all 10 cases from the `cases/` directory
- Start the server at `http://localhost:5000`

---

## Adding New Cases

New cases can be added at any time without restarting the server:

1. Create a new JSON file in `cases/` following the schema (e.g., `cases/case_011.json`)
2. Use the same JSON structure as existing cases (see `cases/case_001.json` for reference)
3. Set a unique `case_id` (e.g., `"case_011"`)
4. Seed the new case one of two ways:
   - **Via command line**: `python seed_cases.py` (idempotent — skips existing cases)
   - **Via API** (no restart needed): `POST /admin/reseed`

### Required JSON keys

```json
{
  "case_id": "case_011",
  "mode": "easy",
  "specialty": "Internal Medicine",
  "diagnosis": "Exact diagnosis name",
  "icd_category": "ICD category string",
  "one_liner": "...",
  "stage2": { ... },
  "stage3": { "lab_results": [...], "imaging_results": [...], "key_tests": [...], "acceptable_tests": [...], "low_yield_tests": [...] },
  "stage5": { "final_clue": "..." },
  "debrief": { "classic_presentation": "...", "attending_mode_notes": null, "pathophysiology": "...", "treatment_overview": "...", "high_yield_pearls": [...], "sources": [...] },
  "ddx_hints": { "reasonable_ddx": [...], "after_stage2_more_likely": [...], "after_stage2_less_likely": [...], "after_labs_top3": [...] }
}
```

---

## File Structure

```
idx/
├── app.py                    # Flask routes and session management
├── feedback_engine.py        # Claude API calls for optional Stage 2/3 feedback
├── seed_cases.py             # Database seeder (run at startup or manually)
├── disease_library.json      # 200+ diseases organized by VINDICATE category
├── cases/
│   ├── case_001.json         # Easy | Internal Medicine — CAP (Strep pneumoniae)
│   ├── case_002.json         # Easy | Emergency Medicine — Pulmonary Embolism
│   ├── case_003.json         # Easy | Internal Medicine — DKA
│   ├── case_004.json         # Easy | Cardiology — Inferior STEMI
│   ├── case_005.json         # Easy | Surgery — Acute Appendicitis
│   ├── case_006.json         # Attending | Internal Medicine — Addison Disease
│   ├── case_007.json         # Attending | Pulmonology — Hypersensitivity Pneumonitis
│   ├── case_008.json         # Attending | Neurology — Myasthenia Gravis
│   ├── case_009.json         # Attending | Infectious Disease — Infective Endocarditis
│   └── case_010.json         # Attending | Nephrology — Rhabdomyolysis-AKI
├── templates/
│   └── index.html            # Full frontend SPA
├── idx.db                    # SQLite database (auto-created)
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve the SPA |
| GET | `/api/new-case?mode=easy&specialty=any` | Start a new case |
| GET | `/api/case/stage2` | Get extended history data |
| POST | `/api/case/stage3/results` | Submit ordered tests, get results |
| GET | `/api/case/stage4` | Get Stage 4 context |
| GET | `/api/case/stage5` | Get final clue |
| POST | `/api/case/reveal` | Submit final diagnosis, get full debrief |
| POST | `/api/feedback/stage2` | Get AI feedback on DDx refinement |
| POST | `/api/feedback/stage3` | Get AI feedback on test ordering |
| GET | `/api/case-counts` | Get easy/attending case counts |
| GET | `/api/case-library` | Get all cases for library view |
| GET | `/api/session/stats` | Get session statistics |
| POST | `/admin/reseed` | Re-seed database with any new case files |
| GET | `/api/disease-library` | Get VINDICATE disease library |

---

## Scoring System

Each case is scored out of 100:

| Component | Points | Criteria |
|-----------|--------|----------|
| DDx Score | 25 | How many "reasonable" diagnoses you included |
| Refinement Score | 20 | % of Stage 2 refinements matching clinical hints |
| Workup Score | 25 | Key tests ordered vs. low-yield tests ordered |
| Diagnosis Score | 30 | 30pts for #1 correct, 20pts for #2, 10pts for #3 |

---

## Deploying to the Web

IDx is production-ready for deployment to platforms like **Render**, **Railway**, or **Heroku**.

### Option A: Deploy to Render (recommended, free tier available)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → **Web Service**
3. Connect your GitHub repo and select the `idx` directory
4. Render will auto-detect the `render.yaml` — accept the defaults
5. Add your `ANTHROPIC_API_KEY` in the Environment tab (optional)
6. Click **Deploy**

Your site will be live at `https://idx-xxxx.onrender.com` within minutes.

### Option B: Deploy to Railway

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → **Deploy from GitHub**
3. Select the repo, Railway auto-detects the `Procfile`
4. Add environment variables: `FLASK_SECRET_KEY` (any random string), `ANTHROPIC_API_KEY` (optional)
5. Deploy — Railway assigns a public URL automatically

### Option C: Deploy anywhere with Docker or manual setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FLASK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export FLASK_ENV=production
export PORT=8080

# Run with gunicorn (Linux/macOS)
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2
```

### Production notes

- The SQLite database is created automatically on first run
- Cases are seeded automatically from the `cases/` directory
- The `ANTHROPIC_API_KEY` is optional — feedback features degrade gracefully without it
- `FLASK_SECRET_KEY` should be a strong random string in production (Render auto-generates one)

---

## Technology Stack

- **Backend**: Python 3.10+ · Flask · SQLAlchemy · SQLite · Gunicorn
- **AI**: Anthropic Claude (claude-sonnet-4-20250514) — feedback only
- **Frontend**: Vanilla HTML/CSS/JavaScript SPA (no build step)
- **Fonts**: Google Fonts (Montserrat + Inter)
