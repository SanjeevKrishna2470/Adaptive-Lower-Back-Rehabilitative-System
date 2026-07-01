// --- Connect to the Flask/Socket.IO server ---
const socket = io();

// --- Elements ---
const video = document.getElementById("webcam");
const processedImg = document.getElementById("processed");
const canvas = document.getElementById("capture-canvas");
const ctx = canvas.getContext("2d");

const exerciseSelect = document.getElementById("exercise");
const holdDurInput = document.getElementById("hold-dur");
const romMinInput = document.getElementById("rom-min");

const startBtn = document.getElementById("start-btn");
const finishBtn = document.getElementById("finish-btn");

const FRAMES_PER_SECOND = 8; // how often we send a frame to the server
let streaming = false;

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

  socket.emit("frame", {
    image: imageData,
    exercise_name: exerciseSelect.value,
    hold_dur: parseFloat(holdDurInput.value),
    rom_min: parseFloat(romMinInput.value),
  });
}

// --- Step 3: Receive the processed frame + telemetry back ---
socket.on("processed_frame", (payload) => {
  if (payload.image) {
    processedImg.src = payload.image;
  }
  updateTelemetry(payload.telemetry || {});
});

// --- Step 4: Update the right-hand panel with the latest telemetry ---
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

// --- Step 5: Tell the server the session is over and show the summary ---
finishBtn.addEventListener("click", () => {
  socket.emit("finalize_session", { exercise_name: exerciseSelect.value });
});

socket.on("session_summary", (summary) => {
  if (!summary || Object.keys(summary).length === 0) {
    alert("No repetitions were tracked during this session.");
  } else {
    alert("Session complete!\n\n" + JSON.stringify(summary, null, 2));
  }
});

// --- Wire up the start button ---
startBtn.addEventListener("click", () => {
  if (!streaming) startCamera();
});