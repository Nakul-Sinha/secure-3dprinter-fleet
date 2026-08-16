// Phase 0 shell script. Confirms the backend is reachable.
async function checkHealth() {
  const pill = document.getElementById("status-pill");
  const out = document.getElementById("health");
  try {
    const res = await fetch("/health");
    const body = await res.json();
    pill.textContent = body.status === "ok" ? "online" : "degraded";
    pill.classList.toggle("ok", body.status === "ok");
    out.textContent = JSON.stringify(body, null, 2);
  } catch (e) {
    pill.textContent = "offline";
    out.textContent = String(e);
  }
}

document.addEventListener("DOMContentLoaded", checkHealth);
