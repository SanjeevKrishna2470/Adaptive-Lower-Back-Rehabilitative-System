# Gemini UI/UX Improvement Prompt — Adaptive Rehabilitative System

## Context

You are improving an existing **AI physiotherapy and rehabilitation system** called **Adaptive Rehabilitative System**. It has two connected interfaces:

1. **Streamlit dashboard** in `streamlit_app/streamlit_app.py`
   - Exercise/protocol selection
   - Prescribed repetition count
   - Adaptive hold threshold and target ROM
   - Postural profile calibration using a live Flask session or uploaded video
   - Live rehabilitation launch
   - Session report with metrics, clinical inferences, recommendation, and longitudinal trends
   - Shared state through `rehab_storage.json`

2. **Flask + Socket.IO live-session interface** in:
   - `flask_rehab/templates/live.html`
   - `flask_rehab/static/live.css`
   - `flask_rehab/static/live.js`
   - `flask_rehab/app.py`
   - It displays the webcam, processed skeleton overlay, real-time telemetry, instructions, calibration controls, restart/finish actions, and form-quality feedback.

The backend biomechanics and session logic are already implemented. Your job is to substantially improve the **UI, UX, visual system, information hierarchy, accessibility, responsiveness, and perceived product quality**, while preserving behavior.

## Non-negotiable constraints

- Do **not** remove or weaken the rehabilitation, calibration, telemetry, Socket.IO, redirect, session-ticket, adaptive progression, or shared-storage behavior.
- Do not replace the Flask live session with a fake static mockup.
- Do not hardcode telemetry values, exercise names, report metrics, or calibration states.
- Preserve all existing IDs, data attributes, event hooks, Socket.IO events, route expectations, query parameters, and JavaScript integration points unless you update every dependent reference safely.
- Preserve the existing two-process architecture: Streamlit remains the dashboard/reporting UI, and Flask remains the real-time camera session UI.
- Keep the interface usable on a laptop, tablet, and mobile-sized viewport. The live session should prioritize a clinical kiosk/laptop layout but degrade gracefully on narrow screens.
- Use semantic HTML, keyboard navigation, visible focus states, appropriate ARIA labels/live regions, sufficient color contrast, and reduced-motion support.
- Avoid emoji-heavy headings and avoid generic “AI futuristic dashboard” styling. The product should feel calm, trustworthy, clinical, human, and premium.
- Do not introduce a frontend framework or build step unless the repository already uses one. Prefer the existing HTML/CSS/JS and Streamlit-compatible techniques.
- Keep patient-facing language plain, reassuring, concise, and action-oriented. Clinician-facing data can remain more detailed.
- If a visual state is uncertain, inspect the existing code and preserve the underlying behavior rather than guessing.

## Product design direction

Create a cohesive design language across both interfaces:

- **Brand personality:** calm clinical technology, supportive coaching, precise measurement, trustworthy progress.
- **Suggested palette:** warm off-white or deep slate foundation; accessible teal/blue as the primary action color; therapeutic amber for calibration and attention; green for positive/completed states; red only for urgent form/fatigue warnings. Do not rely on color alone.
- **Visual style:** generous spacing, restrained rounded cards, subtle borders, layered surfaces, clear typography, strong numeric hierarchy, and purposeful motion.
- **Typography:** use a highly readable system font stack or a safe local/web font. Establish a clear scale for page titles, section headings, labels, body text, telemetry values, warnings, and helper text.
- **Components:** define consistent tokens for color, spacing, radius, shadow, border, focus ring, and motion. Reuse card, badge, button, status, metric, progress, and alert patterns.
- **Tone:** “You’re ready,” “Hold steady,” “Move smoothly,” and “Session complete” rather than technical or alarming copy.

## Streamlit dashboard improvements

Redesign the Streamlit dashboard as a clear step-by-step rehabilitation workspace:

### 1. Header and orientation

- Replace the current emoji-heavy title treatment with a polished product header.
- Show the product name, current exercise, calibration status, and a compact explanation of what the user should do next.
- Make the current step visually obvious: **Choose exercise → Calibrate → Exercise → Review report**.
- Keep the primary action visible above the fold.

### 2. Sidebar/control deck

- Turn the sidebar into a clean “Session setup” panel.
- Group controls logically: exercise prescription, target repetitions, adaptive thresholds, and status.
- Explain adaptive hold and target ROM in plain language with compact helper text or tooltips.
- Make the active exercise and its state visually prominent.
- Avoid making clinically important controls look like unrelated generic Streamlit widgets.

### 3. Calibration flow

- Present calibration as a guided card with a short explanation, prerequisites, and a clear primary CTA.
- Explain camera positioning: full body visible, adequate lighting, stable natural posture.
- Distinguish **Live Camera** and **Upload Video** as two clear options, with a visible recommended option.
- Improve upload feedback with filename, validation, progress, preview, processing status, success, and recovery instructions.
- Make “calibrated” a strong, understandable status rather than just a green banner.
- Make recalibration a secondary/destructive-looking action with clear consequences, but do not add unnecessary confirmation dialogs that block normal use.

### 4. Rehabilitation launch

- Make “Start Live Rehabilitation” the dominant CTA only when appropriate.
- If calibration is missing, explain the consequence without making the experience feel broken.
- Show the selected exercise, target reps, target ROM, and hold duration before launch.
- Add a concise “Before you start” checklist.

### 5. Report experience

- Redesign the report into a clinically legible summary:
  - Overall session status
  - Execution precision
  - Average ROM
  - Mean hold time
  - Transition speed
  - Symmetry score
  - Fatigue index
  - Common compensation and form flaw
  - Clinical directive/recommendation
- Use metric cards with clear units and small explanatory labels.
- Add qualitative status labels such as “On track,” “Needs attention,” or “Excellent control” derived from the existing values, without changing the underlying calculations.
- Improve the longitudinal chart with a title, legend, axis labels, readable colors, and an explanation of what the trend means. If Streamlit’s native chart cannot be styled sufficiently, use a compatible charting approach already supported by the project.
- Make the report useful to both a patient and a clinician: patient-friendly headline, clinically specific details below.
- Include empty, loading, and error states for reports.

### 6. Streamlit accessibility and polish

- Remove unnecessary decorative emoji from core clinical UI.
- Improve spacing and vertical rhythm.
- Avoid raw inline styling where a reusable style pattern is possible.
- Ensure buttons have clear labels and consistent hierarchy.
- Add helpful empty states, progress indicators, and error recovery instructions.
- Keep all redirects and query-parameter behavior working, especially returning to the same tab after calibration or session completion.

## Flask live-session improvements

This is the highest-priority screen because it is used during physical movement.

### 1. Live-session layout

- Build a focused session shell with:
  - Compact top bar containing exercise, mode, session status, and essential controls
  - Large central camera/processed-feed area
  - High-priority coaching instruction area
  - Secondary telemetry panel
  - Clear session completion/restart controls
- The processed skeleton feed should be the visual focal point; raw webcam should remain available but secondary.
- Use a responsive layout that becomes stacked on narrow screens.
- Prevent the fixed instruction bar from covering content or controls.
- Make the page work well in a dark environment without creating excessive glare.

### 2. Camera and skeleton panels

- Improve labels to explain the difference between “Camera view” and “Movement analysis.”
- Add an unobtrusive live indicator and connection/camera status.
- Provide a meaningful empty state before the camera starts.
- Preserve the existing `#processed.form-good` and `#processed.form-bad` behavior, but supplement the border with a visible status badge or text such as “Form aligned” / “Adjust position.” Never rely on border color alone.
- Preserve the actual image/video elements and JS behavior.
- Use aspect-ratio containers, object-fit rules, and stable sizing to prevent layout shifts.

### 3. Telemetry hierarchy

Do not show every metric with equal visual weight. Organize telemetry into tiers:

- **Primary:** reps, correct reps, current phase, hold timer
- **Secondary:** range of motion, movement speed, fatigue score
- **Coaching alerts:** compensation warnings, form flaws, fatigue warnings

- Make the current rep count and phase easy to read from a distance.
- Use units consistently and display zero/loading/unknown values gracefully.
- Use badges, progress indicators, or compact bars where useful, but do not fabricate data.
- Use semantic states and text in addition to color.
- Make warnings prominent but not visually overwhelming.
- Keep long compensation/form-flaw strings readable and wrapped.

### 4. Coaching/instruction system

- Make `#instruction-bar` feel like a real-time coach cue, not a generic footer.
- Preserve the dynamic `#instruction-text` content from telemetry.
- Support a clear visual priority order for calibration, alignment, warm-up, movement, hold, compensation, fatigue, and completion states.
- Add a small state label or icon only if it does not conflict with the existing JS.
- Use subtle transitions, but respect `prefers-reduced-motion`.
- Ensure instruction text remains readable at a distance and on narrow screens.

### 5. Controls and safety

- Make Start Camera the primary initial action.
- Make Calibrate, Finish Calibration, Finish Session, and Restart Session visually distinct and context-sensitive.
- Clearly separate normal actions from session-ending actions.
- Do not accidentally make “Finish Session” look like a routine navigation button.
- Preserve all existing button IDs and hidden-state behavior.
- Add disabled/loading states only if they are synchronized safely with existing JS.

### 6. Live-session status and accessibility

- Add visible camera permission/connection/error states if the current JS provides enough information to support them.
- Add `aria-live` to dynamic instruction/status regions where appropriate.
- Ensure keyboard focus is visible and controls are reachable in a logical order.
- Ensure minimum touch target sizes.
- Avoid flashing or aggressive animation during movement.
- Provide a high-contrast mode or ensure the default contrast is strong enough.

## Implementation requirements

1. First inspect the entire repository and understand the existing behavior.
2. Before editing, create a concise implementation plan mapped to files.
3. Implement the redesign incrementally and preserve functionality.
4. Prefer reusable CSS custom properties and component-like class patterns.
5. Keep patient-facing copy centralized where practical.
6. Do not duplicate state or create a second source of truth for telemetry.
7. Do not change the biomechanics calculations unless a bug directly prevents the UI from representing current state correctly.
8. Do not remove support for uploaded calibration videos.
9. Do not remove support for live calibration or live rehabilitation.
10. Do not break same-tab redirects back to Streamlit.
11. Do not expose session-ticket contents or weaken validation.
12. Keep external CDN dependencies to a minimum and avoid unnecessary libraries.

## Verification checklist

After implementation:

- Run the existing app/test commands and fix errors.
- Verify the Streamlit app loads with no calibration profile.
- Verify the calibration section supports live and uploaded-video paths.
- Verify a calibrated state displays correctly.
- Verify the rehabilitation launch URL still works.
- Verify Flask live page loads with the expected exercise, mode, hold duration, and ROM.
- Verify Start Camera, Calibrate, Finish Calibration, Restart Session, and Finish Session retain their behavior.
- Verify Socket.IO telemetry continues updating the UI.
- Verify form-good/form-bad visual states still work.
- Verify instruction text updates dynamically.
- Verify session completion returns to the same Streamlit tab and displays the report.
- Verify empty/error states and missing-session redirects.
- Test at approximately 1440px desktop, 1024px tablet, and 390px mobile widths.
- Test keyboard navigation, focus states, reduced motion, and high-contrast readability.
- Check browser console and Python logs for errors.
- Summarize changed files, major UX decisions, and any behavior intentionally left unchanged.

## Expected output

Return:

1. A short audit of the existing UI and its main weaknesses.
2. A file-by-file implementation plan.
3. The completed code changes.
4. A verification report with commands run and results.
5. Any remaining risks or recommended next improvements.

Prioritize **clarity, safety, usability during physical movement, clinical trust, and preserving the existing rehabilitation behavior** over decorative effects.
