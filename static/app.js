// Web Frontend State Management & API Client

const state = {
  currentRound: 1,
  maxRounds: 7,
  minAccuseRound: 4,
  canAccuse: false,
  status: "idle",
  agents: [],
  isLoading: false,
};

// DOM Elements
const roundDisplay = document.getElementById("round-display");
const suspectsList = document.getElementById("suspects-list");
const suspectsCount = document.getElementById("suspects-count");
const chatMessages = document.getElementById("chat-messages");
const playerInput = document.getElementById("player-input");
const sendBtn = document.getElementById("send-btn");
const accuseBtn = document.getElementById("accuse-btn");
const restartBtn = document.getElementById("restart-btn");
const mockToggle = document.getElementById("mock-toggle");
const speakerIndicator = document.getElementById("speaker-indicator");

const accuseModal = document.getElementById("accuse-modal");
const closeModalBtn = document.getElementById("close-modal-btn");
const cancelAccuseBtn = document.getElementById("cancel-accuse-btn");
const accuseSuspectsGrid = document.getElementById("accuse-suspects-grid");

const resultModal = document.getElementById("result-modal");
const resultBanner = document.getElementById("result-banner");
const resultTitle = document.getElementById("result-title");
const resultSubtitle = document.getElementById("result-subtitle");
const truthContent = document.getElementById("truth-content");
const resultRestartBtn = document.getElementById("result-restart-btn");

// Avatars mapping
function getAvatar(id) {
  if (id === "player") return "🕵️‍♂️";
  if (id === "agent_butler") return "🧐";
  if (id === "agent_gardener") return "🧑‍🌾";
  return "👤";
}

// 格式化发言角色名
function getSpeakerLabel(msg) {
  if (msg.sender_id === "player") return "侦探 (你)";
  return msg.sender_name || msg.sender_id;
}

// 通用健壮请求封装（针对隧道代理网络波动自动重试 2 次）
async function fetchWithRetry(url, options = {}, retries = 2, backoff = 800) {
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(url, options);
      return res;
    } catch (err) {
      if (i === retries) throw err;
      console.warn(`[网络波动] 请求 ${url} 失败，正在重试第 ${i + 1} 次...`, err);
      await new Promise((r) => setTimeout(r, backoff * (i + 1)));
    }
  }
}

// 初始化/开局
async function initGame() {
  setLoading(true);
  try {
    const res = await fetchWithRetry("/api/game/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mock_mode: false,
      }),
    });
    const data = await res.json();
    if (data.status === "success") {
      renderFullState(data.state);
    } else {
      alert("启动游戏失败: " + (data.detail || "未知错误"));
    }
  } catch (err) {
    console.error("Init error:", err);
    alert("无法连接后端服务，请确认服务已启动。");
  } finally {
    setLoading(false);
  }
}

// 渲染完整状态
function renderFullState(gameState) {
  state.currentRound = gameState.current_round;
  state.maxRounds = gameState.max_rounds;
  state.minAccuseRound = gameState.min_accuse_round;
  state.canAccuse = gameState.can_accuse;
  state.agents = gameState.agents;
  state.status = gameState.status;

  // 1. 进度指示
  roundDisplay.textContent = `第 ${state.currentRound} / ${state.maxRounds} 轮`;

  // 2. 嫌疑人列表
  suspectsCount.textContent = `${state.agents.length} 位嫌疑人`;
  suspectsList.innerHTML = "";
  state.agents.forEach((agent) => {
    const card = document.createElement("div");
    card.className = "suspect-card";
    card.innerHTML = `
      <div class="suspect-avatar">${getAvatar(agent.id)}</div>
      <div class="suspect-info">
        <div class="suspect-name">${agent.name}</div>
        <div class="suspect-role">${agent.role}</div>
      </div>
    `;
    suspectsList.appendChild(card);
  });

  // 3. 对话笔录消息流
  chatMessages.innerHTML = "";
  let lastRound = 0;
  if (gameState.messages && gameState.messages.length > 0) {
    gameState.messages.forEach((msg) => {
      if (msg.round_idx !== lastRound) {
        renderRoundSeparator(msg.round_idx);
        lastRound = msg.round_idx;
      }
      renderMessageBubble(msg);
    });
  } else {
    // 渲染欢迎/开场指引
    const welcomeBubble = document.createElement("div");
    welcomeBubble.className = "thinking-bubble";
    welcomeBubble.innerHTML = `
      <span>🏛️ 伯爵书房大门已封锁。管家与园丁已带到审讯室内，请侦探开始第一轮质问。</span>
    `;
    chatMessages.appendChild(welcomeBubble);
  }
  scrollChatToBottom();

  // 4. 指认真凶按钮控制
  updateAccuseButton();

  // 5. 检查是否结算
  if (gameState.status === "victory" || gameState.status === "defeat") {
    showResultModal(
      gameState.status,
      gameState.truth_revealed || "案情已揭晓",
      gameState.chosen_name || "",
      gameState.real_culprit_name || "老管家"
    );
  } else if (gameState.status === "mandatory_accuse") {
    openAccuseModal(true);
  }
}

// 渲染分轮分隔符
function renderRoundSeparator(roundNum) {
  const sep = document.createElement("div");
  sep.className = "round-separator";
  sep.innerHTML = `<span>第 ${roundNum} 轮 审讯</span>`;
  chatMessages.appendChild(sep);
}

// 渲染单条气泡
function renderMessageBubble(msg) {
  const isPlayer = msg.sender_id === "player" || msg.is_player;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${isPlayer ? "bubble-player" : "bubble-agent"}`;

  bubble.innerHTML = `
    <div class="bubble-avatar">${getAvatar(msg.sender_id)}</div>
    <div class="bubble-content-wrap">
      <div class="bubble-meta">${getSpeakerLabel(msg)}</div>
      <div class="bubble-body">${escapeHTML(msg.content)}</div>
    </div>
  `;
  chatMessages.appendChild(bubble);
}

// 渲染思考中动画气泡
function showThinkingIndicator(speakerName = "嫌疑人") {
  const existing = document.getElementById("thinking-indicator");
  if (existing) existing.remove();

  const bubble = document.createElement("div");
  bubble.id = "thinking-indicator";
  bubble.className = "thinking-bubble";
  bubble.innerHTML = `
    <span>${speakerName} 正在思考供词...</span>
    <div class="dots">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  `;
  chatMessages.appendChild(bubble);
  scrollChatToBottom();
}

function removeThinkingIndicator() {
  const existing = document.getElementById("thinking-indicator");
  if (existing) existing.remove();
}

function updateAccuseButton() {
  if (state.canAccuse) {
    accuseBtn.style.display = "inline-flex";
    accuseBtn.title = "已达到第4轮，随时可指认真凶结案";
  } else {
    accuseBtn.style.display = "none";
  }
}

function scrollChatToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHTML(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setLoading(isLoading) {
  state.isLoading = isLoading;
  sendBtn.disabled = isLoading;
  playerInput.disabled = isLoading;
  if (isLoading) {
    speakerIndicator.textContent = "审讯进行中...";
  } else {
    speakerIndicator.textContent = "等待侦探提问...";
  }
}

// 发送质询
async function handleSend() {
  const text = playerInput.value.trim();
  if (!text || state.isLoading) return;

  // 1. 本地立即回显玩家气泡
  playerInput.value = "";
  renderMessageBubble({
    sender_id: "player",
    sender_name: "侦探(你)",
    content: text,
    is_player: true,
  });
  scrollChatToBottom();

  setLoading(true);
  showThinkingIndicator("嫌疑人");

  try {
    const res = await fetchWithRetry("/api/game/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });

    removeThinkingIndicator();
    const data = await res.json();

    if (!res.ok) {
      alert("发言请求失败: " + (data.detail || "服务端异常"));
      return;
    }

    if (data.status === "success") {
      // 重新按后端权威状态刷新完整面板
      renderFullState(data.state);
    }
  } catch (err) {
    removeThinkingIndicator();
    console.error("Speak error:", err);
    alert("通信失败: " + err.message);
  } finally {
    setLoading(false);
  }
}

// 打开指认弹窗
function openAccuseModal(isMandatory = false) {
  accuseSuspectsGrid.innerHTML = "";
  state.agents.forEach((agent) => {
    const btn = document.createElement("button");
    btn.className = "accuse-target-btn";
    btn.innerHTML = `
      <div class="target-avatar">${getAvatar(agent.id)}</div>
      <div class="target-name">${agent.name}</div>
      <div class="target-role">${agent.role}</div>
    `;
    btn.onclick = () => submitAccusation(agent.id);
    accuseSuspectsGrid.appendChild(btn);
  });

  if (isMandatory) {
    cancelAccuseBtn.style.display = "none";
    closeModalBtn.style.display = "none";
  } else {
    cancelAccuseBtn.style.display = "block";
    closeModalBtn.style.display = "block";
  }

  accuseModal.classList.remove("hidden");
}

function closeAccuseModal() {
  accuseModal.classList.add("hidden");
}

// 提交指控凶手
async function submitAccusation(agentId) {
  closeAccuseModal();
  setLoading(true);

  try {
    const res = await fetchWithRetry("/api/game/accuse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert("指认失败: " + (data.detail || "服务端错误"));
      return;
    }

    if (data.status === "success") {
      const acc = data.accusation;
      renderFullState(data.state);
      showResultModal(acc.result, acc.truth_revealed, acc.chosen_name, acc.real_culprit_name);
    }
  } catch (err) {
    console.error("Accuse error:", err);
    alert("指控请求失败: " + err.message);
  } finally {
    setLoading(false);
  }
}

// 结案结算展示
function showResultModal(result, truthText, chosenName = "", realCulpritName = "") {
  resultBanner.className = `result-banner ${result}`;
  if (result === "victory") {
    resultTitle.textContent = "🎉 真相大白！探案胜利！";
    resultSubtitle.textContent = `你成功识破伪装，指认了真凶【${chosenName || "老管家"}】！`;
  } else {
    resultTitle.textContent = "❌ 冤假错案！推理失败！";
    resultSubtitle.textContent = `你指认了【${chosenName}】，但真凶其实是【${realCulpritName || "老管家"}】！`;
  }

  truthContent.textContent = truthText;
  resultModal.classList.remove("hidden");
}

// 事件绑定
sendBtn.addEventListener("click", handleSend);
playerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

accuseBtn.addEventListener("click", () => openAccuseModal(false));
closeModalBtn.addEventListener("click", closeAccuseModal);
cancelAccuseBtn.addEventListener("click", closeAccuseModal);

restartBtn.addEventListener("click", () => {
  if (confirm("确定重新开始本案审讯吗？当前进度将被重置。")) {
    // Hide any result modal that may be visible
    const resultModal = document.getElementById("result-modal");
    if (resultModal) {
      resultModal.classList.add("hidden");
    }
    // Reinitialize the game state
    initGame();
  }
});

resultRestartBtn.addEventListener("click", () => {
  resultModal.classList.add("hidden");
  initGame();
});

// 页面加载自动开启
window.addEventListener("DOMContentLoaded", () => {
  initGame();
});
