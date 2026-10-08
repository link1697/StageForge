// State Management & Client Logic (Strings separated to strings.js)
const state = {
  currentRound: 1,
  maxRounds: 7,
  minAccuseRound: 4,
  canAccuse: false,
  status: "idle",
  agents: [],
  isLoading: false,
  lang: localStorage.getItem("stageforge_lang") || "zh",
  theme: localStorage.getItem("stageforge_theme") || "dark",
  rawState: null,
  dismissedClueIds: new Set(),
};

// 获取翻译文案（由 strings.js 集中管理）
function t(key, params = {}) {
  const dict = (typeof UI_DICTIONARIES !== "undefined" ? UI_DICTIONARIES[state.lang] : null) || {};
  const fallback = (typeof UI_DICTIONARIES !== "undefined" ? UI_DICTIONARIES.zh : null) || {};
  let text = dict[key] || fallback[key] || key;
  for (const [k, v] of Object.entries(params)) {
    text = text.replaceAll(`{${k}}`, v);
  }
  return text;
}

// 应用静态 DOM i18n
function applyI18n() {
  document.documentElement.lang = state.lang === "en" ? "en" : "zh-CN";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.innerHTML = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.placeholder = t(key);
  });

  // 设置弹窗内表单项选中
  const langSelect = document.getElementById("lang-select");
  if (langSelect) langSelect.value = state.lang;
  const themeSelect = document.getElementById("theme-select");
  if (themeSelect) themeSelect.value = state.theme;

  // 主题应用
  applyTheme(state.theme);

  if (state.rawState) {
    renderFullState(state.rawState);
  }
}

// 主题切换
function applyTheme(theme) {
  state.theme = theme;
  localStorage.setItem("stageforge_theme", theme);
  document.body.setAttribute("data-theme", theme);
}

// DOM Elements
const roundDisplay = document.getElementById("round-display");
const suspectsList = document.getElementById("suspects-list");
const suspectsCount = document.getElementById("suspects-count");
const chatMessages = document.getElementById("chat-messages");
const playerInput = document.getElementById("player-input");
const sendBtn = document.getElementById("send-btn");
const accuseBtn = document.getElementById("accuse-btn");
const restartBtn = document.getElementById("restart-btn");
const speakerIndicator = document.getElementById("speaker-indicator");

const settingsBtn = document.getElementById("settings-btn");
const settingsModal = document.getElementById("settings-modal");
const closeSettingsBtn = document.getElementById("close-settings-btn");
const applySettingsBtn = document.getElementById("apply-settings-btn");
const langSelect = document.getElementById("lang-select");
const themeSelect = document.getElementById("theme-select");

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
  const agent = state.agents.find((a) => a.id === id);
  if (agent && agent.avatar) return agent.avatar;
  if (id === "agent_butler") return "🧐";
  if (id === "agent_gardener") return "🧑‍🌾";
  return "👤";
}

// 格式化发言角色名
function getSpeakerLabel(msg) {
  if (msg.sender_id === "player" || msg.is_player) return t("speaker_detective_me");
  return msg.sender_name || msg.sender_id;
}

// 通用健壮请求封装（针对网络波动自动重试 2 次）
async function fetchWithRetry(url, options = {}, retries = 2, backoff = 800) {
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(url, options);
      return res;
    } catch (err) {
      if (i === retries) throw err;
      console.warn(`[网络重试] ${url} 正在重试第 ${i + 1} 次...`, err);
      await new Promise((r) => setTimeout(r, backoff * (i + 1)));
    }
  }
}

// 初始化/开局 (携带当前选择的语言)
async function initGame() {
  setLoading(true);
  try {
    const res = await fetchWithRetry("/api/game/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mock_mode: false,
        lang: state.lang,
      }),
    });
    const data = await res.json();
    if (data.status === "success") {
      state.dismissedClueIds.clear();
      renderFullState(data.state);
    } else {
      alert("启动游戏失败: " + (data.detail || "未知错误"));
    }
  } catch (err) {
    console.error("Init error:", err);
    alert(t("connection_failed"));
  } finally {
    setLoading(false);
  }
}

// 渲染完整状态
function renderFullState(gameState) {
  state.rawState = gameState;
  state.currentRound = gameState.current_round;
  state.maxRounds = gameState.max_rounds;
  state.minAccuseRound = gameState.min_accuse_round;
  state.canAccuse = gameState.can_accuse;
  state.agents = gameState.agents;
  state.status = gameState.status;

  // 1. 标题与案情通报 (动态根据 YAML 渲染)
  const caseTitle = gameState.case_name || gameState.name;
  const gameTitleEl = document.getElementById("game-title");
  if (gameTitleEl && caseTitle) {
    gameTitleEl.textContent = caseTitle;
    document.title = `${caseTitle} · StageForge`;
  }
  const transcriptTitleEl = document.getElementById("chat-transcript-title");
  if (transcriptTitleEl && caseTitle) {
    transcriptTitleEl.textContent = t("transcript_title", { case: caseTitle });
  }
  const guideModalTitleEl = document.getElementById("guide-modal-title");
  if (guideModalTitleEl && caseTitle) {
    guideModalTitleEl.textContent = t("guide_modal_title", { case: caseTitle });
  }
  const gameDescEl = document.getElementById("game-description");
  if (gameDescEl) {
    const briefText = gameState.case_brief || gameState.description;
    if (briefText) {
      gameDescEl.textContent = briefText;
    }
  }

  // 2. 侧边栏规则卡片动态轮次
  const ruleRounds = document.getElementById("sidebar-rule-rounds");
  if (ruleRounds) {
    ruleRounds.innerHTML = t("rule_rounds", { max: gameState.max_rounds });
  }
  const ruleAccuse = document.getElementById("sidebar-rule-accuse");
  if (ruleAccuse) {
    ruleAccuse.innerHTML = t("rule_accuse", { min: gameState.min_accuse_round });
  }
  const ruleMandatory = document.getElementById("sidebar-rule-mandatory");
  if (ruleMandatory) {
    ruleMandatory.innerHTML = t("rule_mandatory", { max: gameState.max_rounds });
  }

  // 3. 探案指引 Modal 动态数据渲染
  const guideStoryDesc = document.getElementById("guide-story-desc");
  if (guideStoryDesc && gameState.description) {
    guideStoryDesc.innerHTML = `${escapeHTML(gameState.description)}<br>${t("guide_story_waiting")}`;
  }
  const guideRule1 = document.getElementById("guide-rule-1");
  if (guideRule1) {
    guideRule1.textContent = t("guide_rule1_desc", { count: state.agents.length });
  }
  const guideRule2 = document.getElementById("guide-rule-2");
  if (guideRule2) {
    guideRule2.innerHTML = t("guide_rule2_desc", {
      max: gameState.max_rounds,
      min: gameState.min_accuse_round,
    });
  }

  const guidePreview = document.getElementById("guide-suspects-preview");
  if (guidePreview) {
    guidePreview.innerHTML = "";
    state.agents.forEach((agent) => {
      const item = document.createElement("div");
      item.className = "preview-item";
      const descText = agent.description || agent.role || "";
      // 提取并清理 role 中的 (Suspect) / （嫌疑人）等冗余标注
      const cleanRole = (agent.role || "")
        .replace(/\s*[\(（](?:Suspect|嫌疑人)[\)）]/gi, "")
        .replace(/^\((.*)\)$/, "$1")
        .trim();
      item.innerHTML = `
        <span class="preview-avatar">${agent.avatar || getAvatar(agent.id)}</span>
        <div class="preview-info">
          <div class="preview-header-line">
            <strong class="preview-name">${escapeHTML(agent.name)}</strong>
            <span class="preview-role-badge">${escapeHTML(cleanRole)}</span>
          </div>
          <p class="preview-desc">${escapeHTML(descText)}</p>
        </div>
      `;
      guidePreview.appendChild(item);
    });
  }

  // 4. 进度指示
  roundDisplay.textContent = t("round_format", {
    curr: state.currentRound,
    max: state.maxRounds,
  });

  // 5. 嫌疑人列表
  suspectsCount.textContent = `${state.agents.length}${t("suspects_count_suffix")}`;
  suspectsList.innerHTML = "";
  state.agents.forEach((agent) => {
    const card = document.createElement("div");
    card.className = "suspect-card";
    // 侧边栏本身已是「嫌疑人名录 / Suspect List」，卡片中角色身份无需再重复后缀 (Suspect) 或（嫌疑人）
    const cleanRole = (agent.role || "")
      .replace(/\s*[\(（](?:Suspect|嫌疑人)[\)）]/gi, "")
      .trim();
    card.innerHTML = `
      <div class="suspect-avatar">${agent.avatar || getAvatar(agent.id)}</div>
      <div class="suspect-info">
        <div class="suspect-name">${agent.name}</div>
        <div class="suspect-role">${cleanRole}</div>
      </div>
    `;
    suspectsList.appendChild(card);
  });

  // 5.2 渲染案件物证库列表与可搜查疑点操作栏
  renderCluesAndActions(gameState.clues || []);

  // 6. 对话笔录消息流
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
    const names = state.agents.map((a) => a.name).join(", ");
    const welcomeBubble = document.createElement("div");
    welcomeBubble.className = "thinking-bubble";
    welcomeBubble.innerHTML = `
      <span>${t("chat_welcome", { names: names || "Suspects" })}</span>
    `;
    chatMessages.appendChild(welcomeBubble);
  }
  scrollChatToBottom();

  // 7. 指认真凶按钮控制
  updateAccuseButton();

  // 8. 检查是否结算或强制指控
  if (gameState.status === "victory" || gameState.status === "defeat") {
    // 延迟 600ms 弹出结算，让玩家先看清最后一轮发言
    setTimeout(() => {
      showResultModal(
        gameState.status,
        gameState.truth_revealed || "案情已揭晓",
        gameState.chosen_name || "",
        gameState.real_culprit_name || "真凶"
      );
    }, 600);
  } else if (gameState.status === "mandatory_accuse") {
    // 到达最终轮次：先延迟 1500ms 让玩家阅读完当前轮所有嫌疑人的最终辩解，再弹出指控弹窗
    setTimeout(() => {
      openAccuseModal(true);
    }, 1500);
  }
}

// 渲染物证卡片与待验证破绽按钮
function renderCluesAndActions(clues) {
  const cluesList = document.getElementById("clues-list");
  const cluesCount = document.getElementById("clues-count");
  const cluesActionBar = document.getElementById("clues-action-bar");
  const cluesActionButtons = document.getElementById("clues-action-buttons");

  if (!cluesList) return;

  const discoveredClues = clues.filter((c) => c.status === "discovered");
  const availableClues = clues.filter((c) => c.status === "available_for_search");

  if (cluesCount) {
    cluesCount.textContent = state.lang === "en" 
      ? `${discoveredClues.length} Discovered` 
      : `${discoveredClues.length} 项已起获`;
  }

  // 渲染侧边栏物证库：只有真正搜查起获的物证才呈现在物证库中，未起获前不泄漏名字和藏匿地点
  cluesList.innerHTML = "";
  if (discoveredClues.length === 0) {
    cluesList.innerHTML = `
      <div style="font-size: 13px; color: var(--text-muted); padding: 18px 12px; text-align: center; border: 1px dashed var(--border-color); border-radius: 8px; margin: 4px 0;">
        <span style="font-size: 18px; display: block; margin-bottom: 4px;">📂</span>
        ${t("clues_empty_title")}<br>
        <span style="font-size: 11px; opacity: 0.8;">${t("clues_empty_hint")}</span>
      </div>
    `;
  } else {
    discoveredClues.forEach((clue) => {
      const card = document.createElement("div");
      card.className = "clue-card discovered";
      card.innerHTML = `
        <div class="clue-card-header">
          <span class="clue-card-title">🔍 ${escapeHTML(clue.name)}</span>
          <span class="clue-badge discovered">${t("clues_status_verified")}</span>
        </div>
        <div class="clue-card-loc">${t("clues_location_prefix")}${escapeHTML(clue.location)}</div>
        <div class="clue-card-detail">${escapeHTML(clue.detail)}</div>
      `;
      cluesList.appendChild(card);
    });
  }

  // 渲染对话区上方的待验证破绽操作栏（平时完全隐藏，仅当有新破绽被言语触发时弹出）
  const cluesActionTitle = document.getElementById("clues-action-title");
  if (cluesActionTitle) {
    cluesActionTitle.textContent = t("clues_action_title");
  }

  if (cluesActionBar && cluesActionButtons) {
    // 过滤出用户未点击「暂时不查验」的待搜查线索
    const pendingClues = availableClues.filter(
      (ac) => !state.dismissedClueIds.has(ac.id)
    );

    if (pendingClues.length > 0) {
      cluesActionButtons.innerHTML = "";
      pendingClues.forEach((ac) => {
        const btn = document.createElement("button");
        btn.className = "clue-search-btn";
        btn.innerHTML = `<span>${t("clues_search_btn_prefix")}${escapeHTML(ac.action_prompt)}</span>`;
        btn.onclick = () => executeSearchClue(ac.id, ac.name);
        cluesActionButtons.appendChild(btn);
      });

      // 添加「暂时不查验 / Dismiss」按钮：点击后收起破绽条
      const dismissBtn = document.createElement("button");
      dismissBtn.className = "clue-dismiss-btn";
      dismissBtn.textContent = t("clues_dismiss_btn");
      dismissBtn.onclick = () => {
        pendingClues.forEach((ac) => state.dismissedClueIds.add(ac.id));
        cluesActionBar.classList.add("hidden");
      };
      cluesActionButtons.appendChild(dismissBtn);

      cluesActionBar.classList.remove("hidden");
    } else {
      cluesActionBar.classList.add("hidden");
    }
  }
}

// 侦探执行物证搜查指令
async function executeSearchClue(clueId, clueName) {
  setLoading(true);
  try {
    const res = await fetchWithRetry("/api/game/clue/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clue_id: clueId }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert("搜查失败: " + (data.detail || "服务端异常"));
      return;
    }
    if (data.status === "success") {
      renderFullState(data.state);
      // 成功提示
      alert(`【搜查大捷】已在指定地点起获关键铁证：${clueName}！\n证据档案已记入卷宗，嫌疑人将无法再推诿此项事实！`);
    }
  } catch (err) {
    console.error("Search clue error:", err);
    alert("搜查请求异常: " + err.message);
  } finally {
    setLoading(false);
  }
}



// 渲染分轮分隔符
function renderRoundSeparator(roundNum) {
  const sep = document.createElement("div");
  sep.className = "round-separator";
  sep.innerHTML = `<span>${t("round_separator", { round: roundNum })}</span>`;
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
    <span>${t("thinking_text", { name: speakerName })}</span>
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
    accuseBtn.title = t("btn_accuse_tooltip", { min: state.minAccuseRound });
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
    speakerIndicator.textContent = t("speaker_indicator_busy");
  } else {
    speakerIndicator.textContent = t("speaker_indicator_wait");
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
    sender_name: t("speaker_detective_me"),
    content: text,
    is_player: true,
  });
  scrollChatToBottom();

  setLoading(true);
  showThinkingIndicator(state.lang === "en" ? "Suspect" : "嫌疑人");

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
    cancelAccuseBtn.style.display = "block";
    cancelAccuseBtn.textContent = state.lang === "en" ? "Review Transcript First" : "先查看审讯笔录";
    closeModalBtn.style.display = "block";
  } else {
    cancelAccuseBtn.style.display = "block";
    cancelAccuseBtn.textContent = t("btn_cancel_accuse");
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
    resultTitle.textContent = t("result_victory_title");
    resultSubtitle.textContent = t("result_victory_sub", { name: chosenName });
  } else {
    resultTitle.textContent = t("result_defeat_title");
    resultSubtitle.textContent = t("result_defeat_sub", { chosen: chosenName, real: realCulpritName });
  }

  truthContent.textContent = truthText;
  resultModal.classList.remove("hidden");
}

// 设置弹窗控制
function openSettingsModal() {
  if (langSelect) langSelect.value = state.lang;
  if (themeSelect) themeSelect.value = state.theme;
  if (settingsModal) settingsModal.classList.remove("hidden");
}

function closeSettingsModal() {
  if (settingsModal) settingsModal.classList.add("hidden");
}

async function handleSaveSettings() {
  const newLang = langSelect.value;
  const newTheme = themeSelect.value;
  const langChanged = newLang !== state.lang;

  state.lang = newLang;
  localStorage.setItem("stageforge_lang", newLang);
  applyTheme(newTheme);
  applyI18n();
  closeSettingsModal();

  if (langChanged) {
    // 语言改变时，热更新后端当前对局语言配置，保留当前对局进度、轮次与历史记录
    try {
      const res = await fetchWithRetry("/api/game/language", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: newLang }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.state) {
          renderFullState(data.state);
          return;
        }
      }
    } catch (err) {
      console.warn("更新服务器语言失败，仅在前端更新:", err);
    }
  }

  if (state.rawState) {
    renderFullState(state.rawState);
  }
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

if (settingsBtn) settingsBtn.addEventListener("click", openSettingsModal);
if (closeSettingsBtn) closeSettingsBtn.addEventListener("click", closeSettingsModal);
if (applySettingsBtn) applySettingsBtn.addEventListener("click", handleSaveSettings);

restartBtn.addEventListener("click", () => {
  if (confirm(t("restart_confirm"))) {
    const resModal = document.getElementById("result-modal");
    if (resModal) resModal.classList.add("hidden");
    initGame();
  }
});

resultRestartBtn.addEventListener("click", () => {
  resultModal.classList.add("hidden");
  initGame();
});

// 移动端档案侧边抽屉交互
const infoDrawerBtn = document.getElementById("info-drawer-btn");
const sidebarDrawer = document.getElementById("sidebar-drawer");
const drawerBackdrop = document.getElementById("drawer-backdrop");
const closeDrawerBtn = document.getElementById("close-drawer-btn");

function openMobileDrawer() {
  if (sidebarDrawer) sidebarDrawer.classList.add("open");
  if (drawerBackdrop) drawerBackdrop.classList.remove("hidden");
}

function closeMobileDrawer() {
  if (sidebarDrawer) sidebarDrawer.classList.remove("open");
  if (drawerBackdrop) drawerBackdrop.classList.add("hidden");
}

if (infoDrawerBtn) infoDrawerBtn.addEventListener("click", openMobileDrawer);
if (closeDrawerBtn) closeDrawerBtn.addEventListener("click", closeMobileDrawer);
if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeMobileDrawer);

// 探案指南 Modal 交互
const guideModal = document.getElementById("guide-modal");
const guideBtn = document.getElementById("guide-btn");
const closeGuideBtn = document.getElementById("close-guide-btn");
const startInvestigationBtn = document.getElementById("start-investigation-btn");

function openGuideModal() {
  if (guideModal) guideModal.classList.remove("hidden");
}

function closeGuideModal() {
  if (guideModal) guideModal.classList.add("hidden");
}

if (guideBtn) guideBtn.addEventListener("click", openGuideModal);
if (closeGuideBtn) closeGuideBtn.addEventListener("click", closeGuideModal);
if (startInvestigationBtn) startInvestigationBtn.addEventListener("click", closeGuideModal);

// 页面加载自动开启游戏
window.addEventListener("DOMContentLoaded", async () => {
  // 先应用本地缓存或默认 i18n
  applyI18n();

  try {
    const res = await fetchWithRetry("/api/game/state");
    const data = await res.json();
    if (data.active && data.state) {
      // 若后端已有运行中的对局，以当前对局的语言为准，确保 UI 与剧情语言 100% 同步
      if (data.state.lang && data.state.lang !== state.lang) {
        state.lang = data.state.lang;
        localStorage.setItem("stageforge_lang", data.state.lang);
        applyI18n();
      }
      renderFullState(data.state);
    } else {
      await initGame();
    }
  } catch (err) {
    await initGame();
  }
  openGuideModal();
});
