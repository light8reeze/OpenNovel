const logEl = document.getElementById("log");
const choicesEl = document.getElementById("choices");
const stateEl = document.getElementById("state");
const formEl = document.getElementById("input-form");
const inputEl = document.getElementById("input");
const storyTitleEl = document.getElementById("story-title");
const storyOriginEl = document.getElementById("story-origin");
const startButton = document.getElementById("start-button");
const suggestButton = document.getElementById("suggest-button");
const loadingOverlayEl = document.getElementById("loading-overlay");
const loadingMessageEl = document.getElementById("loading-message");
const graphEl = document.getElementById("graph");
const graphHoverEl = document.getElementById("graph-hover");
const turnDetailEl = document.getElementById("turn-detail");
const graphModeEl = document.getElementById("graph-mode");
const tabGameEl = document.getElementById("tab-game");
const tabDebugEl = document.getElementById("tab-debug");
const panelGameEl = document.getElementById("panel-game");
const panelDebugEl = document.getElementById("panel-debug");
const debugStatusEl = document.getElementById("debug-status");
const debugSessionsEl = document.getElementById("debug-sessions");
const debugTurnsEl = document.getElementById("debug-turns");
const debugTraceEl = document.getElementById("debug-trace");

const SESSION_KEY = "open-novel-session";
const LEGACY_SESSION_KEY = "novel-gg-session";
const SVG_NS = "http://www.w3.org/2000/svg";

let sessionId =
  localStorage.getItem(SESSION_KEY) || localStorage.getItem(LEGACY_SESSION_KEY);
let debugUiEnabled = false;
let turnHistory = [];
let selectedTurnId = null;
let storySetups = [];
let selectedStorySetupId = null;
let activeSideTab = "game";
let debugSessions = [];
let debugTurns = [];
let selectedDebugSessionId = null;
let selectedDebugTurn = null;
let pendingRequests = 0;

const debugCache = new Map();

suggestButton.disabled = !sessionId;

function renderStorySetupSelector() {
  if (!storySetups.length) {
    selectedStorySetupId = null;
    storyTitleEl.textContent = "시나리오를 불러오는 중...";
    storyOriginEl.textContent = "에이전트가 생성한 스토리를 준비하고 있습니다.";
    return;
  }
  selectedStorySetupId = storySetups[0].id;
  updateStoryTitle(selectedStorySetupId);
}

function updateStoryTitle(storySetupId) {
  const preset = storySetups.find((item) => item.id === storySetupId);
  storyTitleEl.textContent = preset ? preset.title : "OpenNovel Scenario";
  storyOriginEl.textContent = preset
    ? "에이전트가 생성한 이번 스토리입니다. 새 세션 시작을 누르면 바로 진행합니다."
    : "에이전트가 생성한 스토리로 시작합니다.";
}

function appendMessage(role, content) {
  const item = document.createElement("article");
  item.className = `message ${role}`;
  item.textContent = content;
  logEl.appendChild(item);
  logEl.scrollTop = logEl.scrollHeight;
}

function renderChoices(choices) {
  choicesEl.innerHTML = "";
  choices.forEach((choice) => {
    const button = document.createElement("button");
    button.className = "choice";
    button.type = "button";
    button.textContent = choice;
    button.addEventListener("click", () => sendAction({ choiceText: choice }));
    choicesEl.appendChild(button);
  });
}

function setLoading(isLoading, message = "응답을 기다리는 중...") {
  pendingRequests = isLoading ? pendingRequests + 1 : Math.max(0, pendingRequests - 1);
  const active = pendingRequests > 0;
  loadingOverlayEl.classList.toggle("hidden", !active);
  if (active) {
    loadingMessageEl.textContent = message;
  }
  startButton.disabled = active;
  suggestButton.disabled = active || !sessionId;
  inputEl.disabled = active;
  formEl.querySelector('button[type="submit"]').disabled = active;
  choicesEl.querySelectorAll("button").forEach((button) => {
    button.disabled = active;
  });
}

function renderState(state) {
  const themeId = state.world?.theme_id || "-";
  const objectiveStatus = state.objective?.status || "-";
  const victoryPath = state.objective?.victory_path || "-";
  const styleTags = (state.player?.style_tags || []).join(", ") || "-";
  stateEl.innerHTML = `
    <dl>
      <dt>Turn</dt><dd>${state.meta.turn}</dd>
      <dt>HP</dt><dd>${state.player.hp}</dd>
      <dt>Gold</dt><dd>${state.player.gold}</dd>
      <dt>Location</dt><dd>${state.player.location_id}</dd>
      <dt>Story Arc Stage</dt><dd>${state.quests.story_arc.stage}</dd>
      <dt>Theme</dt><dd>${themeId}</dd>
      <dt>Objective</dt><dd>${objectiveStatus}</dd>
      <dt>Victory Path</dt><dd>${victoryPath}</dd>
      <dt>Style Tags</dt><dd>${styleTags}</dd>
    </dl>
  `;
}

function renderEmptyState(message = "에이전트가 준비한 스토리를 시작하려면 새 세션 시작을 누르세요.") {
  stateEl.innerHTML = `<p class="panel-meta">${escapeHtml(message)}</p>`;
}

async function fetchHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      return;
    }
    const data = await response.json();
    debugUiEnabled = Boolean(data.debugUiEnabled);
    graphModeEl.textContent = debugUiEnabled ? "Debug logs on" : "Debug logs off";
    debugStatusEl.textContent = debugUiEnabled ? "Debug logs on" : "Debug logs off";
    if (!debugUiEnabled) {
      tabDebugEl.disabled = true;
    }
  } catch (_error) {
    graphModeEl.textContent = "Debug logs unavailable";
    debugStatusEl.textContent = "Debug logs unavailable";
    tabDebugEl.disabled = true;
  }
}

function resetTurnHistory() {
  turnHistory = [];
  selectedTurnId = null;
  debugCache.clear();
  hideGraphHover();
  renderGraph();
  renderTurnDetail(null);
}

function appendTurnNode(node) {
  turnHistory.push(node);
  selectedTurnId = node.id;
  renderGraph();
  renderTurnDetail(node);
  if (debugUiEnabled && selectedDebugSessionId === sessionId) {
    fetchDebugTurns(sessionId, { preserveSelection: false });
  }
  loadDebugBundle(node).then((data) => {
    if (node.id === selectedTurnId && data) {
      renderTurnDetail(node, data);
    }
  });
}

function createStartNode(data) {
  return {
    id: `turn-${data.state.meta.turn}`,
    turn: data.state.meta.turn,
    playerInput: "새 세션 시작",
    messageCode: "GAME_STARTED",
    narrative: data.narrative,
    locationId: data.state.player.location_id,
    questStage: data.state.quests.story_arc.stage,
    hp: data.state.player.hp,
    gold: data.state.player.gold,
    storySetupId: data.storySetupId || selectedStorySetupId,
  };
}

function createActionNode(payload, data) {
  const turn = data.state.meta.turn;
  return {
    id: `turn-${turn}`,
    turn,
    playerInput: payload.inputText || payload.choiceText || "",
    messageCode: data.engineResult.message_code,
    narrative: data.narrative,
    locationId: data.state.player.location_id,
    questStage: data.state.quests.story_arc.stage,
    hp: data.state.player.hp,
    gold: data.state.player.gold,
    storySetupId: data.storySetupId || selectedStorySetupId,
  };
}

function renderGraph() {
  graphEl.innerHTML = "";
  if (!turnHistory.length) {
    graphEl.innerHTML = `<p class="graph-empty">세션이 시작되면 턴 흐름도가 여기에 표시됩니다.</p>`;
    return;
  }

  const width = Math.max(360, turnHistory.length * 136);
  const height = 220;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "graph-svg");

  turnHistory.forEach((node, index) => {
    const x = 72 + index * 124;
    const y = 92;

    if (index < turnHistory.length - 1) {
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", String(x + 24));
      line.setAttribute("y1", String(y));
      line.setAttribute("x2", String(x + 100));
      line.setAttribute("y2", String(y));
      line.setAttribute("class", "graph-link");
      svg.appendChild(line);
    }

    const group = document.createElementNS(SVG_NS, "g");
    group.setAttribute("class", `graph-node ${node.id === selectedTurnId ? "is-selected" : ""}`);
    group.setAttribute("transform", `translate(${x}, ${y})`);
    group.addEventListener("click", () => {
      selectedTurnId = node.id;
      renderGraph();
      renderTurnDetail(node);
      loadDebugBundle(node).then((data) => {
        if (node.id === selectedTurnId && data) {
          renderTurnDetail(node, data);
        }
      });
    });
    group.addEventListener("mouseenter", (event) => showHoverDebug(node, event));
    group.addEventListener("mouseleave", hideGraphHover);

    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("r", "24");
    circle.setAttribute("class", `graph-circle ${messageTone(node.messageCode)}`);
    group.appendChild(circle);

    const turnText = document.createElementNS(SVG_NS, "text");
    turnText.setAttribute("class", "graph-turn");
    turnText.setAttribute("text-anchor", "middle");
    turnText.setAttribute("y", "5");
    turnText.textContent = `T${node.turn}`;
    group.appendChild(turnText);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("class", "graph-label");
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("y", "48");
    label.textContent = shortenLabel(node.messageCode);
    group.appendChild(label);

    const sublabel = document.createElementNS(SVG_NS, "text");
    sublabel.setAttribute("class", "graph-sublabel");
    sublabel.setAttribute("text-anchor", "middle");
    sublabel.setAttribute("y", "66");
    sublabel.textContent = shortLocation(node.locationId);
    group.appendChild(sublabel);

    svg.appendChild(group);
  });

  graphEl.appendChild(svg);
}

function renderTurnDetail(node, debugData = null) {
  if (!node) {
    turnDetailEl.className = "turn-detail empty";
    turnDetailEl.textContent = "노드를 클릭하면 해당 턴의 입력, 결과, 서술이 표시됩니다.";
    return;
  }

  const normalizedAction =
    debugData?.intentResponse?.action?.action_type ||
    debugData?.intentResponse?.action?.actionType ||
    "unknown";
  const validationFlags = debugData?.intentResponse?.validation_flags || [];
  const safetyFlags = debugData?.narrativeResponse?.safety_flags || [];
  const validatorFlags = debugData?.validationResponse?.validation_flags || [];
  const progressKind = debugData?.validationResponse?.progress_kind || "n/a";
  const worldTitle = debugData?.worldBuildResponse?.blueprint?.title || "n/a";

  turnDetailEl.className = "turn-detail";
  turnDetailEl.innerHTML = `
    <div class="detail-grid">
      <div>
        <p class="detail-label">Turn</p>
        <p class="detail-value">T${node.turn}</p>
      </div>
      <div>
        <p class="detail-label">Action</p>
        <p class="detail-value">${normalizedAction}</p>
      </div>
      <div>
        <p class="detail-label">Message</p>
        <p class="detail-value">${node.messageCode}</p>
      </div>
      <div>
        <p class="detail-label">Location</p>
        <p class="detail-value">${node.locationId}</p>
      </div>
      <div>
        <p class="detail-label">Progress</p>
        <p class="detail-value">${progressKind}</p>
      </div>
    </div>
    <div class="detail-block">
      <p class="detail-label">Input</p>
      <p class="detail-copy">${escapeHtml(node.playerInput || "시작 노드")}</p>
    </div>
    <div class="detail-block">
      <p class="detail-label">Narrative</p>
      <p class="detail-copy">${escapeHtml(node.narrative)}</p>
    </div>
    <div class="detail-grid">
      <div>
        <p class="detail-label">HP</p>
        <p class="detail-value">${node.hp}</p>
      </div>
      <div>
        <p class="detail-label">Gold</p>
        <p class="detail-value">${node.gold}</p>
      </div>
      <div>
        <p class="detail-label">Quest Stage</p>
        <p class="detail-value">${node.questStage}</p>
      </div>
    </div>
    ${
      debugData
        ? `
      <div class="detail-block">
        <p class="detail-label">Debug</p>
        <p class="detail-copy">${
          debugSummary(debugData) +
          ` / world=${worldTitle}` +
          (validationFlags.length ? ` / intent=${validationFlags.join(", ")}` : "") +
          (validatorFlags.length ? ` / validator=${validatorFlags.join(", ")}` : "") +
          (safetyFlags.length ? ` / narrative=${safetyFlags.join(", ")}` : "")
        }</p>
      </div>
    `
        : ""
    }
  `;
}

function messageTone(messageCode) {
  if (messageCode === "GAME_STARTED") {
    return "tone-opening";
  }
  if (messageCode === "MOVE_OK") {
    return "tone-move";
  }
  if (messageCode === "TORCH_LIT") {
    return "tone-item";
  }
  return "tone-neutral";
}

function shortenLabel(messageCode) {
  return messageCode
    .replaceAll("_", " ")
    .split(" ")
    .slice(0, 2)
    .join(" ");
}

function shortLocation(locationId) {
  return locationId.replace("collapsed_", "").replace("buried_", "").replaceAll("_", " ");
}

async function showHoverDebug(node, event) {
  if (!debugUiEnabled || !sessionId) {
    return;
  }
  graphHoverEl.classList.remove("hidden");
  graphHoverEl.innerHTML = `<p class="hover-title">T${node.turn} Debug</p><p class="hover-copy">로그를 불러오는 중...</p>`;
  positionHoverPanel(event);
  const data = await loadDebugBundle(node);

  graphHoverEl.classList.remove("hidden");
  graphHoverEl.innerHTML = renderHoverMarkup(node, data);
  positionHoverPanel(event);
  if (node.id === selectedTurnId) {
    renderTurnDetail(node, data);
  }
}

async function fetchTurnDebugBundle(targetSessionId, turn) {
  if (!debugUiEnabled || !targetSessionId) {
    return null;
  }

  const key = `${targetSessionId}:${turn}`;
  if (debugCache.has(key)) {
    return debugCache.get(key);
  }

  try {
    const response = await fetch(
      `/debug/turn-log?sessionId=${encodeURIComponent(targetSessionId)}&turn=${encodeURIComponent(turn)}`,
    );
    if (!response.ok) {
      throw new Error(`debug log request failed: ${response.status}`);
    }
    const data = await response.json();
    debugCache.set(key, data);
    return data;
  } catch (_error) {
    const data = { found: false };
    debugCache.set(key, data);
    return data;
  }
}

async function loadDebugBundle(node) {
  if (!debugUiEnabled || !sessionId) {
    return null;
  }
  return fetchTurnDebugBundle(sessionId, node.turn);
}

function positionHoverPanel(event) {
  const frame = graphEl.parentElement.getBoundingClientRect();
  const left = Math.min(event.clientX - frame.left + 16, frame.width - 280);
  const top = Math.max(12, event.clientY - frame.top - 12);
  graphHoverEl.style.left = `${left}px`;
  graphHoverEl.style.top = `${top}px`;
}

function hideGraphHover() {
  graphHoverEl.classList.add("hidden");
}

function renderHoverMarkup(node, data) {
  if (!data?.found) {
    return `
      <p class="hover-title">T${node.turn} Debug</p>
      <p class="hover-copy">연결된 디버그 로그를 찾지 못했습니다.</p>
    `;
  }

  const actionType =
    data.intentResponse?.action?.action_type ||
    data.intentResponse?.action?.actionType ||
    "unknown";
  const provider = data.provider || "n/a";
  const model = data.model || "n/a";
  const fallback = data.usedFallback === true ? "yes" : "no";
  const intentFlags = (data.errorSummary?.intentValidationFlags || []).join(", ") || "none";
  const safetyFlags = (data.errorSummary?.narrativeSafetyFlags || []).join(", ") || "none";
  const turnTokens = formatTokenUsage(data.turnTokenUsage);
  const sessionTokens = formatTokenUsage(data.sessionTokenUsage?.combined);
  const worldTokens = formatTokenUsage(data.worldBuildResponse?.token_usage || data.sessionTokenUsage?.worldBuild);
  const intentTokens = formatTokenUsage(data.intentResponse?.token_usage);
  const proposalTokens = formatTokenUsage(data.stateProposalResponse?.token_usage || data.sessionTokenUsage?.stateProposal);
  const narrativeTokens = formatTokenUsage(data.narrativeResponse?.token_usage);
  const validatorFlags = (data.validationResponse?.validation_flags || []).join(", ") || "none";
  const progressKind = data.validationResponse?.progress_kind || "n/a";
  const worldTitle = data.worldBuildResponse?.blueprint?.title || "n/a";

  return `
    <p class="hover-title">T${node.turn} Debug</p>
    <dl class="hover-grid">
      <dt>Input</dt><dd>${escapeHtml(node.playerInput || "새 세션 시작")}</dd>
      <dt>World</dt><dd>${escapeHtml(worldTitle)}</dd>
      <dt>Action</dt><dd>${escapeHtml(actionType)}</dd>
      <dt>Provider</dt><dd>${escapeHtml(provider)}</dd>
      <dt>Model</dt><dd>${escapeHtml(model)}</dd>
      <dt>Fallback</dt><dd>${fallback}</dd>
      <dt>Progress</dt><dd>${escapeHtml(progressKind)}</dd>
      <dt>Turn Tokens</dt><dd>${escapeHtml(turnTokens)}</dd>
      <dt>Session Tokens</dt><dd>${escapeHtml(sessionTokens)}</dd>
      <dt>Intent Flags</dt><dd>${escapeHtml(intentFlags)}</dd>
      <dt>Validator Flags</dt><dd>${escapeHtml(validatorFlags)}</dd>
      <dt>Safety Flags</dt><dd>${escapeHtml(safetyFlags)}</dd>
    </dl>
    <div class="hover-block">
      <p class="hover-label">World Build</p>
      <p class="hover-copy">tokens: ${escapeHtml(worldTokens)}</p>
      <pre>${escapeHtml(
        JSON.stringify({ request: data.worldBuildRequest, response: data.worldBuildResponse }, null, 2),
      )}</pre>
    </div>
    <div class="hover-block">
      <p class="hover-label">Game Request</p>
      <pre>${escapeHtml(JSON.stringify(data.gameRequest, null, 2))}</pre>
    </div>
    <div class="hover-block">
      <p class="hover-label">Game Response</p>
      <pre>${escapeHtml(JSON.stringify(data.gameResponse, null, 2))}</pre>
    </div>
    <div class="hover-block">
      <p class="hover-label">Intent</p>
      <p class="hover-copy">tokens: ${escapeHtml(intentTokens)}</p>
      <pre>${escapeHtml(JSON.stringify({ request: data.intentRequest, response: data.intentResponse }, null, 2))}</pre>
    </div>
    <div class="hover-block">
      <p class="hover-label">State Proposal</p>
      <p class="hover-copy">tokens: ${escapeHtml(proposalTokens)}</p>
      <pre>${escapeHtml(
        JSON.stringify({ request: data.stateProposalRequest, response: data.stateProposalResponse }, null, 2),
      )}</pre>
    </div>
    <div class="hover-block">
      <p class="hover-label">Validation</p>
      <pre>${escapeHtml(
        JSON.stringify({ request: data.validationRequest, response: data.validationResponse }, null, 2),
      )}</pre>
    </div>
    <div class="hover-block">
      <p class="hover-label">Narrative</p>
      <p class="hover-copy">tokens: ${escapeHtml(narrativeTokens)}</p>
      <pre>${escapeHtml(
        JSON.stringify({ request: data.narrativeRequest, response: data.narrativeResponse }, null, 2),
      )}</pre>
    </div>
  `;
}

function debugSummary(data) {
  const provider = data.provider || "n/a";
  const model = data.model || "n/a";
  const fallback = data.usedFallback === true ? "fallback" : "live";
  const turnTokens = formatTokenUsage(data.turnTokenUsage);
  return `${provider} / ${model} / ${fallback} / tokens=${turnTokens}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatTokenUsage(usage) {
  if (!usage) {
    return "n/a";
  }
  const input = Number(usage.input_tokens || 0);
  const output = Number(usage.output_tokens || 0);
  const total = Number(usage.total_tokens || 0);
  const prefix = usage.estimated ? "~" : "";
  return `${prefix}${input}/${output}/${total}`;
}

function setSideTab(mode) {
  activeSideTab = mode;
  tabGameEl.classList.toggle("is-active", mode === "game");
  tabDebugEl.classList.toggle("is-active", mode === "debug");
  panelGameEl.classList.toggle("is-active", mode === "game");
  panelDebugEl.classList.toggle("is-active", mode === "debug");
  if (mode === "debug" && debugUiEnabled) {
    fetchDebugSessions();
  }
}

async function fetchDebugSessions() {
  if (!debugUiEnabled) {
    return;
  }
  try {
    const response = await fetch("/debug/sessions");
    if (!response.ok) {
      throw new Error(`debug sessions request failed: ${response.status}`);
    }
    const data = await response.json();
    debugSessions = data.sessions || [];
    renderDebugSessions();
    if (!selectedDebugSessionId && debugSessions.length) {
      await selectDebugSession(debugSessions[0].sessionId);
    } else if (selectedDebugSessionId) {
      const exists = debugSessions.some((item) => item.sessionId === selectedDebugSessionId);
      if (exists) {
        await fetchDebugTurns(selectedDebugSessionId, { preserveSelection: true });
      }
    }
  } catch (_error) {
    debugSessions = [];
    renderDebugSessions();
  }
}

async function selectDebugSession(targetSessionId) {
  selectedDebugSessionId = targetSessionId;
  renderDebugSessions();
  await fetchDebugTurns(targetSessionId, { preserveSelection: false });
}

async function fetchDebugTurns(targetSessionId, { preserveSelection } = { preserveSelection: true }) {
  if (!debugUiEnabled || !targetSessionId) {
    return;
  }
  try {
    const response = await fetch(`/debug/session-turns?sessionId=${encodeURIComponent(targetSessionId)}`);
    if (!response.ok) {
      throw new Error(`debug turns request failed: ${response.status}`);
    }
    const data = await response.json();
    debugTurns = data.turns || [];
    if (!preserveSelection || !debugTurns.some((item) => item.turn === selectedDebugTurn)) {
      selectedDebugTurn = debugTurns.length ? debugTurns[debugTurns.length - 1].turn : null;
    }
    renderDebugTurns();
    await renderSelectedDebugTrace();
  } catch (_error) {
    debugTurns = [];
    selectedDebugTurn = null;
    renderDebugTurns();
    renderDebugTraceEmpty("turn 목록을 불러오지 못했습니다.");
  }
}

function renderDebugSessions() {
  if (!debugUiEnabled) {
    debugSessionsEl.className = "debug-list empty";
    debugSessionsEl.textContent = "개발 모드에서만 표시됩니다.";
    return;
  }
  if (!debugSessions.length) {
    debugSessionsEl.className = "debug-list empty";
    debugSessionsEl.textContent = "최근 세션 로그가 없습니다.";
    return;
  }
  debugSessionsEl.className = "debug-list";
  debugSessionsEl.innerHTML = debugSessions
    .map((item) => {
      const active = item.sessionId === selectedDebugSessionId ? " is-active" : "";
      const status = item.isActive === false ? "inactive" : "live";
      return `
        <button class="debug-item${active}" type="button" data-session-id="${escapeHtml(item.sessionId)}">
          <span class="debug-item-title">${escapeHtml(item.storySetupId || item.sessionId)}</span>
          <span class="debug-item-meta">${escapeHtml(status)} / turn ${item.latestTurn} / ${escapeHtml(item.lastMessageCode || "n/a")} / ${escapeHtml(item.lastLocationId || "n/a")}</span>
        </button>
      `;
    })
    .join("");
  debugSessionsEl.querySelectorAll("[data-session-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      await selectDebugSession(button.dataset.sessionId);
    });
  });
}

function renderDebugTurns() {
  if (!selectedDebugSessionId) {
    debugTurnsEl.className = "debug-list empty";
    debugTurnsEl.textContent = "세션을 선택하면 turn 목록이 표시됩니다.";
    return;
  }
  if (!debugTurns.length) {
    debugTurnsEl.className = "debug-list empty";
    debugTurnsEl.textContent = "선택한 세션의 turn 로그가 없습니다.";
    return;
  }
  debugTurnsEl.className = "debug-list";
  debugTurnsEl.innerHTML = debugTurns
    .map((item) => {
      const active = item.turn === selectedDebugTurn ? " is-active" : "";
      return `
        <button class="debug-item${active}" type="button" data-turn="${item.turn}">
          <span class="debug-item-title">T${item.turn} · ${escapeHtml(item.messageCode || "n/a")}</span>
          <span class="debug-item-meta">${escapeHtml(item.locationId || "n/a")} / ${escapeHtml(item.input || "새 세션 시작")}</span>
        </button>
      `;
    })
    .join("");
  debugTurnsEl.querySelectorAll("[data-turn]").forEach((button) => {
    button.addEventListener("click", async () => {
      selectedDebugTurn = Number(button.dataset.turn);
      renderDebugTurns();
      await renderSelectedDebugTrace();
    });
  });
}

async function renderSelectedDebugTrace() {
  if (!selectedDebugSessionId || selectedDebugTurn == null) {
    renderDebugTraceEmpty("세션과 turn을 선택하면 agent trace가 표시됩니다.");
    return;
  }
  const data = await fetchTurnDebugBundle(selectedDebugSessionId, selectedDebugTurn);
  if (!data?.found) {
    renderDebugTraceEmpty("선택한 turn의 디버그 로그를 찾지 못했습니다.");
    return;
  }
  debugTraceEl.className = "debug-trace";
  debugTraceEl.innerHTML = renderDebugTraceMarkup(data);
}

function renderDebugTraceEmpty(message) {
  debugTraceEl.className = "debug-trace empty";
  debugTraceEl.textContent = message;
}

function renderDebugTraceMarkup(data) {
  const turnTokens = formatTokenUsage(data.turnTokenUsage);
  const sessionTokens = formatTokenUsage(data.sessionTokenUsage?.combined);
  const provider = data.provider || "n/a";
  const model = data.model || "n/a";
  const fallback = data.usedFallback === true ? "yes" : "no";
  const worldTitle = data.worldBuildResponse?.blueprint?.title || "n/a";
  const sections = [
    renderTraceStage("World Build", data.worldBuildRequest, data.worldBuildResponse, {
      provider: data.worldBuildResponse?.provider,
      model: data.worldBuildResponse?.model,
      fallback: data.worldBuildResponse?.used_fallback,
      tokenUsage: data.worldBuildResponse?.token_usage,
    }),
    renderTraceStage("Intent", data.intentRequest, data.intentResponse, {
      provider: data.intentResponse?.provider,
      model: data.intentResponse?.model,
      fallback: data.intentResponse?.source === "heuristic",
      tokenUsage: data.intentResponse?.token_usage,
    }),
    renderTraceStage("State Proposal", data.stateProposalRequest, data.stateProposalResponse, {
      provider: data.stateProposalResponse?.provider,
      model: data.stateProposalResponse?.model,
      fallback: data.stateProposalResponse?.used_fallback,
      tokenUsage: data.stateProposalResponse?.token_usage,
    }),
    renderTraceStage("Validation", data.validationRequest, data.validationResponse, {
      provider: "deterministic",
      model: "validator",
      fallback: false,
      tokenUsage: null,
    }),
    renderTraceStage("Narrative", data.narrativeRequest, data.narrativeResponse, {
      provider: data.narrativeResponse?.provider,
      model: data.narrativeResponse?.model,
      fallback: data.narrativeResponse?.used_fallback,
      tokenUsage: data.narrativeResponse?.token_usage,
    }),
    renderTraceStage("Game Response", data.gameRequest, data.gameResponse, {
      provider,
      model,
      fallback,
      tokenUsage: null,
    }),
  ].join("");

  return `
    <div class="trace-meta">
      <div>
        <p class="detail-label">Session</p>
        <p class="detail-value">${escapeHtml(data.sessionId)}</p>
      </div>
      <div>
        <p class="detail-label">Turn</p>
        <p class="detail-value">T${data.turn}</p>
      </div>
      <div>
        <p class="detail-label">World</p>
        <p class="detail-value">${escapeHtml(worldTitle)}</p>
      </div>
      <div>
        <p class="detail-label">Tokens</p>
        <p class="detail-value">${escapeHtml(turnTokens)} / session ${escapeHtml(sessionTokens)}</p>
      </div>
    </div>
    ${sections}
  `;
}

function renderTraceStage(title, request, response, meta = {}) {
  const provider = meta.provider || "n/a";
  const model = meta.model || "n/a";
  const fallback = meta.fallback === true ? "fallback" : "live";
  const tokens = formatTokenUsage(meta.tokenUsage);
  return `
    <section class="trace-stage">
      <div class="trace-stage-head">
        <h3 class="trace-stage-title">${escapeHtml(title)}</h3>
        <p class="trace-stage-meta">${escapeHtml(provider)} / ${escapeHtml(model)} / ${escapeHtml(fallback)} / ${escapeHtml(tokens)}</p>
      </div>
      <pre class="trace-pre">${escapeHtml(JSON.stringify({ request, response }, null, 2))}</pre>
    </section>
  `;
}

async function startGame() {
  setLoading(true, "새 스토리를 구성하는 중...");
  try {
    if (!storySetups.length) {
      await fetchStorySetups();
    }
    selectedStorySetupId = selectedStorySetupId || storySetups[0]?.id || null;
    updateStoryTitle(selectedStorySetupId);

    const response = await fetch("/game/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        storySetupId: selectedStorySetupId || undefined,
      }),
    });
    const data = await response.json();
    sessionId = data.sessionId;
    localStorage.setItem(SESSION_KEY, sessionId);
    selectedDebugSessionId = sessionId;
    selectedStorySetupId = data.storySetupId || selectedStorySetupId;
    if (selectedStorySetupId) {
      updateStoryTitle(selectedStorySetupId);
    }
    logEl.innerHTML = "";
    resetTurnHistory();
    appendMessage("ai", data.narrative);
    renderChoices(data.choices || []);
    renderState(data.state);
    appendTurnNode(createStartNode(data));
    if (debugUiEnabled) {
      await fetchDebugSessions();
    }
  } finally {
    setLoading(false);
  }
}

async function restoreState() {
  if (!sessionId) {
    return;
  }
  try {
    if (debugUiEnabled) {
      const debugResponse = await fetch("/debug/sessions");
      if (debugResponse.ok) {
        const debugData = await debugResponse.json();
        const activeSession = (debugData.sessions || []).find((item) => item.sessionId === sessionId);
        if (!activeSession) {
          throw new Error("restore state skipped for stale session");
        }
        if (activeSession.isActive !== true) {
          throw new Error("restore state skipped for inactive session");
        }
      }
    }
    const response = await fetch(`/game/state?sessionId=${encodeURIComponent(sessionId)}`);
    if (!response.ok) {
      throw new Error(`restore state failed: ${response.status}`);
    }
    const data = await response.json();
    selectedStorySetupId = data.storySetupId || selectedStorySetupId;
    if (selectedStorySetupId && storySetups.some((preset) => preset.id === selectedStorySetupId)) {
      updateStoryTitle(selectedStorySetupId);
    }
    renderState(data.state);
    suggestButton.disabled = false;
    if (debugUiEnabled && !selectedDebugSessionId) {
      selectedDebugSessionId = sessionId;
    }
  } catch (_error) {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(LEGACY_SESSION_KEY);
    sessionId = null;
    selectedDebugSessionId = null;
  }
}

async function fetchStorySetups() {
  const response = await fetch("/story-setups");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  storySetups = data.presets || [];
  renderStorySetupSelector();
}

async function sendAction(payload) {
  if (!sessionId) {
    await startGame();
  }

  if (payload.inputText) {
    appendMessage("player", payload.inputText);
  } else if (payload.choiceText) {
    appendMessage("player", payload.choiceText);
  }

  setLoading(true, "에이전트가 다음 장면을 생성하는 중...");
  try {
    const response = await fetch("/game/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, ...payload }),
    });
    const data = await response.json();
    appendMessage("ai", data.narrative);
    renderChoices(data.choices || []);
    renderState(data.state);
    appendTurnNode(createActionNode(payload, data));
    if (debugUiEnabled) {
      await fetchDebugSessions();
    }
  } finally {
    setLoading(false);
  }
}

async function requestChoices() {
  if (!sessionId) {
    return;
  }
  setLoading(true, "현재 상황에 맞는 선택지를 정리하는 중...");
  try {
    const response = await fetch(`/game/choices?sessionId=${encodeURIComponent(sessionId)}`);
    if (!response.ok) {
      throw new Error(`choices request failed: ${response.status}`);
    }
    const data = await response.json();
    renderChoices(data.choices || []);
  } finally {
    setLoading(false);
  }
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const inputText = inputEl.value.trim();
  if (!inputText) {
    return;
  }
  inputEl.value = "";
  await sendAction({ inputText });
});

startButton.addEventListener("click", startGame);
suggestButton.addEventListener("click", requestChoices);
tabGameEl.addEventListener("click", () => setSideTab("game"));
tabDebugEl.addEventListener("click", () => {
  if (!debugUiEnabled) {
    return;
  }
  setSideTab("debug");
});

renderStorySetupSelector();
fetchHealth().then(async () => {
  await fetchStorySetups();
  await restoreState();
  if (debugUiEnabled) {
    await fetchDebugSessions();
  }
  if (!sessionId) {
    resetTurnHistory();
    logEl.innerHTML = "";
    renderChoices([]);
    renderEmptyState();
    appendMessage("ai", "에이전트가 준비한 스토리를 시작하려면 새 세션 시작을 누르세요.");
  }
});
