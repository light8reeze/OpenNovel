const logEl = document.getElementById("log");
const choicesEl = document.getElementById("choices");
const stateEl = document.getElementById("state");
const formEl = document.getElementById("input-form");
const inputEl = document.getElementById("input");
const geminiKeyEl = document.getElementById("gemini-key");
const startButton = document.getElementById("start-button");

const SESSION_KEY = "open-novel-session";
const LEGACY_SESSION_KEY = "novel-gg-session";
const GEMINI_KEY_STORAGE = "open-novel-gemini-key";
const LEGACY_GEMINI_KEY_STORAGE = "novel-gg-gemini-key";

let sessionId =
  localStorage.getItem(SESSION_KEY) || localStorage.getItem(LEGACY_SESSION_KEY);
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
      <dt>Quest Stage</dt><dd>${state.quests.murder_case.stage}</dd>
    </dl>
  `;
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
  appendMessage("ai", data.narrative);
  renderChoices(data.choices);
  renderState(data.state);
}

async function restoreState() {
  if (!sessionId) {
    return;
  }
  const response = await fetch(
    `/game/state?sessionId=${encodeURIComponent(sessionId)}`,
  );
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

restoreState().then(() => {
  if (!sessionId) {
    startGame();
  }
});
