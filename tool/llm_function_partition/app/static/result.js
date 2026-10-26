const i18n = window.I18N;
const t = (key, params = {}) => (i18n ? i18n.t(key, params) : key);
const currentLanguage = () => (i18n ? i18n.getLanguage() : "en");

const resultData = readResultData();
const requestData = readRequestData();

const TEXT = {
  get emptySelection() { return t("result.selectionEmpty"); },
  get noFunctionSummary() { return t("result.noFunctionSummary"); },
  get noDescription() { return t("result.noDescription"); },
  get noModuleSummary() { return t("result.noModuleSummary"); },
  get noIntentSummary() { return t("result.noIntentSummary"); },
  get none() { return t("common.none"); },
  get rerunFailed() { return t("result.rerunFailed"); },
  get missingData() { return t("result.missingData"); }
};

const sourceViewerEl = document.getElementById("source-viewer");
const warningsEl = document.getElementById("warnings");
const moduleSummaryEl = document.getElementById("module-summary");
const cfgSummaryEl = document.getElementById("cfg-summary");
const modulesListEl = document.getElementById("modules-list");
const detailsBoxEl = document.getElementById("details-box");
const functionSummaryEl = document.getElementById("function-summary");
const rawResponseEl = document.getElementById("raw-response");
const codeFocusLabelEl = document.getElementById("code-focus-label");
const titleEl = document.getElementById("workspace-title");
const subtitleEl = document.getElementById("workspace-subtitle");
const backBtn = document.getElementById("back-btn");
const reloadBtn = document.getElementById("reload-btn");
const variableTraceBtn = document.getElementById("variable-trace-btn");
const memoryBoardBtn = document.getElementById("memory-board-btn");
const taskModeBtn = document.getElementById("task-mode-btn");
const selectionSummaryEl = document.getElementById("selection-summary");
const openSubcfgBtn = document.getElementById("open-subcfg-btn");
const openEvidenceBtn = document.getElementById("open-evidence-btn");
const openDetailsBtn = document.getElementById("open-details-btn");
const resetCfgBtn = document.getElementById("reset-cfg-btn");
const moduleSummaryStripEl = document.getElementById("module-summary-strip");
const evidenceSummaryEl = document.getElementById("evidence-summary");
const evidenceChainViewEl = document.getElementById("evidence-chain-view");
const stageAbJsonEl = document.getElementById("stage-ab-json");
const stageCJsonEl = document.getElementById("stage-c-json");
const stageDJsonEl = document.getElementById("stage-d-json");
const metricBlocksEl = document.getElementById("metric-blocks");
const metricModulesEl = document.getElementById("metric-modules");
const metricModeEl = document.getElementById("metric-mode");
const globalMessageEl = document.getElementById("global-message");
const memoryBoardPanelEl = document.getElementById("memory-board-panel");
const memoryBoardInputEl = document.getElementById("memory-board-input");
const memoryCloseBtn = document.getElementById("memory-close-btn");
const memoryExportBtn = document.getElementById("memory-export-btn");
const taskModePanelEl = document.getElementById("task-mode-panel");
const taskCloseBtn = document.getElementById("task-close-btn");
const taskRefreshBtn = document.getElementById("task-refresh-btn");
const taskStatusEl = document.getElementById("task-status");
const taskQuizContentEl = document.getElementById("task-quiz-content");
const taskSubmitBtn = document.getElementById("task-submit-btn");
const variableTracePanelEl = document.getElementById("variable-trace-panel");
const traceCloseBtn = document.getElementById("trace-close-btn");
const traceVariableInputEl = document.getElementById("trace-variable-input");
const traceAutoExplainEl = document.getElementById("trace-auto-explain");
const traceRunBtn = document.getElementById("trace-run-btn");
const traceExplainBtn = document.getElementById("trace-explain-btn");
const traceStatusEl = document.getElementById("trace-status");
const traceSummaryEl = document.getElementById("trace-summary");
const traceTimelineEl = document.getElementById("trace-timeline");
const traceExplanationEl = document.getElementById("trace-explanation");

const stageOutputs = resultData?.stage_outputs || {};
const moduleEvidenceData = resultData?.module_evidence || null;
const moduleEvidenceById = new Map(
  ((moduleEvidenceData && moduleEvidenceData.module_evidence) || []).map((item) => [item.module_id, item])
);
const stageDByModuleId = new Map(
  ((stageOutputs.stage_d && stageOutputs.stage_d.module_metadata) || []).map((item) => [item.module_id, item])
);
const resultIdentityKey = resultData
  ? `${currentLanguage()}::${resultData.function_name || "unknown"}::${resultData.mode || "unknown"}::${(resultData.cfg?.function_source || "").length}`
  : "missing";
const memoryBoardStorageKey = `memory_board::${resultIdentityKey}`;
const memoryBoardPanelStateKey = `memory_board_panel::${resultIdentityKey}`;
const taskPanelStateKey = `task_mode_panel::${resultIdentityKey}`;
const tracePanelStateKey = `variable_trace_panel::${resultIdentityKey}`;

let cfgCy = null;
let moduleCy = null;
let cfgGraphResizeObserver = null;
let moduleGraphResizeObserver = null;
let sourceLines = [];
let activeCfgModuleId = null;
let floatingPanelZIndex = 60;
let currentSelection = {
  type: null,
  moduleId: null,
  bbId: null,
  detailText: "",
  summaryText: TEXT.emptySelection
};
let taskQuizState = {
  questions: [],
  answers: {},
  submitted: false,
  loading: false,
  generationMode: "llm",
  warning: "",
  error: "",
};
let variableTraceState = {
  loading: false,
  explaining: false,
  trace: null,
  explanation: null,
  error: "",
};

const palette = ["#0b4f8a", "#00796b", "#875600", "#6b46c1", "#8e2f3f", "#17613b", "#1f5e7a", "#7b3f00"];

backBtn.addEventListener("click", () => {
  window.location.href = "/";
});
reloadBtn.addEventListener("click", rerunRequest);
window.addEventListener("languagechange", () => {
  window.location.reload();
});

if (!resultData || !requestData) {
  renderMissingDataState();
} else {
  init();
}

function init() {
  const bbCount = resultData.cfg?.bb_nodes?.length || 0;
  const moduleCount = resultData.module_graph?.modules?.length || 0;
  const mode = resultData.mode || requestData.mode || "unknown";

  titleEl.textContent = t("result.headingWithFunction", { name: resultData.function_name || t("result.unknownFunction") });
  subtitleEl.textContent = t("result.subtitleCounts", { blocks: bbCount, modules: moduleCount });
  metricBlocksEl.textContent = String(bbCount);
  metricModulesEl.textContent = String(moduleCount);
  metricModeEl.textContent = formatMode(mode);

  const warnings = resultData.debug?.warnings || [];
  warningsEl.textContent = warnings.length > 0 ? warnings.join(" | ") : t("result.noWarnings");
  warningsEl.classList.toggle("warning-active", warnings.length > 0);

  if (functionSummaryEl) {
    functionSummaryEl.textContent = resultData.debug?.function_summary || TEXT.noFunctionSummary;
  }
  if (rawResponseEl) {
    rawResponseEl.textContent = truncateText(resultData.debug?.raw_response_text || "", 3200) || t("result.noRawResponse");
  }

  sourceLines = buildSourceLines(resultData.cfg?.function_source || requestData.source_code || "");
  renderSource();
  renderModuleList();
  renderModuleSummaryStrip();
  openSubcfgBtn.addEventListener("click", openSubCfgView);
  openEvidenceBtn.addEventListener("click", openEvidenceView);
  openDetailsBtn.addEventListener("click", openSelectionDetails);
  if (variableTraceBtn) variableTraceBtn.addEventListener("click", openVariableTracePanel);
  if (memoryBoardBtn) memoryBoardBtn.addEventListener("click", openMemoryBoard);
  if (taskModeBtn) taskModeBtn.addEventListener("click", openTaskModePanel);
  if (traceCloseBtn) traceCloseBtn.addEventListener("click", () => closeFloatingPanel(variableTracePanelEl));
  if (traceRunBtn) traceRunBtn.addEventListener("click", requestVariableTrace);
  if (traceExplainBtn) traceExplainBtn.addEventListener("click", requestVariableTraceExplanation);
  if (traceVariableInputEl) {
    traceVariableInputEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        requestVariableTrace();
      }
    });
  }
  if (memoryCloseBtn) memoryCloseBtn.addEventListener("click", () => closeFloatingPanel(memoryBoardPanelEl));
  if (taskCloseBtn) taskCloseBtn.addEventListener("click", () => closeFloatingPanel(taskModePanelEl));
  if (memoryExportBtn) memoryExportBtn.addEventListener("click", exportMemoryBoardMarkdown);
  if (taskRefreshBtn) taskRefreshBtn.addEventListener("click", () => requestTaskQuiz(true));
  if (taskSubmitBtn) taskSubmitBtn.addEventListener("click", submitTaskAnswers);
  if (memoryBoardInputEl) memoryBoardInputEl.addEventListener("input", persistMemoryBoardContent);
  renderModuleGraph();
  renderCfgGraph(null);
  renderStageOutputs();
  setupFloatingPanel(memoryBoardPanelEl, memoryBoardPanelStateKey, { top: 116, left: window.innerWidth - 452, width: 420, height: 420 });
  setupFloatingPanel(taskModePanelEl, taskPanelStateKey, { top: 146, left: Math.max(24, window.innerWidth - 932), width: 460, height: 560 });
  setupFloatingPanel(variableTracePanelEl, tracePanelStateKey, { top: 102, left: Math.max(18, window.innerWidth / 2 - 560), width: 1120, height: 680 });
  loadMemoryBoardContent();
  renderTaskQuiz();
  renderVariableTraceState();
  updateSelectionToolbar();
  wireTabs();
  resetCfgBtn.addEventListener("click", () => {
    activeCfgModuleId = null;
    renderCfgGraph(null);
    activateTab("cfg-graph");
  });
}

async function rerunRequest() {
  try {
    reloadBtn.disabled = true;
    showGlobalMessage(t("result.rerunning"), "loading");
    const rerunPayload = { ...requestData, language: currentLanguage() };

    const response = await fetch("/api/partition", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rerunPayload),
      cache: "no-store"
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || t("result.requestFailed"));

    writeSessionJson(resultStorageKey(currentLanguage()), data);
    writeSessionJson(requestStorageKey(currentLanguage()), rerunPayload);
    writeSessionJson("llm_partition_result", data);
    showGlobalMessage(t("result.rerunComplete"), "ok");
    window.location.href = `/result.html?ts=${Date.now()}`;
  } catch (error) {
    const message = `${TEXT.rerunFailed}: ${readError(error)}`;
    detailsBoxEl.textContent = message;
    showGlobalMessage(message, "error");
  } finally {
    reloadBtn.disabled = false;
  }
}

function refreshLocalizedResultView() {
  if (!resultData || !requestData) {
    renderMissingDataState();
    return;
  }

  const bbCount = resultData.cfg?.bb_nodes?.length || 0;
  const moduleCount = resultData.module_graph?.modules?.length || 0;
  titleEl.textContent = t("result.headingWithFunction", { name: resultData.function_name || t("result.unknownFunction") });
  subtitleEl.textContent = t("result.subtitleCounts", { blocks: bbCount, modules: moduleCount });
  const warnings = resultData.debug?.warnings || [];
  warningsEl.textContent = warnings.length > 0 ? warnings.join(" | ") : t("result.noWarnings");

  renderModuleList();
  renderModuleSummaryStrip();
  renderModuleGraph();
  renderCfgGraph(activeCfgModuleId);
  renderSource();
  renderTaskQuiz();
  renderVariableTraceState();

  if (currentSelection.type === "module" && currentSelection.moduleId) {
    focusModule(currentSelection.moduleId);
  } else if (currentSelection.type === "bb" && currentSelection.bbId) {
    focusBb(currentSelection.bbId);
  } else {
    currentSelection.summaryText = TEXT.emptySelection;
    updateSelectionToolbar();
  }
}

function wireTabs() {
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((item) => {
        item.classList.remove("active");
        item.setAttribute("aria-selected", "false");
      });
      document.querySelectorAll(".view-panel").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      button.setAttribute("aria-selected", "true");
      document.getElementById(`view-${button.dataset.view}`).classList.add("active");
      if (button.dataset.view === "cfg-graph" && cfgCy) cfgCy.resize();
      if (button.dataset.view === "module-graph" && moduleCy) moduleCy.resize();
    });
  });
}

function disconnectGraphResizeObserver(type) {
  if (type === "module" && moduleGraphResizeObserver) {
    moduleGraphResizeObserver.disconnect();
    moduleGraphResizeObserver = null;
  }
  if (type === "cfg" && cfgGraphResizeObserver) {
    cfgGraphResizeObserver.disconnect();
    cfgGraphResizeObserver = null;
  }
}

function attachGraphResizeObserver(type, container, cy) {
  disconnectGraphResizeObserver(type);
  if (!container || !cy || typeof ResizeObserver !== "function") return;

  const observer = new ResizeObserver(() => {
    window.requestAnimationFrame(() => {
      try {
        if (!cy.destroyed || !cy.destroyed()) cy.resize();
      } catch (_error) {
        disconnectGraphResizeObserver(type);
      }
    });
  });
  observer.observe(container);

  if (type === "module") moduleGraphResizeObserver = observer;
  if (type === "cfg") cfgGraphResizeObserver = observer;
}

function renderStageOutputs() {
  const hasStages = stageOutputs && Object.keys(stageOutputs).length > 0;
  const stageTabEl = document.getElementById("tab-stages");
  const stagePanelEl = document.getElementById("view-stages");

  if (!hasStages) {
    if (stageTabEl) stageTabEl.style.display = "none";
    if (stagePanelEl) stagePanelEl.style.display = "none";
    return;
  }

  if (stageAbJsonEl) stageAbJsonEl.textContent = JSON.stringify(stageOutputs.stage_ab || {}, null, 2);
  if (stageCJsonEl) stageCJsonEl.textContent = JSON.stringify(stageOutputs.stage_c || {}, null, 2);
  if (stageDJsonEl) stageDJsonEl.textContent = JSON.stringify(stageOutputs.stage_d || {}, null, 2);
}

function renderModuleList() {
  const modules = resultData.module_graph?.modules || [];
  if (modules.length === 0) {
    modulesListEl.innerHTML = `<div class="empty-card">${escapeHtml(t("result.noModuleData"))}</div>`;
    return;
  }

  modulesListEl.innerHTML = modules
    .map((module, index) => buildModuleCard(module, index, palette[index % palette.length]))
    .join("");
  bindModuleActionHandlers(modulesListEl);
}

function renderModuleSummaryStrip() {
  if (!moduleSummaryStripEl) return;
  const modules = resultData.module_graph?.modules || [];
  if (modules.length === 0) {
    moduleSummaryStripEl.innerHTML = `<div class="empty-card">${escapeHtml(t("result.noModulesSummary"))}</div>`;
    return;
  }

  moduleSummaryStripEl.innerHTML = modules
    .map((module, index) => {
      const color = palette[index % palette.length];
      return `
        <article class="module-summary-card" data-module-id="${module.id}" style="--module-color:${color}">
          <div class="module-summary-title">
            <span>${index + 1}. ${escapeHtml(module.name)}</span>
            <span>${escapeHtml(module.id)}</span>
          </div>
          <p class="module-summary-desc">${escapeHtml(module.description || TEXT.noDescription)}</p>
          <p class="module-summary-meta">${escapeHtml(t("result.blocks", { count: module.bb_ids.length }))}</p>
          <div class="module-card-actions">
            <button class="module-action-btn" type="button" data-action="subcfg" data-module-id="${module.id}">${escapeHtml(t("result.subCfg"))}</button>
            <button class="module-action-btn" type="button" data-action="evidence" data-module-id="${module.id}">${escapeHtml(t("result.evidenceChain"))}</button>
            <button class="module-action-btn" type="button" data-action="details" data-module-id="${module.id}">${escapeHtml(t("result.details"))}</button>
          </div>
        </article>`;
    })
    .join("");

  moduleSummaryStripEl
    .querySelectorAll(".module-summary-card")
    .forEach((card) => card.addEventListener("click", () => focusModule(card.dataset.moduleId)));
  bindModuleActionHandlers(moduleSummaryStripEl);
}

function bindModuleActionHandlers(container) {
  container.querySelectorAll(".module-card").forEach((item) => {
    item.addEventListener("click", () => focusModule(item.dataset.moduleId));
  });
  container.querySelectorAll(".module-action-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      focusModule(button.dataset.moduleId);
      if (button.dataset.action === "subcfg") openSubCfgView();
      if (button.dataset.action === "evidence") openEvidenceView();
      if (button.dataset.action === "details") openSelectionDetails();
    });
  });
}

function buildModuleCard(module, index, color) {
  return `
    <article class="module-card" data-module-id="${module.id}" style="--module-color:${color}">
      <div class="module-card-head">
        <strong>${index + 1}. ${escapeHtml(module.name)}</strong>
        <span>${escapeHtml(module.id)}</span>
      </div>
      <p class="module-desc">${escapeHtml(module.description || TEXT.noDescription)}</p>
      <p class="module-meta">${escapeHtml(t("result.blocks", { count: module.bb_ids.length }))}</p>
      <div class="chip-row">${module.bb_ids.map((bbId) => `<span class="chip">${escapeHtml(bbId)}</span>`).join("")}</div>
      <div class="module-card-actions">
        <button class="module-action-btn" type="button" data-action="subcfg" data-module-id="${module.id}">${escapeHtml(t("result.subCfg"))}</button>
        <button class="module-action-btn" type="button" data-action="evidence" data-module-id="${module.id}">${escapeHtml(t("result.evidenceChain"))}</button>
        <button class="module-action-btn" type="button" data-action="details" data-module-id="${module.id}">${escapeHtml(t("result.details"))}</button>
      </div>
    </article>`;
}

function renderModuleGraph() {
  const modules = resultData.module_graph?.modules || [];
  const edges = resultData.module_graph?.edges || [];
  const container = document.getElementById("module-graph");
  moduleSummaryEl.textContent = t("common.modules", { count: modules.length });

  if (modules.length === 0) {
    disconnectGraphResizeObserver("module");
    if (moduleCy) moduleCy.destroy();
    moduleCy = null;
    container.innerHTML = `<div class="graph-empty">${escapeHtml(t("result.noModuleGraph"))}</div>`;
    return;
  }

  if (typeof window.cytoscape !== "function") {
    disconnectGraphResizeObserver("module");
    if (moduleCy) moduleCy.destroy();
    moduleCy = null;
    container.innerHTML = `<div class="graph-empty">${escapeHtml(t("result.moduleGraphUnavailable"))}</div>`;
    return;
  }

  const elements = [];
  modules.forEach((module, index) => {
    elements.push({
      data: {
        id: module.id,
        label: buildModuleGraphLabel(module, index),
        color: palette[index % palette.length],
        payload: JSON.stringify(module)
      }
    });
  });
  edges.forEach((edge, index) => {
    elements.push({ data: { id: `me-${index}`, source: edge.from, target: edge.to } });
  });

  disconnectGraphResizeObserver("module");
  if (moduleCy) moduleCy.destroy();
  container.innerHTML = "";
  moduleCy = cytoscape({
    container,
    elements,
    minZoom: 0.45,
    maxZoom: 3.0,
    wheelSensitivity: 0.16,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#f7fbff",
          "border-width": 2,
          "border-color": "data(color)",
          color: "#0f172a",
          label: "data(label)",
          "font-size": 30,
          "font-weight": 600,
          "text-wrap": "wrap",
          "text-max-width": 260,
          "text-justification": "center",
          "text-valign": "center",
          "text-halign": "center",
          "line-height": 1.3,
          width: 286,
          height: 150,
          shape: "round-rectangle",
          padding: "10px"
        }
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "line-color": "#64748b",
          "target-arrow-color": "#64748b",
          width: 1.8
        }
      },
      { selector: ".faded", style: { opacity: 0.2 } },
      { selector: ".selected", style: { "border-color": "#0f172a", "border-width": 3 } }
    ],
    layout: {
      name: "cose",
      animate: false,
      padding: 18,
      nodeRepulsion: 120000,
      idealEdgeLength: 82,
      edgeElasticity: 120,
      gravity: 1.25,
      componentSpacing: 48
    }
  });

  attachGraphResizeObserver("module", container, moduleCy);
  moduleCy.on("tap", "node", (event) => focusModule(event.target.id()));
}

function renderCfgGraph(moduleId) {
  activeCfgModuleId = moduleId || null;
  const graphData = activeCfgModuleId ? resultData.cfg_by_module?.[activeCfgModuleId] : resultData.cfg;
  const container = document.getElementById("cfg-graph");
  if (!graphData || !graphData.bb_nodes) {
    disconnectGraphResizeObserver("cfg");
    if (cfgCy) cfgCy.destroy();
    cfgCy = null;
    container.innerHTML = `<div class="graph-empty">${escapeHtml(t("result.noCfg"))}</div>`;
    cfgSummaryEl.textContent = t("result.cfgUnavailable");
    return;
  }

  if (typeof window.cytoscape !== "function") {
    disconnectGraphResizeObserver("cfg");
    if (cfgCy) cfgCy.destroy();
    cfgCy = null;
    container.innerHTML = `<div class="graph-empty">${escapeHtml(t("result.cfgGraphUnavailable"))}</div>`;
    const bbCount = graphData.bb_nodes.length;
    const edgeCount = (graphData.cfg_edges || []).length;
    cfgSummaryEl.textContent = activeCfgModuleId
      ? t("result.moduleScope", { blocks: bbCount, edges: edgeCount, module: activeCfgModuleId })
      : t("common.blocksEdges", { blocks: bbCount, edges: edgeCount });
    resetCfgBtn.disabled = !activeCfgModuleId;
    return;
  }

  const colorByModule = {};
  (resultData.module_graph?.modules || []).forEach((module, index) => {
    colorByModule[module.id] = palette[index % palette.length];
  });

  const elements = [];
  graphData.bb_nodes.forEach((node) => {
    const nodeModuleId = resultData.partition?.[node.id] || t("result.unassigned");
    elements.push({
      data: {
        id: node.id,
        label: buildBbGraphLabel(node),
        moduleId: nodeModuleId,
        color: colorByModule[nodeModuleId] || "#6b7280",
        payload: JSON.stringify(node)
      }
    });
  });
  (graphData.cfg_edges || []).forEach((edge, index) => {
    elements.push({
      data: {
        id: `ce-${index}`,
        source: edge.from,
        target: edge.to,
        label: edge.type || ""
      }
    });
  });

  disconnectGraphResizeObserver("cfg");
  if (cfgCy) cfgCy.destroy();
  container.innerHTML = "";
  cfgCy = cytoscape({
    container,
    elements,
    minZoom: 0.42,
    maxZoom: 3.0,
    wheelSensitivity: 0.16,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#ffffff",
          "border-width": 2,
          "border-color": "data(color)",
          color: "#0f172a",
          label: "data(label)",
          "font-size": 18,
          "font-weight": 600,
          "text-wrap": "wrap",
          "text-max-width": 260,
          "text-valign": "center",
          "text-halign": "center",
          "line-height": 1.3,
          shape: "round-rectangle",
          padding: "9px",
          width: 286,
          height: 124
        }
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "line-color": "#94a3b8",
          "target-arrow-color": "#94a3b8",
          label: "data(label)",
          "font-size": 15,
          color: "#475569",
          "text-background-color": "#f8fafc",
          "text-background-opacity": 1,
          "text-background-padding": 3,
          width: 1.9
        }
      },
      { selector: ".faded", style: { opacity: 0.2 } },
      { selector: ".selected", style: { "border-color": "#0f172a", "border-width": 3 } }
    ],
    layout: { name: "breadthfirst", directed: true, padding: 20, spacingFactor: 1.05 }
  });

  attachGraphResizeObserver("cfg", container, cfgCy);
  cfgCy.on("tap", "node", (event) => {
    const payload = JSON.parse(event.target.data("payload"));
    focusBb(payload.id);
  });

  const bbCount = graphData.bb_nodes.length;
  const edgeCount = (graphData.cfg_edges || []).length;
  cfgSummaryEl.textContent = activeCfgModuleId
    ? t("result.moduleScope", { blocks: bbCount, edges: edgeCount, module: activeCfgModuleId })
    : t("common.blocksEdges", { blocks: bbCount, edges: edgeCount });
  resetCfgBtn.disabled = !activeCfgModuleId;
}

function focusModule(moduleId) {
  const module = (resultData.module_graph?.modules || []).find((item) => item.id === moduleId);
  if (!module) return;

  document.querySelectorAll(".module-card").forEach((item) => {
    item.classList.toggle("active", item.dataset.moduleId === moduleId);
  });
  document.querySelectorAll(".module-summary-card").forEach((item) => {
    item.classList.toggle("active", item.dataset.moduleId === moduleId);
  });

  if (cfgCy) {
    cfgCy.elements().addClass("faded");
    cfgCy.edges().removeClass("faded");
    cfgCy.nodes().removeClass("selected");
    const targetNodes = cfgCy.nodes().filter((node) => node.data("moduleId") === moduleId);
    targetNodes.forEach((node) => node.removeClass("faded").addClass("selected"));
    if (targetNodes.length > 0) cfgCy.fit(targetNodes, 50);
  }

  if (moduleCy) {
    moduleCy.elements().addClass("faded");
    moduleCy.nodes().removeClass("selected");
    moduleCy.$id(moduleId).removeClass("faded").addClass("selected");
    moduleCy.edges().forEach((edge) => {
      if (edge.source().id() === moduleId || edge.target().id() === moduleId) {
        edge.removeClass("faded");
        edge.source().removeClass("faded");
        edge.target().removeClass("faded");
      }
    });
  }

  highlightLines(collectModuleLines(moduleId), true);
  codeFocusLabelEl.textContent = t("common.highlightModule", { name: module.name });
  currentSelection = {
    type: "module",
    moduleId,
    bbId: null,
    detailText: buildModuleDetails(module),
    summaryText: `${module.name}: ${module.description || TEXT.noModuleSummary}`
  };
  renderEvidenceView(moduleId);
  updateSelectionToolbar();
}

function focusBb(bbId) {
  const node = (resultData.cfg?.bb_nodes || []).find((item) => item.id === bbId);
  if (!node) return;

  const moduleId = resultData.partition?.[bbId] || null;
  const module = (resultData.module_graph?.modules || []).find((item) => item.id === moduleId) || null;

  if (cfgCy) {
    cfgCy.nodes().removeClass("selected");
    cfgCy.elements().addClass("faded");
    cfgCy.edges().removeClass("faded");
    cfgCy.$id(bbId).removeClass("faded").addClass("selected");
  }

  if (moduleCy && moduleId) {
    moduleCy.elements().addClass("faded");
    moduleCy.nodes().removeClass("selected");
    moduleCy.$id(moduleId).removeClass("faded").addClass("selected");
  }

  highlightLines(collectBbLines(bbId));
  codeFocusLabelEl.textContent = t("common.highlightItem", { name: bbId });
  currentSelection = {
    type: "bb",
    moduleId,
    bbId,
    detailText: buildBbDetails(node, module),
    summaryText: `${bbId}: ${node.intent || TEXT.noIntentSummary}`
  };
  if (moduleId) renderEvidenceView(moduleId, bbId);
  updateSelectionToolbar();
}

function renderEvidenceView(moduleId, activeEvidenceBbId = null) {
  if (!evidenceChainViewEl || !evidenceSummaryEl) return;
  const module = (resultData.module_graph?.modules || []).find((item) => item.id === moduleId);
  const bundle = moduleEvidenceById.get(moduleId);
  if (!module || !bundle) {
    evidenceSummaryEl.textContent = t("evidence.noBundle");
    evidenceChainViewEl.innerHTML = `<div class="empty-card">${escapeHtml(t("evidence.noChain"))}</div>`;
    return;
  }

  const claim = bundle.claim || {};
  const evidenceItems = bundle.evidence || [];
  const reviewFlags = bundle.review_flags || [];
  evidenceSummaryEl.textContent = `${module.name} | ${t("evidence.blocks")}: ${evidenceItems.length} | ${t("evidence.reviewFlags")}: ${reviewFlags.length}`;

  evidenceChainViewEl.innerHTML = `
    <section class="evidence-claim-card">
      <div class="evidence-claim-head">
        <div>
          <p class="evidence-eyebrow">${escapeHtml(t("evidence.finalClaim"))}</p>
          <h3>${escapeHtml(claim.label || module.name)}</h3>
        </div>
        <div class="evidence-claim-metrics">
          <span class="evidence-pill">${escapeHtml(formatDescStatus(claim.desc_status))}</span>
          <span class="evidence-pill">${escapeHtml(t("evidence.confidence", { value: String(claim.confidence ?? t("common.na")) }))}</span>
          <span class="evidence-pill">${escapeHtml(t("evidence.risk", { value: formatRiskLevel(claim.risk) }))}</span>
        </div>
      </div>
      <p class="evidence-claim-desc">${escapeHtml(claim.desc || module.description || TEXT.noDescription)}</p>
    </section>
    <section class="evidence-flags-card">
      <div class="evidence-section-head">
        <h3>${escapeHtml(t("evidence.reviewFlags"))}</h3>
        <span class="muted">${escapeHtml(t("evidence.programmaticWarnings"))}</span>
      </div>
      <div class="evidence-flag-row">
        ${reviewFlags.length > 0 ? reviewFlags.map((flag) => buildReviewFlag(flag)).join("") : `<span class="empty-inline">${escapeHtml(t("evidence.noReviewFlags"))}</span>`}
      </div>
    </section>
    <section class="evidence-list-card">
      <div class="evidence-section-head">
        <h3>${escapeHtml(t("evidence.blocks"))}</h3>
        <span class="muted">${escapeHtml(t("evidence.clickBlock"))}</span>
      </div>
      <div class="evidence-list">
        ${evidenceItems.length > 0 ? evidenceItems.map((item) => buildEvidenceCard(item, activeEvidenceBbId)).join("") : `<div class="empty-card">${escapeHtml(t("evidence.noBlocks"))}</div>`}
      </div>
    </section>
  `;

  evidenceChainViewEl.querySelectorAll(".evidence-item").forEach((item) => {
    item.addEventListener("click", () => {
      focusBb(item.dataset.bbId);
      activateTab("evidence");
    });
  });
}

function buildReviewFlagLegacy(flag) {
  return `<span class="evidence-flag evidence-flag-${escapeHtml((flag.severity || "M").toLowerCase())}">${escapeHtml(flag.type)} · ${escapeHtml(flag.severity || "M")}</span>`;
}

function buildEvidenceCard(item, activeEvidenceBbId) {
  const isActive = item.bb_id === activeEvidenceBbId ? " evidence-item-active" : "";
  const span = Array.isArray(item.line_span) ? t("common.lines", { start: item.line_span[0], end: item.line_span[1] }) : t("common.linesNA");
  return `
    <article class="evidence-item${isActive}" data-bb-id="${item.bb_id}">
      <div class="evidence-item-head">
        <strong>${escapeHtml(item.bb_id)}</strong>
        <span>${escapeHtml(span)}</span>
      </div>
      <div class="evidence-signal-grid">
        <div class="evidence-signal-cell">
      <span class="evidence-signal-label">${escapeHtml(t("evidence.kind"))}</span>
          <code>${escapeHtml(item.signals?.kind || TEXT.none)}</code>
        </div>
        <div class="evidence-signal-cell">
      <span class="evidence-signal-label">${escapeHtml(t("evidence.calls"))}</span>
          <code>${escapeHtml((item.signals?.calls || []).join(", ") || TEXT.none)}</code>
        </div>
        <div class="evidence-signal-cell">
      <span class="evidence-signal-label">${escapeHtml(t("evidence.defs"))}</span>
          <code>${escapeHtml((item.signals?.defs || []).join(", ") || TEXT.none)}</code>
        </div>
        <div class="evidence-signal-cell">
      <span class="evidence-signal-label">${escapeHtml(t("evidence.uses"))}</span>
          <code>${escapeHtml((item.signals?.uses || []).join(", ") || TEXT.none)}</code>
        </div>
        <div class="evidence-signal-cell">
      <span class="evidence-signal-label">${escapeHtml(t("evidence.effects"))}</span>
          <code>${escapeHtml((item.signals?.effects || []).join(", ") || TEXT.none)}</code>
        </div>
      </div>
    </article>`;
}

function buildReviewFlag(flag) {
  return `<span class="evidence-flag evidence-flag-${escapeHtml((flag.severity || "M").toLowerCase())}">${escapeHtml(formatReviewFlagType(flag.type))} / ${escapeHtml(formatRiskLevel(flag.severity))}</span>`;
}

function renderSource() {
  if (!sourceLines.length) {
    sourceViewerEl.innerHTML = `<div class="empty-card">${escapeHtml(t("result.noSource"))}</div>`;
    return;
  }

  sourceViewerEl.innerHTML = sourceLines
    .map((line) => {
      const classes = ["source-line"];
      if (line.highlighted) classes.push("highlighted");
      return `
        <div class="${classes.join(" ")}">
          <span class="line-no">${line.lineNumber}</span>
          <pre>${escapeHtml(line.text)}</pre>
        </div>`;
    })
    .join("");
}

function highlightLines(lineSet, includeContextGap = false) {
  const targetSet = includeContextGap ? expandContextGapLines(lineSet) : lineSet;
  sourceLines = sourceLines.map((line) => ({
    ...line,
    highlighted: targetSet.has(line.lineNumber)
  }));
  renderSource();
}

function buildSourceLines(sourceCode) {
  return sourceCode.split("\n").map((text, index) => ({
    lineNumber: index + 1,
    text,
    highlighted: false
  }));
}

function buildModuleGraphLabel(module, index) {
  const summary = shorten(module.description || TEXT.noModuleSummary, 56);
  return `${index + 1}. ${module.name}\n${summary}`;
}

function buildBbGraphLabel(node) {
  return `${node.id}\n${shorten(node.intent || node.code || "", 64)}`;
}

function buildModuleDetails(module) {
  const evidenceBundle = moduleEvidenceById.get(module.id) || null;
  const claim = evidenceBundle ? evidenceBundle.claim || {} : {};
  const lines = [
    t("details.module", { name: module.name, id: module.id }),
    "",
    t("details.label", { value: claim.label || module.name || TEXT.none }),
    t("details.purpose", { value: claim.desc || module.description || TEXT.none })
  ];

  const metadata = stageDByModuleId.get(module.id);
  if (metadata) {
    lines.push("");
    lines.push(t("details.verificationMetadata"));
    lines.push(t("details.descStatus", { value: formatDescStatus(metadata.desc_status) }));
    lines.push(t("details.overlapRatio", { value: metadata.overlap_ratio ?? TEXT.none }));
    lines.push(t("details.evidenceBBIds", { value: (metadata.evidence_bb_ids || []).join(", ") || TEXT.none }));
    lines.push(t("details.sourceTempModuleId", { value: metadata.source_temp_module_id || t("common.na") }));
    lines.push(t("details.confidence", { value: metadata.confidence ?? TEXT.none }));
    lines.push(t("details.risk", { value: formatRiskLevel(metadata.risk) }));
    if (metadata.more_specific_desc) {
      lines.push("");
      lines.push(t("details.detailedFlow"));
      lines.push(metadata.more_specific_desc);
    }
  }

  if (evidenceBundle) {
    lines.push("");
    lines.push(t("details.evidence"));
    if ((evidenceBundle.evidence || []).length === 0) {
      lines.push(TEXT.none);
    } else {
      evidenceBundle.evidence.forEach((item) => {
        const span = Array.isArray(item.line_span) ? `${item.line_span[0]}-${item.line_span[1]}` : "N/A";
        lines.push(`- ${item.bb_id} @ ${t("common.lines", { start: item.line_span?.[0] || "?", end: item.line_span?.[1] || "?" })}`);
        lines.push(`  kind: ${item.signals?.kind || TEXT.none}`);
        lines.push(`  calls: ${(item.signals?.calls || []).join(", ") || TEXT.none}`);
        lines.push(`  defs: ${(item.signals?.defs || []).join(", ") || TEXT.none}`);
        lines.push(`  uses: ${(item.signals?.uses || []).join(", ") || TEXT.none}`);
        lines.push(`  effects: ${(item.signals?.effects || []).join(", ") || TEXT.none}`);
      });
    }

    lines.push("");
    lines.push(t("details.reviewFlags"));
    if ((evidenceBundle.review_flags || []).length === 0) {
      lines.push(TEXT.none);
    } else {
      evidenceBundle.review_flags.forEach((flag) => {
        lines.push(`- ${formatReviewFlagType(flag.type)} (${formatRiskLevel(flag.severity)})`);
      });
    }
  }
  return lines.join("\n");
}

function buildBbDetails(node, module) {
  return [
    t("details.basicBlock", { id: node.id }),
    t("details.module", { name: module ? module.name : t("result.unassigned"), id: module ? module.id : "" }),
    t("details.kind", { value: node.kind || "statement" }),
    t("details.intent", { value: node.intent || TEXT.none }),
    "",
    t("details.code"),
    node.code || "",
    "",
    t("details.defs", { value: (node.defs || []).join(", ") || TEXT.none }),
    t("details.uses", { value: (node.uses || []).join(", ") || TEXT.none }),
    t("details.calls", { value: (node.calls || []).join(", ") || TEXT.none }),
    t("details.effects", { value: (node.effects || []).join(", ") || TEXT.none })
  ].join("\n");
}

function collectModuleLines(moduleId) {
  const lineSet = new Set();
  (resultData.cfg?.bb_nodes || []).forEach((node) => {
    if (resultData.partition?.[node.id] === moduleId) {
      collectNodeLines(node).forEach((line) => lineSet.add(line));
    }
  });
  return expandModuleGapLines(lineSet, moduleId);
}

function collectBbLines(bbId) {
  const lineSet = new Set();
  const node = (resultData.cfg?.bb_nodes || []).find((item) => item.id === bbId);
  if (node) collectNodeLines(node).forEach((line) => lineSet.add(line));
  return lineSet;
}

function collectNodeLines(node) {
  const lineSet = new Set();
  addRange(lineSet, node.start_line, node.end_line);
  if (lineSet.size > 0) return lineSet;

  const matchedLine = findLineByCode(node.code);
  if (matchedLine !== null) lineSet.add(matchedLine);
  return lineSet;
}

function expandContextGapLines(lineSet) {
  if (!lineSet || lineSet.size < 2) return lineSet;
  const sorted = [...lineSet].sort((a, b) => a - b);
  const expanded = new Set(lineSet);

  for (let index = 0; index < sorted.length - 1; index += 1) {
    const current = sorted[index];
    const next = sorted[index + 1];
    if (next <= current + 1) continue;

    if (isContextOnlyRange(current + 1, next - 1)) {
      for (let line = current + 1; line < next; line += 1) expanded.add(line);
    }
  }
  return expanded;
}

function expandModuleGapLines(lineSet, moduleId) {
  if (!lineSet || lineSet.size < 2) return lineSet;
  const sorted = [...lineSet].sort((a, b) => a - b);
  const expanded = new Set(lineSet);
  const maxGapToFill = 8;

  for (let index = 0; index < sorted.length - 1; index += 1) {
    const current = sorted[index];
    const next = sorted[index + 1];
    const gapSize = next - current - 1;
    if (gapSize <= 0 || gapSize > maxGapToFill) continue;

    let canFillGap = true;
    for (let line = current + 1; line < next; line += 1) {
      const ownerModuleId = findLineOwnerModule(line);
      if (ownerModuleId && ownerModuleId !== moduleId) {
        canFillGap = false;
        break;
      }
    }
    if (!canFillGap) continue;

    for (let line = current + 1; line < next; line += 1) expanded.add(line);
  }
  return expanded;
}

function findLineOwnerModule(lineNumber) {
  for (const node of resultData.cfg?.bb_nodes || []) {
    if (nodeOwnsLine(node, lineNumber)) {
      return resultData.partition?.[node.id] || null;
    }
  }
  return null;
}

function nodeOwnsLine(node, lineNumber) {
  const startLine = Number(node.start_line);
  const endLine = Number(node.end_line);
  return Number.isFinite(startLine) && Number.isFinite(endLine) && lineNumber >= startLine && lineNumber <= endLine;
}

function isContextOnlyRange(startLine, endLine) {
  for (let line = startLine; line <= endLine; line += 1) {
    if (!isContextOnlyLine(line)) return false;
  }
  return true;
}

function isContextOnlyLine(lineNumber) {
  const line = sourceLines[lineNumber - 1];
  if (!line) return false;
  const text = (line.text || "").trim();
  return text === "" || text.startsWith("#");
}

function addRange(lineSet, startLine, endLine) {
  if (!startLine || !endLine) return;
  for (let line = startLine; line <= endLine; line += 1) lineSet.add(line);
}

function findLineByCode(code) {
  const normalizedCode = normalizeCode(code);
  if (!normalizedCode) return null;
  for (const line of sourceLines) {
    if (normalizeCode(line.text).includes(normalizedCode)) return line.lineNumber;
  }
  return null;
}

function normalizeCode(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

function updateSelectionToolbar() {
  selectionSummaryEl.textContent = currentSelection.summaryText;
  openSubcfgBtn.disabled = !currentSelection.moduleId;
  openEvidenceBtn.disabled = false;
  openDetailsBtn.disabled = !currentSelection.detailText;
}

function openSubCfgView() {
  if (!currentSelection.moduleId) return;
  renderCfgGraph(currentSelection.moduleId);
  activateTab("cfg-graph");
}

function openEvidenceView() {
  const moduleId = currentSelection.moduleId || getDefaultEvidenceModuleId();
  if (!moduleId) return;
  if (!currentSelection.moduleId || currentSelection.moduleId !== moduleId) {
    focusModule(moduleId);
  }
  renderEvidenceView(moduleId, currentSelection.bbId);
  activateTab("evidence");
}

function getDefaultEvidenceModuleId() {
  const firstEvidenceModule = (moduleEvidenceData?.module_evidence || [])[0];
  if (firstEvidenceModule?.module_id) return firstEvidenceModule.module_id;
  const firstModule = (resultData.module_graph?.modules || [])[0];
  return firstModule?.id || null;
}

function setupFloatingPanel(panel, storageKey, defaultState) {
  if (!panel) return;
  const handle = panel.querySelector("[data-drag-handle]");
  const restored = readLocalJson(storageKey);
  const state = { ...defaultState, ...(restored || {}) };
  applyFloatingPanelState(panel, state);

  panel.addEventListener("mousedown", () => bringFloatingPanelToFront(panel));
  if (!handle) return;

  handle.addEventListener("mousedown", (event) => {
    if (event.target.closest("button")) return;
    event.preventDefault();
    bringFloatingPanelToFront(panel);

    const rect = panel.getBoundingClientRect();
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;

    const onMove = (moveEvent) => {
      const nextLeft = clamp(moveEvent.clientX - offsetX, 12, window.innerWidth - 220);
      const nextTop = clamp(moveEvent.clientY - offsetY, 12, window.innerHeight - 120);
      panel.style.left = `${nextLeft}px`;
      panel.style.top = `${nextTop}px`;
      panel.style.right = "auto";
    };

    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      persistFloatingPanelState(panel, storageKey);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });

  if (typeof ResizeObserver === "function") {
    const observer = new ResizeObserver(() => persistFloatingPanelState(panel, storageKey));
    observer.observe(panel);
  }
}

function applyFloatingPanelState(panel, state) {
  if (!panel) return;
  if (typeof state.width === "number") panel.style.width = `${Math.max(300, state.width)}px`;
  if (typeof state.height === "number") panel.style.height = `${Math.max(240, state.height)}px`;
  if (typeof state.left === "number") {
    panel.style.left = `${Math.max(12, state.left)}px`;
    panel.style.right = "auto";
  } else if (typeof state.right === "number") {
    panel.style.right = `${Math.max(12, state.right)}px`;
  }
  if (typeof state.top === "number") panel.style.top = `${Math.max(12, state.top)}px`;
}

function persistFloatingPanelState(panel, storageKey) {
  if (!panel || !storageKey) return;
  const rect = panel.getBoundingClientRect();
  writeLocalJson(storageKey, {
    top: Math.round(rect.top),
    left: Math.round(rect.left),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
  });
}

function bringFloatingPanelToFront(panel) {
  if (!panel) return;
  floatingPanelZIndex += 1;
  panel.style.zIndex = String(floatingPanelZIndex);
}

function openFloatingPanel(panel) {
  if (!panel) return;
  panel.classList.remove("floating-panel-hidden");
  bringFloatingPanelToFront(panel);
}

function closeFloatingPanel(panel) {
  if (!panel) return;
  panel.classList.add("floating-panel-hidden");
}

function openMemoryBoard() {
  openFloatingPanel(memoryBoardPanelEl);
  if (memoryBoardInputEl) memoryBoardInputEl.focus();
}

function loadMemoryBoardContent() {
  if (!memoryBoardInputEl) return;
  memoryBoardInputEl.value = readLocalText(memoryBoardStorageKey);
}

function persistMemoryBoardContent() {
  if (!memoryBoardInputEl) return;
  writeLocalText(memoryBoardStorageKey, memoryBoardInputEl.value || "");
}

function exportMemoryBoardMarkdown() {
  const content = memoryBoardInputEl ? memoryBoardInputEl.value || "" : "";
  const timestamp = new Date().toISOString().replaceAll(":", "-").slice(0, 19);
  const functionSlug = slugify(resultData?.function_name || "function");
  const filename = `${functionSlug}-memory-board-${timestamp}.md`;
  downloadTextFile(filename, content || `# ${resultData?.function_name || t("memory.title")}\n`);
}

function openTaskModePanel() {
  openFloatingPanel(taskModePanelEl);
  if (!taskQuizState.questions.length || taskQuizState.error) {
    requestTaskQuiz(false);
  } else {
    renderTaskQuiz();
  }
}

function openVariableTracePanel() {
  openFloatingPanel(variableTracePanelEl);
  renderVariableTraceState();
  if (traceVariableInputEl) traceVariableInputEl.focus();
}

async function requestVariableTrace() {
  const variableQuery = (traceVariableInputEl?.value || "").trim();
  if (!variableQuery) {
    setTraceStatus(t("trace.enterVariable"), "error");
    return;
  }
  if (variableTraceState.loading) return;

  variableTraceState = {
    loading: true,
    explaining: false,
    trace: null,
    explanation: null,
    error: "",
  };
  renderVariableTraceState();
  setTraceStatus(t("trace.tracing", { name: variableQuery }), "loading");

  try {
    const response = await fetch("/api/variable-trace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildVariableTracePayload(variableQuery)),
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || t("trace.failed"));

    variableTraceState = {
      loading: false,
      explaining: false,
      trace: data,
      explanation: null,
      error: "",
    };
    renderVariableTraceState();
    setTraceStatus(t("trace.ready", { name: data.resolved_variable, count: data.timeline.length }), "ok");

    if (traceAutoExplainEl?.checked) {
      await requestVariableTraceExplanation(true);
    }
  } catch (error) {
    variableTraceState = {
      loading: false,
      explaining: false,
      trace: null,
      explanation: null,
      error: readError(error),
    };
    renderVariableTraceState();
    setTraceStatus(t("trace.failedDetail", { error: variableTraceState.error }), "error");
  }
}

async function requestVariableTraceExplanation(fromAutoExplain = false) {
  if (!variableTraceState.trace || variableTraceState.explaining) return;

  variableTraceState = {
    ...variableTraceState,
    explaining: true,
    explanation: null,
    error: "",
  };
  renderVariableTraceState();
  setTraceStatus(
    fromAutoExplain
      ? t("trace.generatingAuto", { name: variableTraceState.trace.resolved_variable })
      : t("trace.generating", { name: variableTraceState.trace.resolved_variable }),
    "loading"
  );

  try {
    const response = await fetch("/api/variable-trace-explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildVariableTraceExplainPayload()),
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || t("trace.explainRequestFailed"));

    variableTraceState = {
      ...variableTraceState,
      explaining: false,
      explanation: data,
      error: "",
    };
    renderVariableTraceState();
    const modeLabel = data.generation_mode === "fallback" ? t("trace.fallbackExplanation") : t("trace.explanationReady");
    setTraceStatus(t("trace.statusReady", { mode: modeLabel, name: data.resolved_variable }), "ok");
  } catch (error) {
    variableTraceState = {
      ...variableTraceState,
      explaining: false,
      error: readError(error),
    };
    renderVariableTraceState();
    setTraceStatus(t("trace.explainFailed", { error: variableTraceState.error }), "error");
  }
}

function buildVariableTracePayload(variableQuery) {
  return {
    function_name: resultData.function_name,
    variable_query: variableQuery,
    cfg: resultData.cfg || {},
    partition: resultData.partition || {},
    module_graph: resultData.module_graph || {},
    cfg_by_module: resultData.cfg_by_module || {},
    stage_outputs: resultData.stage_outputs || {},
    module_evidence: resultData.module_evidence || null,
    language: currentLanguage(),
  };
}

function buildVariableTraceExplainPayload() {
  return {
    function_name: resultData.function_name,
    variable_query: variableTraceState.trace?.query || (traceVariableInputEl?.value || "").trim(),
    trace: variableTraceState.trace,
    cfg: resultData.cfg || {},
    partition: resultData.partition || {},
    module_graph: resultData.module_graph || {},
    cfg_by_module: resultData.cfg_by_module || {},
    stage_outputs: resultData.stage_outputs || {},
    module_evidence: resultData.module_evidence || null,
    model: requestData?.model || "deepseek-chat",
    temperature: 0.0,
    llm: requestData?.llm || null,
    language: currentLanguage(),
  };
}

function renderVariableTraceState() {
  if (!traceSummaryEl || !traceTimelineEl || !traceExplanationEl || !traceRunBtn || !traceExplainBtn) return;

  const trace = variableTraceState.trace;
  const explanation = variableTraceState.explanation;

  traceRunBtn.disabled = variableTraceState.loading || variableTraceState.explaining;
  traceExplainBtn.disabled = variableTraceState.loading || variableTraceState.explaining || !trace;
  traceExplainBtn.textContent = variableTraceState.explaining ? t("trace.explaining") : t("trace.generateExplanation");

  traceSummaryEl.innerHTML = trace ? buildTraceSummaryHtml(trace) : `<div class="empty-card">${escapeHtml(t("trace.noTrace"))}</div>`;
  traceTimelineEl.innerHTML = trace ? buildTraceTimelineHtml(trace) : `<div class="empty-card">${escapeHtml(t("trace.timelineEmpty"))}</div>`;
  traceExplanationEl.innerHTML = explanation
    ? buildTraceExplanationHtml(explanation)
    : `<div class="empty-card">${escapeHtml(trace ? t("trace.readyGenerate") : t("trace.noExplanation"))}</div>`;

  bindTraceInteractions();
}

function bindTraceInteractions() {
  traceTimelineEl?.querySelectorAll("[data-trace-index]").forEach((element) => {
    element.addEventListener("click", () => {
      const index = Number(element.dataset.traceIndex);
      const item = variableTraceState.trace?.timeline?.[index];
      if (item) applyTraceSelection(item);
    });
  });
  traceSummaryEl?.querySelectorAll("[data-trace-module]").forEach((element) => {
    element.addEventListener("click", () => {
      const moduleId = element.dataset.traceModule;
      if (moduleId) {
        focusModule(moduleId);
        activateTab("module-graph");
      }
    });
  });
}

function buildTraceSummaryHtml(trace) {
  return `
    <div class="trace-summary-grid">
      <div class="trace-summary-item">
        <strong>${escapeHtml(t("trace.query"))}</strong>
        <span>${escapeHtml(trace.query || "")}</span>
      </div>
      <div class="trace-summary-item">
        <strong>${escapeHtml(t("trace.resolvedVariable"))}</strong>
        <span>${escapeHtml(trace.resolved_variable || "")}</span>
      </div>
      <div class="trace-summary-item">
        <strong>${escapeHtml(t("trace.roleHint"))}</strong>
        <span>${escapeHtml(trace.role_hint || TEXT.none)}</span>
      </div>
    </div>
    <div class="trace-summary-item">
      <strong>${escapeHtml(t("trace.matches"))}</strong>
      <div class="trace-inline-list">${buildTraceInlineItems(trace.matches || [])}</div>
    </div>
    <div class="trace-summary-item">
      <strong>${escapeHtml(t("trace.stats"))}</strong>
      <div class="trace-chip-row">
        ${buildTraceStatChip("def", trace.trace_stats?.def_count)}
        ${buildTraceStatChip("update", trace.trace_stats?.update_count)}
        ${buildTraceStatChip("use", trace.trace_stats?.use_count)}
        ${buildTraceStatChip("condition", trace.trace_stats?.condition_count)}
        ${buildTraceStatChip("output", trace.trace_stats?.output_count)}
      </div>
    </div>
    <div class="trace-summary-item">
      <strong>${escapeHtml(t("trace.relatedModules"))}</strong>
      <div class="trace-chip-row">${buildTraceModuleChips(trace.related_modules || [])}</div>
    </div>
    <div class="trace-summary-item">
      <strong>${escapeHtml(t("trace.anchors"))}</strong>
      <div class="trace-chip-row">
        <span class="trace-chip">${escapeHtml(t("trace.bbs", { count: (trace.bb_ids || []).length }))}</span>
        <span class="trace-chip">${escapeHtml(t("trace.lineSpans", { count: (trace.line_spans || []).length }))}</span>
      </div>
    </div>
  `;
}

function buildTraceInlineItems(items) {
  if (!items.length) return `<span class="muted">${escapeHtml(t("trace.noMatches"))}</span>`;
  return items.map((item) => `<span class="trace-chip">${escapeHtml(item)}</span>`).join("");
}

function buildTraceStatChip(label, value) {
  return `<span class="trace-chip">${escapeHtml(label)} ${escapeHtml(String(value ?? 0))}</span>`;
}

function buildTraceModuleChips(items) {
  if (!items.length) return `<span class="muted">${escapeHtml(t("trace.noRelatedModules"))}</span>`;
  return items
    .map((item) => `<button class="trace-chip trace-chip-button" type="button" data-trace-module="${escapeHtml(item)}">${escapeHtml(item)}</button>`)
    .join("");
}

function buildTraceTimelineHtml(trace) {
  if (!(trace.timeline || []).length) {
    return `<div class="empty-card">${escapeHtml(t("trace.noEvents"))}</div>`;
  }
  return (trace.timeline || [])
    .map((item, index) => {
      const moduleLabel = item.module_name ? `${item.module_id} / ${item.module_name}` : (item.module_id || t("trace.noModule"));
      return `
        <article class="trace-event-card" data-trace-index="${index}">
          <div class="trace-event-head">
            <div class="trace-event-title">
              <span class="trace-badge event-${escapeHtml(item.event_type)}">${escapeHtml(formatTraceEventType(item.event_type))}</span>
              <strong>${escapeHtml(item.bb_id || t("result.unknownBB"))}</strong>
            </div>
            <span class="muted">${escapeHtml(formatLineSpan(item.line_span))}</span>
          </div>
          <div class="trace-chip-row">
            <span class="trace-chip">${escapeHtml(moduleLabel)}</span>
          </div>
          <pre class="trace-code">${escapeHtml(item.code_snippet || "")}</pre>
          <div class="trace-reason">${escapeHtml(item.reason || "")}</div>
        </article>
      `;
    })
    .join("");
}

function buildTraceExplanationHtml(explanation) {
  const warningBlock = explanation.warning
    ? `<div class="trace-explain-block"><h4>${escapeHtml(t("trace.notice"))}</h4><div>${escapeHtml(explanation.warning)}</div></div>`
    : "";
  return `
    ${warningBlock}
    <div class="trace-explain-block">
      <h4>${escapeHtml(t("trace.role"))}</h4>
      <div>${escapeHtml(formatTraceRole(explanation.role))}</div>
    </div>
    <div class="trace-explain-block">
      <h4>${escapeHtml(t("trace.summary"))}</h4>
      <div>${escapeHtml(explanation.summary || "")}</div>
    </div>
    <div class="trace-explain-block">
      <h4>${escapeHtml(t("trace.keyTransitions"))}</h4>
      ${buildTraceList(explanation.key_transitions || [], t("trace.noKeyTransitions"))}
    </div>
    <div class="trace-explain-block">
      <h4>${escapeHtml(t("trace.impact"))}</h4>
      ${buildTraceList(explanation.impact || [], t("trace.noImpact"))}
    </div>
  `;
}

function buildTraceList(items, emptyText) {
  if (!items.length) return `<div class="muted">${escapeHtml(emptyText)}</div>`;
  return `<ul class="trace-bullet-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function applyTraceSelection(item) {
  if (!item) return;
  if (item.module_id) focusModule(item.module_id);
  if (item.bb_id) {
    focusBb(item.bb_id);
    activateTab("cfg-graph");
    return;
  }
  if (Array.isArray(item.line_span)) {
    focusLineSpan(item.line_span[0], item.line_span[1]);
  }
}

function formatLineSpan(lineSpan) {
  const startLine = Array.isArray(lineSpan) ? lineSpan[0] : null;
  const endLine = Array.isArray(lineSpan) ? lineSpan[1] : null;
  if (startLine && endLine) return t("common.lines", { start: startLine, end: endLine });
  return t("common.linesNA");
}

function setTraceStatus(message, state) {
  if (!traceStatusEl) return;
  traceStatusEl.textContent = message;
  traceStatusEl.className = state ? `task-status ${state}` : "task-status";
}

async function requestTaskQuiz(forceRefresh) {
  if (taskQuizState.loading) return;
  taskQuizState = {
    questions: [],
    answers: {},
    submitted: false,
    loading: true,
    generationMode: "llm",
    warning: "",
    error: "",
  };
  renderTaskQuiz();
  setTaskStatus(t("task.generating"), "loading");

  try {
    const response = await fetch("/api/generate_tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildGenerateTasksPayload()),
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || t("task.failed"));
    }

    taskQuizState = {
      questions: data.questions || [],
      answers: {},
      submitted: false,
      loading: false,
      generationMode: data.generation_mode || "llm",
      warning: data.warning || "",
      error: "",
    };
    const modeLabel = taskQuizState.generationMode === "fallback" ? t("task.fallbackGenerated") : t("task.questionsReady");
    setTaskStatus(forceRefresh ? t("task.refreshed", { mode: modeLabel }) : t("task.ready", { mode: modeLabel }), "ok");
    renderTaskQuiz();
  } catch (error) {
    taskQuizState = {
      questions: [],
      answers: {},
      submitted: false,
      loading: false,
      generationMode: "llm",
      warning: "",
      error: readError(error),
    };
    setTaskStatus(t("task.generationFailedDetail", { error: taskQuizState.error }), "error");
    renderTaskQuiz();
  }
}

function buildGenerateTasksPayload() {
  return {
    function_name: resultData.function_name,
    mode: resultData.mode || requestData.mode || "multi_stage",
    cfg: resultData.cfg || {},
    partition: resultData.partition || {},
    module_graph: resultData.module_graph || {},
    cfg_by_module: resultData.cfg_by_module || {},
    stage_outputs: resultData.stage_outputs || {},
    module_evidence: resultData.module_evidence || null,
    model: requestData?.model || "deepseek-chat",
    temperature: 0.0,
    question_count: 4,
    llm: requestData?.llm || null,
    language: currentLanguage(),
  };
}

function submitTaskAnswers() {
  if (taskQuizState.loading || taskQuizState.submitted) return;
  const required = taskQuizState.questions.length;
  const answered = Object.keys(taskQuizState.answers).length;
  if (!required || answered < required) {
    setTaskStatus(t("task.selectAll"), "error");
    return;
  }
  taskQuizState.submitted = true;
  setTaskStatus(t("task.answersSubmitted"), "ok");
  renderTaskQuiz();
}

function renderTaskQuiz() {
  if (!taskQuizContentEl || !taskSubmitBtn) return;
  if (taskQuizState.loading) {
    taskQuizContentEl.innerHTML = `<div class="empty-card">${escapeHtml(t("task.loadingEmpty"))}</div>`;
    taskSubmitBtn.disabled = true;
    taskSubmitBtn.textContent = t("task.submit");
    return;
  }
  if (taskQuizState.error) {
    taskQuizContentEl.innerHTML = `<div class="empty-card">${escapeHtml(t("task.failedRetry"))}</div>`;
    taskSubmitBtn.disabled = true;
    taskSubmitBtn.textContent = t("task.submit");
    return;
  }
  if (!taskQuizState.questions.length) {
    taskQuizContentEl.innerHTML = `<div class="empty-card">${escapeHtml(t("task.initialEmpty"))}</div>`;
    taskSubmitBtn.disabled = true;
    taskSubmitBtn.textContent = t("task.submit");
    return;
  }

  const warningNote = taskQuizState.warning
    ? `<div class="quiz-warning-note">${escapeHtml(taskQuizState.warning)}</div>`
    : "";
  taskQuizContentEl.innerHTML = `
    ${warningNote}
    ${taskQuizState.questions.map((question, index) => buildTaskQuestionCard(question, index)).join("")}
  `;

  taskQuizContentEl.querySelectorAll('input[name^="task-question-"]').forEach((input) => {
    input.addEventListener("change", () => {
      taskQuizState.answers[input.dataset.questionId] = input.value;
      updateTaskSubmitState();
    });
  });
  taskQuizContentEl.querySelectorAll(".quiz-evidence-chip[data-module-id]").forEach((button) => {
    button.addEventListener("click", () => {
      focusModule(button.dataset.moduleId);
      activateTab("modules");
    });
  });
  taskQuizContentEl.querySelectorAll(".quiz-evidence-chip[data-bb-id]").forEach((button) => {
    button.addEventListener("click", () => {
      focusBb(button.dataset.bbId);
      activateTab("cfg-graph");
    });
  });
  taskQuizContentEl.querySelectorAll(".quiz-evidence-chip[data-line-span]").forEach((button) => {
    button.addEventListener("click", () => {
      const [startLine, endLine] = String(button.dataset.lineSpan || "")
        .split(":")
        .map((item) => Number(item));
      focusLineSpan(startLine, endLine);
    });
  });

  updateTaskSubmitState();
}

function buildTaskQuestionCard(question, index) {
  const selected = taskQuizState.answers[question.id] || "";
  const submitted = taskQuizState.submitted;
  const feedback = submitted ? buildTaskFeedback(question) : "";
  return `
    <article class="quiz-question-card">
      <div class="quiz-question-head">
        <h3>Q${index + 1}. ${escapeHtml(question.question)}</h3>
        <span class="quiz-badge">${escapeHtml(formatTaskQuestionType(question.type))}</span>
      </div>
      <div class="quiz-options">
        ${(question.options || []).map((option) => buildTaskOption(question, option, selected, submitted)).join("")}
      </div>
      ${feedback}
    </article>
  `;
}

function buildTaskOption(question, option, selected, submitted) {
  const isSelected = selected === option.id;
  const isCorrect = submitted && question.answer === option.id;
  const isIncorrect = submitted && isSelected && question.answer !== option.id;
  const classes = ["quiz-option"];
  if (isCorrect) classes.push("correct");
  if (isIncorrect) classes.push("incorrect");
  return `
    <label class="${classes.join(" ")}">
      <input
        type="radio"
        name="task-question-${escapeHtml(question.id)}"
        value="${escapeHtml(option.id)}"
        data-question-id="${escapeHtml(question.id)}"
        ${isSelected ? "checked" : ""}
        ${submitted ? "disabled" : ""}
      >
      <span class="quiz-option-label">
        <span class="quiz-option-id">${escapeHtml(option.id)}</span>
        <span>${escapeHtml(option.text)}</span>
      </span>
    </label>
  `;
}

function buildTaskFeedback(question) {
  const evidence = question.evidence || {};
  const moduleChips = (evidence.modules || [])
    .map((moduleId) => `<button class="quiz-evidence-chip" type="button" data-module-id="${escapeHtml(moduleId)}">${escapeHtml(moduleId)}</button>`)
    .join("");
  const bbChips = (evidence.bb_ids || [])
    .map((bbId) => `<button class="quiz-evidence-chip" type="button" data-bb-id="${escapeHtml(bbId)}">${escapeHtml(bbId)}</button>`)
    .join("");
  const lineChips = (evidence.line_spans || [])
    .map((span) => {
      const startLine = Array.isArray(span) ? span[0] : null;
      const endLine = Array.isArray(span) ? span[1] : null;
      if (!startLine || !endLine) return "";
      return `<button class="quiz-evidence-chip" type="button" data-line-span="${startLine}:${endLine}">${escapeHtml(t("common.lines", { start: startLine, end: endLine }))}</button>`;
    })
    .join("");
  return `
    <div class="quiz-feedback">
      <strong>${escapeHtml(t("task.answer", { answer: question.answer }))}</strong>
      <div>${escapeHtml(question.explanation)}</div>
      <div class="quiz-evidence">
        <span class="muted">${escapeHtml(t("task.evidenceAnchors"))}</span>
        <div class="quiz-chip-row">${moduleChips || `<button class="quiz-evidence-chip" type="button" disabled>${escapeHtml(t("task.noModules"))}</button>`}</div>
        <div class="quiz-chip-row">${bbChips || `<button class="quiz-evidence-chip" type="button" disabled>${escapeHtml(t("task.noBBIds"))}</button>`}</div>
        <div class="quiz-chip-row">${lineChips || `<button class="quiz-evidence-chip" type="button" disabled>${escapeHtml(t("task.noLineSpans"))}</button>`}</div>
      </div>
    </div>
  `;
}

function updateTaskSubmitState() {
  if (!taskSubmitBtn) return;
  const required = taskQuizState.questions.length;
  const answered = Object.keys(taskQuizState.answers).length;
  taskSubmitBtn.textContent = taskQuizState.submitted ? t("task.submitted") : t("task.submit");
  taskSubmitBtn.disabled = taskQuizState.loading || taskQuizState.submitted || required === 0 || answered < required;
}

function setTaskStatus(message, state) {
  if (!taskStatusEl) return;
  taskStatusEl.textContent = message;
  taskStatusEl.className = state ? `task-status ${state}` : "task-status";
}

function focusLineSpan(startLine, endLine) {
  const lineSet = new Set();
  addRange(lineSet, startLine, endLine);
  highlightLines(lineSet, false);
  codeFocusLabelEl.textContent = t("common.highlightLines", { start: startLine, end: endLine });
}

function writeLocalText(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    console.warn("localStorage write failed", error);
  }
}

function readLocalText(key) {
  try {
    return localStorage.getItem(key) || "";
  } catch (error) {
    console.warn("localStorage read failed", error);
    return "";
  }
}

function writeLocalJson(key, value) {
  writeLocalText(key, JSON.stringify(value));
}

function readLocalJson(key) {
  const raw = readLocalText(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function slugify(text) {
  return String(text || "notes")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "notes";
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function openSelectionDetails() {
  if (!currentSelection.detailText) return;
  detailsBoxEl.textContent = currentSelection.detailText;
  activateTab("modules");
}

function activateTab(view) {
  const button = document.querySelector(`.tab-btn[data-view="${view}"]`);
  if (button) button.click();
}

function renderMissingDataState() {
  showGlobalMessage(TEXT.missingData, "error");
  titleEl.textContent = t("result.missingTitle");
  subtitleEl.textContent = t("result.missingSubtitle");
  metricBlocksEl.textContent = "0";
  metricModulesEl.textContent = "0";
  metricModeEl.textContent = t("common.na");
  warningsEl.textContent = t("result.noData");

  sourceViewerEl.innerHTML = `<div class="empty-card">${TEXT.missingData}</div>`;
  document.querySelectorAll(".tab-btn").forEach((button) => (button.disabled = true));
  if (variableTraceBtn) variableTraceBtn.disabled = true;
  if (memoryBoardBtn) memoryBoardBtn.disabled = true;
  if (taskModeBtn) taskModeBtn.disabled = true;
  openSubcfgBtn.disabled = true;
  openEvidenceBtn.disabled = true;
  openDetailsBtn.disabled = true;
  resetCfgBtn.disabled = true;
  modulesListEl.innerHTML = `<div class="empty-card">${escapeHtml(t("result.noModulesDisplay"))}</div>`;
}

function showGlobalMessage(message, state) {
  if (!globalMessageEl) return;
  globalMessageEl.textContent = message;
  globalMessageEl.className = `state-banner ${state}`;
}

function readResultData() {
  return readLanguageScopedSession("llm_partition_result", resultStorageKey(currentLanguage()));
}

function readRequestData() {
  return readLanguageScopedSession("llm_partition_request", requestStorageKey(currentLanguage()), true);
}

function readLanguageScopedSession(legacyKey, scopedKey, allowLanguageMismatch = false) {
  const rawScoped = sessionStorage.getItem(scopedKey);
  if (rawScoped) return JSON.parse(rawScoped);

  const rawLegacy = sessionStorage.getItem(legacyKey);
  if (!rawLegacy) return null;
  const parsed = JSON.parse(rawLegacy);
  const payloadLanguage = parsed?.language;
  if (allowLanguageMismatch || !payloadLanguage || payloadLanguage === currentLanguage()) {
    return parsed;
  }
  return null;
}

function formatMode(mode) {
  if (mode === "one_shot") return t("result.mode.oneShot");
  if (mode === "multi_stage") return t("result.mode.multiStage");
  return t("common.unknown");
}

function formatDescStatus(status) {
  if (!status) return t("common.unknown");
  if (!["inherited", "weakly_inherited", "invalidated"].includes(status)) return status;
  return t(`evidence.descStatus.${status}`);
}

function formatReviewFlagType(type) {
  if (!type) return t("common.unknown");
  if (!["weak_desc_inheritance", "high_uncertainty_evidence", "module_repair_heavy"].includes(type)) return type;
  return t(`evidence.flag.${type}`);
}

function formatRiskLevel(level) {
  if (!level) return t("common.na");
  if (!["L", "M", "H"].includes(level)) return level;
  return t(`evidence.level.${level}`);
}

function formatTraceEventType(type) {
  if (!type) return t("common.unknown");
  if (!["def", "update", "use", "condition", "output"].includes(type)) return type;
  return t(`trace.event.${type}`);
}

function formatTraceRole(role) {
  if (!role) return t("common.unknown");
  if (["output_state", "control_flag", "state_accumulator", "input_dependency", "working_state"].includes(role)) {
    return t(`trace.roleValue.${role}`);
  }
  return role;
}

function formatTaskQuestionType(type) {
  if (type === "single_choice") return t("task.type.single_choice");
  return type || t("common.unknown");
}

function resultStorageKey(language) {
  return `llm_partition_result::${language || "en"}`;
}

function requestStorageKey(language) {
  return `llm_partition_request::${language || "en"}`;
}

function writeSessionJson(key, value) {
  sessionStorage.setItem(key, JSON.stringify(value));
}

function truncateText(text, limit) {
  if (!text) return "";
  return text.length <= limit ? text : `${text.slice(0, limit)}\n...`;
}

function shorten(text, limit) {
  if (!text) return "";
  return text.length <= limit ? text : `${text.slice(0, limit - 3)}...`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function readError(error) {
  return error && error.message ? error.message : String(error);
}
