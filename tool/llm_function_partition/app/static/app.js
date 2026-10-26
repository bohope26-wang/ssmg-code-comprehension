const sourceEl = document.getElementById("source-code");
const functionNameEl = document.getElementById("function-name");
const modelEl = document.getElementById("model");
const modeEl = document.getElementById("mode");
const maxModulesEl = document.getElementById("max-modules");
const temperatureEl = document.getElementById("temperature");
const maxCandidatesEl = document.getElementById("max-candidates");
const enableRepairEl = document.getElementById("enable-repair");
const multiCandidatesDebugEl = document.getElementById("multi-candidates-debug");
const submitBtn = document.getElementById("submit-btn");
const sampleBtn = document.getElementById("load-sample-btn");
const fileInput = document.getElementById("file-input");
const statusEl = document.getElementById("status-text");
const sourceStatsEl = document.getElementById("source-stats");
const inputHintEl = document.getElementById("input-hint");
const modeHelpEl = document.getElementById("mode-help");
const fileNameEl = document.getElementById("file-name");

const i18n = window.I18N;
const t = (key, params = {}) => (i18n ? i18n.t(key, params) : key);

const MODE_DESCRIPTIONS = {
  one_shot: "home.mode.oneShot",
  multi_stage: "home.mode.multiStage"
};

let currentStatus = { key: "home.status.idle", params: {}, state: "idle" };
let fileNameState = { key: "home.file.none", params: {} };

sampleBtn.addEventListener("click", loadSample);
submitBtn.addEventListener("click", submitPartition);
fileInput.addEventListener("change", loadFileContent);
sourceEl.addEventListener("input", updateInputState);
functionNameEl.addEventListener("input", updateInputState);
modeEl.addEventListener("change", updateModeHint);
window.addEventListener("languagechange", () => {
  updateModeHint();
  updateInputState();
  renderFileNameState();
  renderStatusState();
});

updateModeHint();
updateInputState();
loadSample();

async function loadSample() {
  try {
    setStatusKey("home.status.loadingSample", "loading");
    const response = await fetch("/api/sample", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || t("home.status.sampleFailed", { error: "" }));

    sourceEl.value = data.source_code || "";
    functionNameEl.value = data.function_name || "";
    setFileName(data.sample_path ? "home.file.sample" : "home.file.builtin", data.sample_path ? { path: data.sample_path } : {});
    updateInputState();
    setStatusKey("home.status.sampleLoaded", "ok");
  } catch (error) {
    setStatusKey("home.status.sampleFailed", "error", { error: readError(error) });
  }
}

async function loadFileContent(event) {
  const [file] = event.target.files;
  if (!file) return;
  try {
    sourceEl.value = await file.text();
    setFileName("home.file.loaded", { name: file.name });
    updateInputState();
    setStatusKey("home.status.fileLoaded", "ok", { name: file.name });
  } catch (error) {
    setStatusKey("home.status.fileFailed", "error", { error: readError(error) });
  }
}

async function submitPartition() {
  const payload = buildPayload();
  const errors = validatePayload(payload);
  if (errors.length > 0) {
    setStatusKey(errors[0], "error");
    return;
  }

  try {
    setBusy(true);
    setStatusKey("home.status.running", "loading");
    await nextFrame();

    const response = await fetch("/api/partition", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store"
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || t("result.requestFailed"));

    writeSessionJson(resultStorageKey(payload.language), data);
    writeSessionJson(requestStorageKey(payload.language), payload);
    writeSessionJson("llm_partition_result", data);
    writeSessionJson("llm_partition_request", payload);
    setStatusKey("home.status.completed", "ok");
    window.location.href = `/result.html?ts=${Date.now()}`;
  } catch (error) {
    setStatusKey("home.status.runFailed", "error", { error: readError(error) });
  } finally {
    setBusy(false);
  }
}

function buildPayload() {
  const modelName = safeTrim(modelEl.value) || "deepseek-chat";
  return {
    source_code: sourceEl.value || "",
    function_name: safeTrim(functionNameEl.value),
    model: modelName,
    mode: modeEl.value || "one_shot",
    language: currentLanguage(),
    max_modules: Number(maxModulesEl.value || 6),
    temperature: Number(temperatureEl.value || 0),
    max_candidates: Number(maxCandidatesEl.value || 3),
    enable_repair: enableRepairEl ? enableRepairEl.value === "true" : true,
    multi_candidates_debug: multiCandidatesDebugEl ? multiCandidatesDebugEl.value === "true" : false,
    llm: {
      provider: "deepseek",
      base_url: "https://api.deepseek.com",
      api_key_env: "DEEPSEEK_API_KEY",
      model_ab: modelName,
      model_c: modelName,
      timeout_sec: 120
    }
  };
}

function validatePayload(payload) {
  const errors = [];
  if (!payload.source_code.trim()) errors.push("home.error.sourceRequired");
  if (!payload.function_name) errors.push("home.error.functionRequired");
  if (Number.isNaN(payload.max_modules) || payload.max_modules < 6 || payload.max_modules > 9) {
    errors.push("home.error.maxModules");
  }
  if (Number.isNaN(payload.temperature) || payload.temperature < 0 || payload.temperature > 1) {
    errors.push("home.error.temperature");
  }
  return errors;
}

function setBusy(isBusy) {
  submitBtn.disabled = isBusy || validatePayload(buildPayload()).length > 0;
  sampleBtn.disabled = isBusy;
}

function updateInputState() {
  const source = sourceEl.value || "";
  const lineCount = source ? source.split("\n").length : 0;
  sourceStatsEl.textContent = t("home.sourceStats", { lines: lineCount, chars: source.length });

  const errors = validatePayload(buildPayload());
  const isReady = errors.length === 0;
  submitBtn.disabled = !isReady;
  inputHintEl.textContent = isReady ? t("home.inputHint.ready") : t(errors[0]);
}

function updateModeHint() {
  modeHelpEl.textContent = t(MODE_DESCRIPTIONS[modeEl.value] || MODE_DESCRIPTIONS.one_shot);
}

function setStatusKey(key, state, params = {}) {
  currentStatus = { key, params, state };
  renderStatusState();
}

function renderStatusState() {
  statusEl.textContent = t(currentStatus.key, currentStatus.params);
  statusEl.className = `status-pill ${currentStatus.state}`;
}

function setFileName(key, params = {}) {
  fileNameState = { key, params };
  renderFileNameState();
}

function renderFileNameState() {
  fileNameEl.textContent = t(fileNameState.key, fileNameState.params);
}

function currentLanguage() {
  return i18n ? i18n.getLanguage() : "en";
}

function resultStorageKey(language = currentLanguage()) {
  return `llm_partition_result::${language}`;
}

function requestStorageKey(language = currentLanguage()) {
  return `llm_partition_request::${language}`;
}

function writeSessionJson(key, value) {
  sessionStorage.setItem(key, JSON.stringify(value));
}

function setStatus(message, state) {
  statusEl.textContent = message;
  statusEl.className = `status-pill ${state}`;
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(resolve));
}

function readError(error) {
  return error && error.message ? error.message : String(error);
}

function safeTrim(value) {
  return value ? value.trim() : "";
}
