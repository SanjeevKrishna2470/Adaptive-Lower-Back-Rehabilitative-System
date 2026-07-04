// --- Connect to the Flask/Socket.IO server ---
const socket = io();

// --- Elements ---
const video = document.getElementById("webcam");
const processedImg = document.getElementById("processed");
const canvas = document.getElementById("capture-canvas");
const ctx = canvas.getContext("2d");

// --- ALL parameters come from the injected SESSION object.
//     No UI elements exist to change these.
//     No hidden input fields are used.
const EXERCISE_NAME = window.SESSION.exercise;
const HOLD_DUR = Number(window.SESSION.holdDur);
const ROM_MIN = Number(window.SESSION.romMin);
const MODE = window.SESSION.mode;

const startBtn = document.getElementById("start-btn");
const calibrateBtn = document.getElementById("calibrate-btn"); // only rendered in calibration mode
const finishBtn = document.getElementById("finish-btn");       // only rendered in rehab mode

const instructionText = document.getElementById("instruction-text");

const FRAMES_PER_SECOND = 8;
let streaming = false;

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

// --- Step 1: Start the webcam ---
async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = stream;
    await video.play();

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    streaming = true;
    setInterval(sendFrame, 1000 / FRAMES_PER_SECOND);
  } catch (err) {
    alert("Could not access webcam: " + err.message);
  }
}

// --- Step 2: Grab a frame and send it to the server ---
function sendFrame() {
  if (!streaming || video.readyState < 2) return;

  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const imageData = canvas.toDataURL("image/jpeg", 0.7);

  // Emit exactly as required – all values are locked.
  socket.emit("frame", {
    image: imageData,
    exercise_name: EXERCISE_NAME,
    hold_dur: HOLD_DUR,
    rom_min: ROM_MIN,
    mode: MODE,
  });
}

// --- Initial connection / calibration events ---
socket.on("ready", (data) => {
  updateInstruction(data.instruction);
});

socket.on("calibration_started", (data) => {
  updateInstruction(data.instruction);
});

// --- Step 3: Receive the processed frame + telemetry ---
socket.on("processed_frame", (payload) => {
  if (payload.image) {
    processedImg.src = payload.image;
  }
  updateTelemetry(payload.telemetry || {});
  updateInstruction(payload.telemetry && payload.telemetry.instruction);
});

// --- Calibration complete: stop streaming and redirect ---
socket.on("calibration_complete", (data) => {
  streaming = false;
  updateInstruction(data.instruction);
  redirectTo(data.redirect_url);
});

// --- Step 4: Update the right-hand telemetry panel ---
function updateTelemetry(t) {
  document.getElementById("t-reps").textContent = t.rep_count ?? 0;
  document.getElementById("t-correct").textContent = t.correct_rep_count ?? 0;
  document.getElementById("t-phase").textContent = t.phase ?? "-";
  document.getElementById("t-rom").textContent = (t.rom ?? 0) + "°";
  document.getElementById("t-speed").textContent = (t.movement_speed ?? 0) + "°/s";
  document.getElementById("t-hold").textContent = (t.hold_time ?? 0) + "s";
  document.getElementById("t-fatigue").textContent = (t.fatigue_score ?? 0) + "%";

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

// --- Step 5: Finish session (rehab mode only) ---
if (finishBtn) {
  finishBtn.addEventListener("click", () => {
    // Emit exactly as required – locked exercise name.
    socket.emit("finalize_session", {
      exercise_name: EXERCISE_NAME
    });
  });
}

socket.on("session_summary", (summary) => {
  streaming = false;
  updateInstruction(summary && summary.instruction);
  redirectTo(summary && summary.redirect_url);
});

// --- Wire up the start button ---
startBtn.addEventListener("click", () => {
  if (!streaming) startCamera();
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