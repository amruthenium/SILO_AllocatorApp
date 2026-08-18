function checkShapefileBundle(files){
  const name = files.map((f) => f.name.toLowerCase());
  const hasShp = names.some((n) => n.endsWith(".shp"));
  if (!hasShp) return;
  const missing =[".shx", ".dbf"].filter(
    (ext) => !names.some((n) => n.endsWith(ext))
  );
  if (missing.length) {
    alert(
      `A .shp needs its sidecar files too. Missing: ${missing.join(", ")}.\n` +
      `Select the .shp, .shx and .dbf (and .prj) together — on Windows, ` +
      `click the first, then Shift/Ctrl-click the rest.`
    );
  }
}

async function uploadFile(inputEl) {
  const files = Array.from(inputEl.files || []);
  if (!files.length) return null;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (data.error) {
    alert(`Upload failed: ${data.error}`);
    return null;
  }
  inputEl.dataset.path = data.path;
  inputEl.title = `Using: ${data.name}`;
  return data.path;
}

function collectParams(stageEl) {
  const params = {};
  stageEl.querySelectorAll("[data-role]").forEach((el) => {
    const key = el.dataset.role;
    if (el.type === "file") {
      params[key] = el.dataset.path || "";
    } else {
      params[key] = el.value || "";
    }
  });
  return params;
}

function isOptional(el, stageEl){
  if (el.dataset.optional === "true") return true;
  const dependsOn = el.dataset.optionalIf;
  if (!dependsOn) return false;
  return dependsOn.split(",").every((role) => {
    const other = stageEl.querySelector(`[data-role="${role.trim()}"]`);
    if (!other) return false;
    const val = other.type === "file" ? other.dataset.path : other.value;
    return !!val;
  });
}

function findMissingFields(stageEl) {
  const missing = [];
  stageEl.querySelectorAll("[data-role]").forEach((el) => {
    const val = el.type === "file" ? el.dataset.path : el.value;
    if (!val && !isOptional(el, stageEl)) missing.push(el.dataset.role);
  });
  return missing;
}

function logLine(consoleEl, line) {
  const isErr = /^ERROR/.test(line);
  const span = document.createElement("div");
  if (isErr) span.className = "err";
  span.textContent = line;
  consoleEl.appendChild(span);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

async function pollJob(jobId, consoleEl, outputsEl, btn) {
  let seen = 0;
  const timer = setInterval(async () => {
    const res = await fetch(`/api/status/${jobId}`);
    const job = await res.json();
    while (seen < job.log.length) {
      logLine(consoleEl, job.log[seen]);
      seen += 1;
    }
    if (job.status === "done" || job.status === "error") {
      clearInterval(timer);
      btn.disabled = false;
      btn.textContent = btn.dataset.originalLabel;
      if (job.status === "done" && job.outputs) {
        outputsEl.innerHTML = "";
        Object.entries(job.outputs).forEach(([name, path]) => {
          const a = document.createElement("a");
          a.href = `/api/download?path=${encodeURIComponent(path)}`;
          a.textContent = `↓ ${name}`;
          outputsEl.appendChild(a);
        });
      }
      if (job.status === "error") {
        logLine(consoleEl, `ERROR: ${job.error}`);
      }
    }
  }, 900);
}

document.querySelectorAll(".stage").forEach((stageEl) => {
  const step = stageEl.dataset.step;
  const btn = stageEl.querySelector(".run-btn");
  const consoleEl = stageEl.querySelector("[data-console]");
  const outputsEl = stageEl.querySelector("[data-outputs]");
  btn.dataset.originalLabel = btn.textContent;

  const pendingUploads = new Set();

  stageEl.querySelectorAll('input[type="file"]').forEach((inputEl) => {
    inputEl.addEventListener("change", () => {
      const p = uploadFile(inputEl).finally(() => pendingUploads.delete(p));
      pendingUploads.add(p);
    });
  });

  btn.addEventListener("click", async () => {
    if (pendingUploads.size) {
      btn.disabled = true;
      btn.textContent = "Waiting for uploads…";
      await Promise.all(pendingUploads);
      btn.textContent = btn.dataset.originalLabel;
      btn.disabled = false;
    }

    const missing = findMissingFields(stageEl);
    if (missing.length) {
      alert(
        `Still missing: ${missing.join(", ")}.\n` +
        `Pick the file(s) for each field above before running this stage — ` +
        `if you just reloaded the page, your previous selections were cleared, so choose them again.`
      );
      return;
    }

    consoleEl.classList.add("visible");
    consoleEl.innerHTML = "";
    outputsEl.innerHTML = "";
    btn.disabled = true;
    btn.textContent = "Running…";


    const params = collectParams(stageEl);
    try {
      const res = await fetch(`/api/step/${step}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      const data = await res.json();
      if (!data.job_id) {
        logLine(consoleEl, `ERROR: ${data.error || "could not start step"}`);
        btn.disabled = false;
        btn.textContent = btn.dataset.originalLabel;
        return;
      }
      pollJob(data.job_id, consoleEl, outputsEl, btn);
    } catch (err) {
      logLine(consoleEl, `ERROR: ${err}`);
      btn.disabled = false;
      btn.textContent = btn.dataset.originalLabel;
    }
  });
});
