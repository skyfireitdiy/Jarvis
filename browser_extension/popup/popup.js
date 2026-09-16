// popup 逻辑：管理多个网关的连接、显示各网关状态、高危动作确认 UI。
//
// 说明：Token 不由用户手填，而是由扩展自动复用浏览器中已登录的 Jarvis 网页登录态。

const els = {
  gateway: document.getElementById("gateway"),
  connectBtn: document.getElementById("connectBtn"),
  gwList: document.getElementById("gwList"),
  confirmBox: document.getElementById("confirmBox"),
  confirmDesc: document.getElementById("confirmDesc"),
  confirmYes: document.getElementById("confirmYes"),
  confirmNo: document.getElementById("confirmNo"),
  logBox: document.getElementById("logBox"),
  clearLogBtn: document.getElementById("clearLogBtn"),
};

/** 追加一条诊断日志到 popup 面板（同时输出到 console）。 */
function log(message) {
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const line = `[${time}] ${message}`;
  console.log("[Jarvis popup]", message);
  if (!els.logBox) return;
  const div = document.createElement("div");
  div.className = "log-line";
  div.textContent = line;
  els.logBox.appendChild(div);
  els.logBox.scrollTop = els.logBox.scrollHeight;
}

const STATE_TEXT = {
  connected: "已连接",
  connecting: "连接中…",
  disconnected: "未连接",
};

/** 转义 HTML，避免网关地址中的特殊字符造成注入。 */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** 渲染网关列表。 */
function renderGateways(list) {
  const items = Array.isArray(list) ? list : [];
  if (items.length === 0) {
    els.gwList.innerHTML = '<div class="hint">尚未添加任何网关。</div>';
    return;
  }

  els.gwList.innerHTML = items
    .map((gw) => {
      const state = gw.state || "disconnected";
      const stateText = STATE_TEXT[state] || state;
      const authText = gw.has_token ? "登录态：已获取" : "登录态：未获取";
      const sessionText = gw.session_id
        ? `session: ${escapeHtml(gw.session_id)}`
        : "";
      const safeGateway = escapeHtml(gw.gateway);
      const isConnected = state === "connected" || state === "connecting";
      return `
        <div class="gw-item">
          <div class="gw-head">
            <span class="dot ${state}"></span>
            <span class="gw-url">${safeGateway}</span>
          </div>
          <div class="gw-meta hint">
            ${stateText} · ${authText}${sessionText ? " · " + sessionText : ""}
          </div>
          <div class="gw-actions">
            <button class="mini" data-action="connect" data-gateway="${safeGateway}" ${
              isConnected ? "disabled" : ""
            }>连接</button>
            <button class="mini secondary" data-action="disconnect" data-gateway="${safeGateway}" ${
              isConnected ? "" : "disabled"
            }>断开</button>
            <button class="mini secondary" data-action="remove" data-gateway="${safeGateway}">移除</button>
          </div>
        </div>
      `;
    })
    .join("");
}

/** 查询 background 当前所有网关状态。 */
async function refreshStatus() {
  try {
    const resp = await chrome.runtime.sendMessage({
      type: "jarvis_get_status",
    });
    if (resp && resp.success) {
      renderGateways(resp.gateways);
      const list = Array.isArray(resp.gateways) ? resp.gateways : [];
      if (list.length === 0) {
        log("状态刷新：无网关");
      } else {
        for (const gw of list) {
          log(
            `状态刷新：${gw.gateway} state=${gw.state} has_token=${gw.has_token}`,
          );
        }
      }
    } else {
      log("状态刷新失败：background 无响应");
    }
  } catch (e) {
    log(`状态刷新异常：${(e && e.message) || String(e)}`);
    renderGateways([]);
  }
}

/** 添加并连接一个网关。 */
async function connect() {
  const gateway = els.gateway.value.trim();
  if (!gateway) {
    alert("请填写网关地址");
    return;
  }
  log(`请求连接：${gateway}`);
  try {
    const resp = await chrome.runtime.sendMessage({
      type: "jarvis_connect",
      gateway,
    });
    if (resp && !resp.success) {
      log(`连接失败：${resp.error || "未知错误"}`);
      alert("连接失败：" + (resp.error || "未知错误"));
    } else {
      log("已向 background 发出连接请求");
    }
  } catch (e) {
    log(`发送消息异常：${(e && e.message) || String(e)}`);
    console.error("[Jarvis] connect failed", e);
  }
  els.gateway.value = "";
  // 稍等片刻再刷新状态，给连接留出时间
  setTimeout(refreshStatus, 800);
}

/** 对指定网关执行操作。 */
async function gatewayAction(action, gateway) {
  try {
    if (action === "connect") {
      await chrome.runtime.sendMessage({ type: "jarvis_connect", gateway });
    } else if (action === "disconnect") {
      await chrome.runtime.sendMessage({ type: "jarvis_disconnect", gateway });
    } else if (action === "remove") {
      await chrome.runtime.sendMessage({
        type: "jarvis_remove_gateway",
        gateway,
      });
    }
  } catch (e) {
    console.error("[Jarvis] gateway action failed", action, e);
  }
  setTimeout(refreshStatus, 500);
}

// ---------------- 高危动作确认（占位实现） ----------------
//
// 说明：当前版本尚未接入真实的高危动作拦截。
// 后续由 background 在执行高危动作前向 popup 发起确认请求，
// 用户点击「允许/拒绝」后再继续或中止。

function showConfirm(desc) {
  els.confirmDesc.textContent =
    desc || "Agent 请求执行可能造成不可逆后果的操作。";
  els.confirmBox.classList.add("show");
}

function hideConfirm() {
  els.confirmBox.classList.remove("show");
}

els.connectBtn.addEventListener("click", connect);
els.confirmYes.addEventListener("click", () => hideConfirm());
els.confirmNo.addEventListener("click", () => hideConfirm());
els.clearLogBtn.addEventListener("click", () => {
  if (els.logBox) els.logBox.innerHTML = "";
});

// 网关列表按钮事件（事件委托）
els.gwList.addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-action]");
  if (!btn) return;
  gatewayAction(btn.dataset.action, btn.dataset.gateway);
});

// 监听 background 广播的状态变化
chrome.runtime.onMessage.addListener((message) => {
  if (message && message.type === "jarvis_state") {
    log("收到状态广播");
    renderGateways(message.gateways);
  }
  if (message && message.type === "jarvis_confirm") {
    showConfirm(message.description);
  }
  return false;
});

// 初始化
log("popup 已打开，开始查询状态");
refreshStatus();
