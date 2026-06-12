# RehabAI — Feature 1 Architecture Reference
## Lower Back Rehabilitation System: Exercise Selection & Rep Setting

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        STREAMLIT FRONTEND                        │
│                                                                   │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────┐   │
│  │  HOME    │→ │EXERCISE LIST │→ │CONFIGURE │→ │ CONFIRM   │   │
│  │ screen   │  │   screen     │  │  screen  │  │  screen   │   │
│  └──────────┘  └──────────────┘  └──────────┘  └───────────┘   │
│                                                                   │
│                    components/ui_components.py                    │
│               (exercise_card, session_summary_card …)            │
└────────────────────────────┬────────────────────────────────────┘
                             │ calls
┌────────────────────────────▼────────────────────────────────────┐
│                      STATE LAYER                                  │
│                  utils/state_manager.py                          │
│   init_state() · navigate_to() · create_session()               │
│   get_active_session() · select_exercise() · persist()          │
│                                                                   │
│          Persistence: JSON files (.rehabai_data/)                │
│          → swap for PostgreSQL in production                     │
└────────────────────────────┬────────────────────────────────────┘
                             │ reads/writes
┌────────────────────────────▼────────────────────────────────────┐
│                      DOMAIN LAYER                                 │
│                                                                   │
│  models/exercise_model.py         data/exercise_db.py           │
│  ┌─────────────┐                  ┌─────────────────────┐       │
│  │  Exercise   │                  │ EXERCISES dict       │       │
│  │  SessionConfig                 │ 6 exercises fully    │       │
│  │  UserProfile│                  │ specified for AI     │       │
│  │  JointAngle │                  └─────────────────────┘       │
│  │  Constraint │                                                  │
│  └─────────────┘                                                 │
│                                                                   │
│  utils/validation.py              utils/analytics.py            │
│  ┌─────────────────┐              ┌─────────────────────┐       │
│  │ SessionConfig   │              │ NumPy computation   │       │
│  │ Validator       │              │ Matplotlib charts   │       │
│  │ ValidationResult│              │ Summary stats       │       │
│  └─────────────────┘              └─────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Flow

```
User opens app
      │
      ▼
init_state()
  ├── Load UserProfile from .rehabai_data/user_profile.json
  ├── Load session_history from .rehabai_data/session_history.json
  └── Set CURRENT_SCREEN = "home"
      │
      ▼
HOME SCREEN
  ├── compute_summary_stats(history) → NumPy aggregations
  ├── plot_session_frequency()       → Matplotlib figure
  └── User clicks "Start New Session"
      │
      ▼ navigate_to(EXERCISE_LIST)
EXERCISE LIST SCREEN
  ├── get_all_exercises()    → sorted Exercise list from exercise_db.py
  ├── Filter by difficulty/category
  └── User clicks "Select" on exercise_card()
      │ select_exercise(exercise)
      ▼ navigate_to(CONFIGURE)
CONFIGURE SCREEN
  ├── User sets: reps, hold_sec, difficulty, sets
  ├── Live: validate_session_config() → ValidationResult (no Streamlit)
  ├── Live: Estimated duration shown
  ├── pain_level_selector() → VAS 0–10
  └── User clicks "Review Session →"
      │ create_session(exercise, reps, hold_sec, ...) → SessionConfig
      │ persist to .rehabai_data/session_<id>.json
      ▼ navigate_to(CONFIRM)
CONFIRM SCREEN
  ├── session_summary_card()        → visual review
  ├── Checklist checkboxes (all must be ticked)
  └── User clicks "Begin Session"
      │ config.start() → status = ACTIVE
      ▼ navigate_to(SESSION)
SESSION SCREEN (Feature 2 placeholder)
  └── config available via get_active_session()
      All downstream features read from here.
```

---

## 3. Database Schema

### Current (file-based, Streamlit prototype):

```
.rehabai_data/
├── user_profile.json          ← UserProfile.to_dict()
├── session_history.json       ← list[SessionConfig.to_dict()]
└── session_<uuid>.json        ← individual SessionConfig snapshots
```

### Production schema (PostgreSQL):

```sql
-- Users
CREATE TABLE users (
    user_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(100) NOT NULL,
    age              INTEGER,
    diagnosis        TEXT,
    preferred_difficulty VARCHAR(20) DEFAULT 'beginner',
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Exercise catalogue (seeded by physio admin)
CREATE TABLE exercises (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             VARCHAR(60) UNIQUE NOT NULL,
    name             VARCHAR(100) NOT NULL,
    category         VARCHAR(30) NOT NULL,
    difficulty       VARCHAR(20) NOT NULL,
    description      TEXT,
    instructions     JSONB,          -- list[str]
    default_reps     INTEGER,
    min_reps         INTEGER,
    max_reps         INTEGER,
    default_hold_sec INTEGER,
    max_hold_sec     INTEGER,
    target_joints    JSONB,          -- list[str]
    compensation_joints JSONB,
    joint_constraints JSONB,         -- list[JointAngleConstraint]
    calibration      JSONB,          -- CalibrationParameters
    contraindications JSONB,
    progression_from VARCHAR(60) REFERENCES exercises(slug),
    progression_to   VARCHAR(60) REFERENCES exercises(slug),
    tags             TEXT[],
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Session configurations
CREATE TABLE sessions (
    session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(user_id),
    exercise_id      UUID REFERENCES exercises(id),
    reps             INTEGER NOT NULL,
    hold_sec         INTEGER DEFAULT 0,
    difficulty       VARCHAR(20),
    sets             INTEGER DEFAULT 1,
    status           VARCHAR(20) DEFAULT 'configured',
    pain_level       INTEGER DEFAULT 0,  -- VAS 0-10
    notes            TEXT,

    -- Feature 2+ (nullable until available)
    reps_completed   INTEGER DEFAULT 0,
    sets_completed   INTEGER DEFAULT 0,
    form_score       FLOAT,              -- 0.0–1.0
    compensation_count INTEGER DEFAULT 0,
    pose_data        JSONB,              -- raw MediaPipe landmarks

    created_at       TIMESTAMPTZ DEFAULT now(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX idx_sessions_user_id    ON sessions(user_id);
CREATE INDEX idx_sessions_exercise   ON sessions(exercise_id);
CREATE INDEX idx_sessions_status     ON sessions(status);
CREATE INDEX idx_sessions_created    ON sessions(created_at DESC);
```

### Example records:

```json
// Exercise record: Pelvic Tilt
{
  "id": "ex_001",
  "slug": "pelvic_tilt",
  "name": "Pelvic Tilt",
  "difficulty": "beginner",
  "default_reps": 10,
  "target_joints": ["lumbar_spine", "pelvis"],
  "joint_constraints": [
    {"joint": "lumbar_spine", "min_angle_deg": 5, "max_angle_deg": 25, "is_primary": true}
  ]
}

// Session record
{
  "session_id": "f3a2b1c0-...",
  "exercise_slug": "pelvic_tilt",
  "reps": 10,
  "hold_sec": 3,
  "difficulty": "beginner",
  "status": "completed",
  "form_score": 0.87,
  "reps_completed": 10
}
```

---

## 4. Frontend Architecture

```
app.py  (router + screen functions)
│
├── screen_home()           ← KPIs, charts, quick-start
├── screen_exercise_list()  ← filter + card grid
├── screen_configure()      ← form with live validation
├── screen_confirm()        ← review + checklist
└── screen_session()        ← Feature 2 entry point
│
└── components/ui_components.py
    ├── exercise_card()          ← pure render, returns bool
    ├── session_summary_card()   ← visual session review
    ├── pain_level_selector()    ← VAS slider with feedback
    ├── metric_cards_row()       ← KPI row
    ├── page_header()            ← consistent header + back
    ├── difficulty_badge()       ← HTML badge string
    └── exercise_detail_panel()  ← expander with full info
```

**Key architectural decision:** Every `ui_component` function:
- Takes data as arguments (never reads session_state)
- Returns user actions as return values (bool for "was clicked")
- Can be tested in isolation

---

## 5. Backend Architecture

```
utils/
├── state_manager.py    ← All st.session_state access (single contract)
│   ├── StateKeys class     (all key name constants)
│   ├── Screen class        (all screen name constants)
│   ├── init_state()        (idempotent initialiser)
│   ├── navigate_to()       (state transitions)
│   ├── create_session()    (builds + persists SessionConfig)
│   └── _persist_*()        (file I/O — swap for DB here)
│
├── validation.py       ← Pure business logic (no Streamlit)
│   ├── SessionConfigValidator
│   │   ├── _validate_reps()
│   │   ├── _validate_hold()
│   │   ├── _validate_sets()
│   │   ├── _validate_difficulty_progression()
│   │   └── _check_safety_warnings()
│   └── ValidationResult (errors + warnings)
│
└── analytics.py        ← NumPy + Matplotlib (no Streamlit)
    ├── plot_session_frequency()
    ├── plot_reps_over_time()
    ├── plot_exercise_distribution()
    └── compute_summary_stats()
```

---

## 6. API Contracts

When you move to a FastAPI backend, these are the endpoint signatures:

```
GET  /api/exercises
     Query: ?difficulty=beginner&category=mobility
     Response: { exercises: Exercise[] }

GET  /api/exercises/:slug
     Response: { exercise: Exercise }

POST /api/sessions
     Body: { exercise_slug, reps, hold_sec, difficulty, sets, pain_level }
     Response: { session: SessionConfig }
     Validation: 400 if invalid config

PATCH /api/sessions/:id
      Body: { status?, reps_completed?, form_score?, ... }
      Response: { session: SessionConfig }

GET  /api/users/:id/history
     Query: ?limit=20&offset=0
     Response: { sessions: SessionConfig[], stats: SummaryStats }
```

---

## 7. State Management

```
st.session_state keys (StateKeys constants):
│
├── active_session      SessionConfig | None
│   └── Persisted to: .rehabai_data/session_<id>.json
│
├── selected_exercise   Exercise | None
│   └── Persisted to: (in-memory only — lost on refresh, by design)
│
├── user_profile        UserProfile
│   └── Persisted to: .rehabai_data/user_profile.json
│
├── session_history     list[dict]
│   └── Persisted to: .rehabai_data/session_history.json
│
├── current_screen      str (Screen.*)
│
└── Feature 2+ keys (initialised False/0, not yet used):
    ├── mediapipe_active    bool
    ├── current_rep_count   int
    ├── current_form_score  float | None
    └── camera_ready        bool

State lifecycle:
  - Across rerun:      ✅ preserved by Streamlit (session_state)
  - Across refresh:    ✅ reloaded from JSON files
  - Across login:      ✅ JSON files keyed by user_id (production: DB)
  - Across sessions:   ✅ session_history persisted
```

---

## 8. UI Screen Flow

```
HOME ──────────────────────────────────────────────────────────────
• Header with personalised greeting + streak
• KPI metric cards (sessions, reps, streak, completion %)
• "Start New Session" primary CTA
• Progress charts: frequency, rep progression, distribution
• Recent sessions list
• If active_session exists: resume banner

EXERCISE LIST ─────────────────────────────────────────────────────
• Filter bar: difficulty, category
• Exercise cards (sortable: beginner first, then intermediate)
  Each card: name, category, difficulty badge, description preview
  Click "Select" → stores in session_state, navigates to CONFIGURE
• Detail expander: full instructions, constraints, progressions

CONFIGURE ─────────────────────────────────────────────────────────
• Exercise context bar (name, difficulty, description)
• Left column: reps (number_input), hold_sec (slider), sets
• Right column: difficulty (selectbox), pain level (VAS slider)
• Live validation: errors shown inline as user changes values
• Estimated duration shown
• "Review Session →" disabled if validation fails OR pain ≥ 7

CONFIRM ────────────────────────────────────────────────────────────
• Session summary card (reps / hold / sets / difficulty / duration)
• Step-by-step instruction quick view
• Pre-session safety checklist (all must be ticked)
• Contraindication warning (if any)
• "Begin Session" (disabled until all boxes ticked)

SESSION (Feature 2 entry point) ───────────────────────────────────
• Receives: get_active_session() → SessionConfig
• Has: exercise's joint_constraints, calibration parameters
• Ready for MediaPipe integration
```

---

## 9. Validation Rules

| Rule                          | Code                       | Blocks? |
|-------------------------------|----------------------------|---------|
| Reps below exercise minimum   | BELOW_EXERCISE_MINIMUM     | ✅ Yes  |
| Reps above exercise maximum   | ABOVE_EXERCISE_MAXIMUM     | ✅ Yes  |
| Beginner > 15 reps            | BEGINNER_SAFEGUARD_REPS    | ✅ Yes  |
| Hold > exercise max_hold_sec  | ABOVE_EXERCISE_HOLD_MAX    | ✅ Yes  |
| Beginner hold > 10s           | BEGINNER_SAFEGUARD_HOLD    | ✅ Yes  |
| Sets > 5                      | ABOVE_MAX_SETS             | ✅ Yes  |
| Pain level ≥ 7                | (handled in screen)        | ✅ Yes  |
| Advanced difficulty on beginner exercise | —             | ⚠️ Warn |
| Session duration > 5 minutes  | —                          | ⚠️ Warn |
| Contraindications present     | —                          | ⚠️ Warn |

---

## 10. Scalability Notes

**Adding a new exercise:**
→ Add one `Exercise(...)` entry to `data/exercise_db.py`.
→ Zero other changes needed.

**Swapping to PostgreSQL:**
→ Replace the 3 `_persist_*()` functions in `state_manager.py`.
→ Add a `repositories/` layer with `ExerciseRepository`, `SessionRepository`.
→ All business logic (validation, analytics, models) is unchanged.

**Adding MediaPipe (Feature 2):**
→ Implement `screen_session()` in a new file.
→ Read `get_active_session()` and `get_selected_exercise()`.
→ `exercise.target_joints` and `exercise.joint_constraints` are already there.
→ Write `update_rep_count(n)` and `update_form_score(f)` to state_manager.
→ Feature 1 code does NOT change.

**Adding authentication:**
→ Add `screen_login()`.
→ `UserProfile.user_id` is already the foreign key for all sessions.
→ State manager's `_load_or_create_profile()` switches from file path
   to `WHERE user_id = :authenticated_user_id`.

**Multi-user / clinic mode:**
→ `SessionConfig.user_id` is already present.
→ Add a Physio role: `users.role = 'physio'` can see all their patients.
→ Exercise `prescribed_exercises` on UserProfile acts as the prescription list.

---

## 11. Risks and Edge Cases

| Risk                                  | Mitigation                                          |
|---------------------------------------|-----------------------------------------------------|
| User sets pain = 9, forces start      | Hard gate: "Begin Session" disabled if pain ≥ 7    |
| Browser refresh loses exercise choice | Exercise re-selection is cheap; sessions persisted  |
| Contradicting difficulty/exercise     | Warning shown; physio responsible for prescription  |
| Concurrent sessions on same device    | Session history append-only; active_session overwritten |
| Invalid JSON in persistence files     | try/except in all _load_* functions; fallback to default |
| User exceeds beginner rep cap         | Blocked with clear explanation + upgrade path       |
| Large session history (memory)        | Capped at 50 in-memory; full history on disk        |

---

## 12. Recommended Next Step

**Feature 2: Pose Calibration & MediaPipe Integration**

Input contract (already fully defined in Feature 1):
```python
config   = get_active_session()   # SessionConfig
exercise = get_exercise_by_slug(config.exercise_slug)

# Everything Feature 2 needs:
exercise.target_joints           # which joints to track
exercise.joint_constraints       # angle ranges to validate
exercise.calibration             # camera distance, visibility thresholds
exercise.compensation_joints     # joints to watch for substitution
config.reps                      # how many reps to count
config.hold_sec                  # how long to hold each rep
config.difficulty                # how strict to be on angle tolerances
```

Steps:
1. Add `mediapipe-python` to requirements.txt
2. Implement `utils/pose_processor.py`:
   - `init_mediapipe()` → returns `mp.solutions.pose.Pose`
   - `extract_landmarks(frame)` → dict of JointName → (x, y, z, visibility)
   - `compute_joint_angle(landmarks, joint)` → float degrees
   - `validate_form(angle, constraint)` → bool
3. Implement `screen_session()` in `components/session_screen.py`
4. Write `RepCounter` class using angle threshold crossing detection
5. All state updates go through `state_manager` functions

---

*Generated as the engineering foundation for a production rehabilitation AI system.*
*Every design decision in Feature 1 is intentionally forward-compatible.*
