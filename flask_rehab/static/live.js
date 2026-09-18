// --- Connect to the Flask/Socket.IO server ---
const socket = io();

// --- Elements ---
const video = document.getElementById("webcam");
const processedImg = document.getElementById("processed");
const canvas = document.getElementById("capture-canvas");
const ctx = canvas.getContext("2d");

const formStatusBadge = document.getElementById("form-status-badge");
const cameraStatusPill = document.getElementById("camera-status-pill");
const liveIndicator = document.getElementById("live-indicator");
const processedPlaceholder = document.getElementById("processed-placeholder");
const fatigueProgress = document.getElementById("fatigue-progress");

// --- ALL parameters come from the injected SESSION object.
//     No UI elements exist to change these.
//     No hidden input fields are used.
const EXERCISE_NAME = window.SESSION.exercise;
const HOLD_DUR = Number(window.SESSION.holdDur);
const ROM_MIN = Number(window.SESSION.romMin);
const MODE = window.SESSION.mode;

const startBtn = document.getElementById("start-btn");
const restartBtn = document.getElementById("restart-btn");
const calibrateBtn = document.getElementById("calibrate-btn"); // only rendered in calibration mode
const finishCalibrationBtn = document.getElementById("finish-calibration-btn"); // only rendered in calibration mode
const finishBtn = document.getElementById("finish-btn");       // only rendered in rehab mode

const instructionText = document.getElementById("instruction-text");

const FRAMES_PER_SECOND = 8;
let streaming = false;
let awaitingResponse = false; // true while a frame is in flight to the server
let frameIntervalId = null;   // tracked so Restart can actually stop the loop instead of stacking a second one
let mediaStream = null;       // tracked so Restart can release the camera before re-acquiring it

// Bumped every time a session is (re)started. Sent with every outgoing
// frame and echoed back by the server on every reply. If a reply comes
// back tagged with an older generation, it's a straggler from a session
// the patient already abandoned via Restart — it gets dropped instead of
// writing that unwanted session's reps/telemetry into the current one.
let sessionGeneration = 0;

// --- Instruction bar helper ---
function updateInstruction(msg) {
  if (msg) instructionText.textContent = msg;
}

// --- Hand the browser back to Streamlit after a short delay ---
function redirectTo(url) {
  if (!url) return;
  setTimeout(() => {
    window.location.href = url;
  }, 1500);
}

// --- Release the webcam and stop the capture loop. Idempotent. ---
function stopFrameLoop() {
  if (frameIntervalId !== null) {
    clearInterval(frameIntervalId);
    frameIntervalId = null;
  }
}

function stopCameraStream() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  video.srcObject = null;
  if (cameraStatusPill) cameraStatusPill.textContent = "Standby";
  if (liveIndicator) liveIndicator.classList.remove("active");
}

// --- Step 1: Start the webcam ---
async function startCamera() {
  try {
    // Guard against a leftover interval/stream from a prior attempt
    // (e.g. Restart was clicked mid-frame) before acquiring a new one.
    stopFrameLoop();
    stopCameraStream();

    if (cameraStatusPill) cameraStatusPill.textContent = "Connecting...";

    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    mediaStream = stream;
    video.srcObject = stream;
    await video.play();

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    streaming = true;
    frameIntervalId = setInterval(sendFrame, 1000 / FRAMES_PER_SECOND);

    if (cameraStatusPill) cameraStatusPill.textContent = "Streaming";
    if (liveIndicator) liveIndicator.classList.add("active");
    if (restartBtn) restartBtn.classList.remove("hidden");
  } catch (err) {
    if (cameraStatusPill) cameraStatusPill.textContent = "Error";
    alert("Could not access webcam: " + err.message);
  }
}

// --- Step 2: Grab a frame and send it to the server ---
// Self-throttling: skip this tick if the previous frame hasn't come back
// yet, so we never queue up frames faster than the server (pose
// estimation) can actually process them. The setInterval timer just
// becomes a poll — real send rate settles at whatever the server can
// sustain instead of piling up in the socket buffer.
function sendFrame() {
  if (!streaming || video.readyState < 2 || awaitingResponse) return;

  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const imageData = canvas.toDataURL("image/jpeg", 0.7);

  awaitingResponse = true;

  // Emit exactly as required – all values are locked.
  socket.emit("frame", {
    image: imageData,
    exercise_name: EXERCISE_NAME,
    hold_dur: HOLD_DUR,
    rom_min: ROM_MIN,
    mode: MODE,
    session_generation: sessionGeneration,
  });
}

// --- Initial connection / calibration events ---
socket.on("ready", (data) => {
  awaitingResponse = false; // safety reset (e.g. after a reconnect)
  updateInstruction(data.instruction);
});

socket.on("calibration_started", (data) => {
  updateInstruction(data.instruction);
  updateFormStatus(null); // no such thing as bad form while calibrating
  if (finishCalibrationBtn) finishCalibrationBtn.classList.remove("hidden");
});

// --- Step 3: Receive the processed frame + telemetry ---
socket.on("processed_frame", (payload) => {
  awaitingResponse = false; // unblocks the next sendFrame tick

  // Straggler from a session we've since restarted — ignore it so it
  // can't overwrite the new session's reps/telemetry on screen.
  if (payload.session_generation !== undefined && payload.session_generation !== sessionGeneration) {
    return;
  }

  if (payload.image) {
    processedImg.src = payload.image;
    if (processedPlaceholder) processedPlaceholder.classList.add("hidden");
  }
  updateTelemetry(payload.telemetry || {});
  updateInstruction(payload.telemetry && payload.telemetry.instruction);
  updateFormStatus(payload.telemetry && payload.telemetry.form_status);
});

// --- Blue border = matches calibrated form (counts). Red border =
//     deviates from calibrated form (won't count). No border = still
//     calibrating / aligning starting position — there's no "bad form"
//     yet at that stage, so the server always sends "good" there.
//     Accompanied by high-contrast explicit text badge (non-reliance on color alone).
function updateFormStatus(status) {
  processedImg.classList.remove("form-good", "form-bad");
  if (status === "bad") {
    processedImg.classList.add("form-bad");
    if (formStatusBadge) {
      formStatusBadge.textContent = "Adjust Form";
      formStatusBadge.className = "status-badge badge-bad";
    }
  } else if (status === "good") {
    processedImg.classList.add("form-good");
    if (formStatusBadge) {
      formStatusBadge.textContent = "Form Aligned";
      formStatusBadge.className = "status-badge badge-good";
    }
  } else {
    if (formStatusBadge) {
      formStatusBadge.textContent = MODE === "calibration" ? "Calibrating" : "Ready";
      formStatusBadge.className = "status-badge badge-neutral";
    }
  }
}

// --- Calibration complete: stop streaming and redirect ---
socket.on("calibration_complete", (data) => {
  streaming = false;
  stopFrameLoop();
  stopCameraStream();
  updateInstruction(data.instruction);
  if (finishCalibrationBtn) finishCalibrationBtn.classList.add("hidden");
  redirectTo(data.redirect_url);
});

// --- Step 4: Update the right-hand telemetry panel ---
function updateTelemetry(t) {
  document.getElementById("t-reps").textContent = t.rep_count ?? 0;
  document.getElementById("t-correct").textContent = t.correct_rep_count ?? 0;
  document.getElementById("t-flagged").textContent = t.flagged_rep_count ?? 0;
  document.getElementById("t-phase").textContent = t.phase ?? "-";
  document.getElementById("t-rom").textContent = (t.rom ?? 0) + "°";
  document.getElementById("t-speed").textContent = (t.movement_speed ?? 0) + "°/s";
  document.getElementById("t-hold").textContent = (t.hold_time ?? 0) + "s";
  
  const fatigueScore = t.fatigue_score ?? 0;
  document.getElementById("t-fatigue").textContent = fatigueScore + "%";

  if (fatigueProgress) {
    const fatigueVal = Math.min(100, Math.max(0, fatigueScore));
    fatigueProgress.style.width = fatigueVal + "%";
    if (fatigueVal >= 70) {
      fatigueProgress.style.backgroundColor = "var(--state-deviating)";
    } else if (fatigueVal >= 40) {
      fatigueProgress.style.backgroundColor = "var(--state-caution)";
    } else {
      fatigueProgress.style.backgroundColor = "var(--teal-primary)";
    }
  }

  document.getElementById("t-warmup").textContent = t.warmup_active
    ? `Warming up (${t.warmup_reps_remaining} reps left)`
    : "Complete";

  document.getElementById("t-comp").textContent =
    t.compensations && t.compensations.length ? t.compensations.join(", ") : "None detected";

  document.getElementById("t-flaws").textContent =
    t.flaws && t.flaws.length ? t.flaws.join(", ") : "None detected";

  document.getElementById("t-fatigue-warn").textContent =
    t.fatigue_warnings && t.fatigue_warnings.length ? t.fatigue_warnings.join(" | ") : "None";
}

// Puts the right-hand panel and form-status border back to their
// fresh-page-load state — used on restart so nothing from the unwanted
// session lingers on screen even before the server confirms the reset.
function resetTelemetryDisplay() {
  updateTelemetry({});
  updateFormStatus(null);
  if (processedPlaceholder) processedPlaceholder.classList.remove("hidden");
  processedImg.removeAttribute("src");
  if (fatigueProgress) fatigueProgress.style.width = "0%";
  if (cameraStatusPill) cameraStatusPill.textContent = "Standby";
  if (liveIndicator) liveIndicator.classList.remove("active");
}

// --- Step 5: Finish session (rehab mode only) ---
if (finishBtn) {
  finishBtn.addEventListener("click", () => {
    // Emit exactly as required – locked exercise name.
    socket.emit("finalize_session", {
      exercise_name: EXERCISE_NAME,
      session_generation: sessionGeneration,
    });
  });
}

socket.on("session_summary", (summary) => {
  // Straggler from an abandoned/restarted session — don't redirect on it.
  if (summary && summary.session_generation !== undefined && summary.session_generation !== sessionGeneration) {
    return;
  }
  streaming = false;
  stopFrameLoop();
  stopCameraStream();
  updateInstruction(summary && summary.instruction);
  redirectTo(summary && summary.redirect_url);
});

// --- Restart: throw away whatever the current/previous session has
//     accumulated on the server (rep counts, calibration-in-progress,
//     compensation history, etc.) and give the patient a clean slate
//     without leaving the page.
socket.on("session_reset", (data) => {
  updateInstruction(data && data.instruction ? data.instruction : "Session reset. Ready to begin again.");
});

function restartSession() {
  // 1. Invalidate anything already in flight first, so a late reply from
  //    the old session can't sneak into the fresh one — see the
  //    session_generation checks in processed_frame/session_summary above.
  sessionGeneration += 1;
  awaitingResponse = false;

  // 2. Tear down the local capture loop/camera fully instead of layering
  //    a second interval or a second getUserMedia stream on top of it.
  streaming = false;
  stopFrameLoop();
  stopCameraStream();

  // 3. Tell the server to discard this processor's in-progress session
  //    state (rep_count, session_reps_log, calibration timer, ...) so it
  //    isn't sitting there waiting to get folded into whatever the
  //    patient finalizes next. See AdvancedRehabProcessor.reset_session()
  //    — the server's "restart_session" handler should call it.
  socket.emit("restart_session", {
    exercise_name: EXERCISE_NAME,
    session_generation: sessionGeneration,
  });

  // 4. Reset everything the UI shows back to a fresh-load state.
  resetTelemetryDisplay();
  updateInstruction("Get ready to begin your session…");
  if (finishCalibrationBtn) finishCalibrationBtn.classList.add("hidden");
  if (restartBtn) restartBtn.classList.add("hidden");
}

// --- Wire up the start button ---
startBtn.addEventListener("click", () => {
  if (!streaming) startCamera();
});

// --- Wire up the restart button ---
if (restartBtn) {
  restartBtn.addEventListener("click", restartSession);
}

// --- If the patient closes the tab or navigates away mid-session, tell
//     the server so it doesn't sit on an abandoned session's telemetry
//     waiting to be (mis)attributed to whatever comes next.
window.addEventListener("beforeunload", () => {
  if (streaming) {
    socket.emit("restart_session", {
      exercise_name: EXERCISE_NAME,
      session_generation: sessionGeneration,
    });
  }
});

// --- Wire up the calibrate button (calibration mode only) ---
if (calibrateBtn) {
  calibrateBtn.addEventListener("click", () => {
    if (!streaming) {
      alert("Start the camera first, then calibrate.");
      return;
    }
    socket.emit("start_calibration");
  });
}

// --- Wire up the manual Finish Calibration button (calibration mode only) ---
// A safety net in case the automatic ~3s timer never completes cleanly
// (e.g. posture briefly not detected) — lets the patient/clinician force
// calibration through using whatever posture reading was last captured.
if (finishCalibrationBtn) {
  finishCalibrationBtn.addEventListener("click", () => {
    socket.emit("finish_calibration_now", {
      exercise_name: EXERCISE_NAME,
      session_generation: sessionGeneration,
    });
  });
}