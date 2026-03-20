const logEl = document.getElementById("log");
const choicesEl = document.getElementById("choices");
const stateEl = document.getElementById("state");
const formEl = document.getElementById("input-form");
const inputEl = document.getElementById("input");
const geminiKeyEl = document.getElementById("gemini-key");
const startButton = document.getElementById("start-button");
const graphEl = document.getElementById("graph");
const graphHoverEl = document.getElementById("graph-hover");
const turnDetailEl = document.getElementById("turn-detail");
const graphModeEl = document.getElementById("graph-mode");

const SESSION_KEY = "open-novel-session";
const LEGACY_SESSION_KEY = "novel-gg-session";
const GEMINI_KEY_STORAGE = "open-novel-gemini-key";
const LEGACY_GEMINI_KEY_STORAGE = "novel-gg-gemini-key";
const SVG_NS = "http://www.w3.org/2000/svg";

let sessionId =
  localStorage.getItem(SESSION_KEY) || localStorage.getItem(LEGACY_SESSION_KEY);
let debugUiEnabled = false;
let turnHistory = [];
let selectedTurnId = null;

const debugCache = new Map();

geminiKeyEl.value =
  localStorage.getItem(GEMINI_KEY_STORAGE) ||
  localStorage.getItem(LEGACY_GEMINI_KEY_STORAGE) ||
  "";

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

function renderState(state) {
  stateEl.innerHTML = `
    <dl>
      <dt>Turn</dt><dd>${state.meta.turn}</dd>
      <dt>HP</dt><dd>${state.player.hp}</dd>
      <dt>Gold</dt><dd>${state.player.gold}</dd>
      <dt>Location</dt><dd>${state.player.location_id}</dd>
      <dt>Quest Stage</dt><dd>${state.quests.sunken_ruins.stage}</dd>
    </dl>
  `;
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
  } catch (_error) {
    graphModeEl.textContent = "Debug logs unavailable";
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
    questStage: data.state.quests.sunken_ruins.stage,
    hp: data.state.player.hp,
    gold: data.state.player.gold,
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
    questStage: data.state.quests.sunken_ruins.stage,
    hp: data.state.player.hp,
    gold: data.state.player.gold,
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
          (validationFlags.length ? ` / intent=${validationFlags.join(", ")}` : "") +
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

async function loadDebugBundle(node) {
  if (!debugUiEnabled || !sessionId) {
    return null;
  }

  const key = `${sessionId}:${node.turn}`;
  if (debugCache.has(key)) {
    return debugCache.get(key);
  }

  try {
    const response = await fetch(
      `/debug/turn-log?sessionId=${encodeURIComponent(sessionId)}&turn=${encodeURIComponent(node.turn)}`,
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
  const intentTokens = formatTokenUsage(data.intentResponse?.token_usage);
  const narrativeTokens = formatTokenUsage(data.narrativeResponse?.token_usage);

  return `
    <p class="hover-title">T${node.turn} Debug</p>
    <dl class="hover-grid">
      <dt>Input</dt><dd>${escapeHtml(node.playerInput || "새 세션 시작")}</dd>
      <dt>Action</dt><dd>${escapeHtml(actionType)}</dd>
      <dt>Provider</dt><dd>${escapeHtml(provider)}</dd>
      <dt>Model</dt><dd>${escapeHtml(model)}</dd>
      <dt>Fallback</dt><dd>${fallback}</dd>
      <dt>Turn Tokens</dt><dd>${escapeHtml(turnTokens)}</dd>
      <dt>Session Tokens</dt><dd>${escapeHtml(sessionTokens)}</dd>
      <dt>Intent Flags</dt><dd>${escapeHtml(intentFlags)}</dd>
      <dt>Safety Flags</dt><dd>${escapeHtml(safetyFlags)}</dd>
    </dl>
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

async function startGame() {
  const geminiApiKey = geminiKeyEl.value.trim();
  if (geminiApiKey) {
    localStorage.setItem(GEMINI_KEY_STORAGE, geminiApiKey);
  } else {
    localStorage.removeItem(GEMINI_KEY_STORAGE);
  }

  const response = await fetch("/game/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      geminiApiKey: geminiApiKey || undefined,
    }),
  });
  const data = await response.json();
  sessionId = data.sessionId;
  localStorage.setItem(SESSION_KEY, sessionId);
  logEl.innerHTML = "";
  resetTurnHistory();
  appendMessage("ai", data.narrative);
  renderChoices(data.choices);
  renderState(data.state);
  appendTurnNode(createStartNode(data));
}

async function restoreState() {
  if (!sessionId) {
    return;
  }
  const response = await fetch(`/game/state?sessionId=${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    localStorage.removeItem(SESSION_KEY);
    sessionId = null;
    return;
  }
  const data = await response.json();
  renderState(data.state);
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

  const response = await fetch("/game/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, ...payload }),
  });
  const data = await response.json();
  appendMessage("ai", data.narrative);
  renderChoices(data.choices);
  renderState(data.state);
  appendTurnNode(createActionNode(payload, data));
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

fetchHealth().then(() => {
  restoreState().then(() => {
    if (!sessionId) {
      startGame();
    }
  });
});
