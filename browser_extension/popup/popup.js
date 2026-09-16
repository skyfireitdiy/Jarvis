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
  // 脚本管理（类油猴）
  scriptName: document.getElementById("scriptName"),
  scriptSource: document.getElementById("scriptSource"),
  scriptFile: document.getElementById("scriptFile"),
  scriptInstallBtn: document.getElementById("scriptInstallBtn"),
  scriptList: document.getElementById("scriptList"),
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

// ---------------- 脚本管理（类油猴） ----------------
//
// 与 background 的约定：发送 { type: "jarvis_script_*", ... }，
// 收到结果信封 { success, data, error }，其中 data 即 ScriptManager 的返回值。

/** 渲染已安装脚本列表。 */
function renderScripts(list) {
  const items = Array.isArray(list) ? list : [];
  if (items.length === 0) {
    els.scriptList.innerHTML =
      '<div class="hint">尚未安装任何脚本。可粘贴脚本源码后点击「安装脚本」。</div>';
    return;
  }

  els.scriptList.innerHTML = items
    .map((s) => {
      const enabled = s.enabled !== false;
      const stateClass = enabled ? "connected" : "disconnected";
      const stateText = enabled ? "已启用" : "已停用";
      const safeName = escapeHtml(s.name || "");
      const safeId = escapeHtml(s.id || "");
      const safeVersion = escapeHtml(s.version || "0.0.0");
      const safeDesc = escapeHtml(s.description || "");
      const matchText =
        Array.isArray(s.match) && s.match.length
          ? escapeHtml(s.match.join(", "))
          : "";
      const sizeText =
        typeof s.source_size === "number" ? `${s.source_size} 字节` : "";
      const metaParts = [safeVersion, stateText];
      if (matchText) metaParts.push(matchText);
      if (sizeText) metaParts.push(sizeText);
      return `
        <div class="gw-item">
          <div class="gw-head">
            <span class="dot ${stateClass}"></span>
            <span class="gw-url">${safeName}</span>
          </div>
          <div class="gw-meta hint">${metaParts.join(" · ")}</div>
          ${safeDesc ? `<div class="gw-meta hint">${safeDesc}</div>` : ""}
          <div class="gw-actions">
            <button class="mini" data-script-action="${
              enabled ? "disable" : "enable"
            }" data-script-id="${safeId}">${enabled ? "停用" : "启用"}</button>
            <button class="mini secondary" data-script-action="view" data-script-id="${safeId}">查看源码</button>
            <button class="mini secondary" data-script-action="uninstall" data-script-id="${safeId}">卸载</button>
          </div>
        </div>
      `;
    })
    .join("");
}

/** 查询 background 已安装脚本并渲染。 */
async function refreshScripts() {
  try {
    const resp = await chrome.runtime.sendMessage({
      type: "jarvis_script_list",
    });
    if (resp && resp.success) {
      renderScripts(resp.data);
      const list = Array.isArray(resp.data) ? resp.data : [];
      log(`脚本列表已刷新：${list.length} 个`);
    } else {
      log(`脚本列表刷新失败：${(resp && resp.error) || "background 无响应"}`);
      renderScripts([]);
    }
  } catch (e) {
    log(`脚本列表刷新异常：${(e && e.message) || String(e)}`);
    renderScripts([]);
  }
}

/** 安装脚本（从输入框 / 已选择的文件内容）。 */
async function installScript() {
  const name = els.scriptName.value.trim();
  const source = els.scriptSource.value;
  if (!name) {
    alert("请填写脚本名称");
    return;
  }
  if (!source || !source.trim()) {
    alert("请粘贴脚本源码或选择本地 .js 文件");
    return;
  }
  log(`请求安装脚本：${name}`);
  try {
    const resp = await chrome.runtime.sendMessage({
      type: "jarvis_script_install",
      name,
      source,
      description: "",
      match: [],
      version: "1.0.0",
    });
    if (resp && resp.success) {
      log(`脚本安装成功：${name}`);
      els.scriptName.value = "";
      els.scriptSource.value = "";
      els.scriptFile.value = "";
    } else {
      const err = (resp && resp.error) || "未知错误";
      log(`脚本安装失败：${err}`);
      alert("安装失败：" + err);
    }
  } catch (e) {
    log(`脚本安装异常：${(e && e.message) || String(e)}`);
  }
  refreshScripts();
}

/** 对指定脚本执行操作：enable / disable / view / uninstall。 */
async function scriptAction(action, id) {
  try {
    if (action === "enable" || action === "disable") {
      const resp = await chrome.runtime.sendMessage({
        type: "jarvis_script_set_enabled",
        id,
        enabled: action === "enable",
      });
      if (resp && resp.success) {
        log(`脚本已${action === "enable" ? "启用" : "停用"}：${id}`);
      } else {
        log(`脚本启停失败：${(resp && resp.error) || "未知错误"}`);
      }
    } else if (action === "view") {
      const resp = await chrome.runtime.sendMessage({
        type: "jarvis_script_get",
        id,
      });
      if (resp && resp.success && resp.data) {
        els.scriptSource.value = resp.data.source || "";
        els.scriptName.value = resp.data.name || "";
        log(`已载入脚本源码：${resp.data.name || id}`);
      } else {
        log(`读取脚本源码失败：${(resp && resp.error) || "未知错误"}`);
      }
      return; // 查看源码不需刷新列表
    } else if (action === "uninstall") {
      const resp = await chrome.runtime.sendMessage({
        type: "jarvis_script_uninstall",
        id,
      });
      if (resp && resp.success) {
        log(`脚本已卸载：${id}`);
      } else {
        log(`脚本卸载失败：${(resp && resp.error) || "未知错误"}`);
      }
    }
  } catch (e) {
    log(`脚本操作异常：${(e && e.message) || String(e)}`);
  }
  refreshScripts();
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

// 脚本管理：安装按钮
els.scriptInstallBtn.addEventListener("click", installScript);

// 脚本管理：选择本地 .js 文件后把内容填入源码框
els.scriptFile.addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    els.scriptSource.value = String(reader.result || "");
    if (!els.scriptName.value.trim()) {
      // 未填名称时，用文件名（去掉扩展名）作为默认脚本名
      els.scriptName.value = file.name.replace(/\.js$/i, "");
    }
    log(`已读取本地脚本文件：${file.name}`);
  };
  reader.onerror = () => log(`读取本地脚本文件失败：${file.name}`);
  reader.readAsText(file);
});

// 脚本列表按钮事件（事件委托）
els.scriptList.addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-script-action]");
  if (!btn) return;
  scriptAction(btn.dataset.scriptAction, btn.dataset.scriptId);
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
refreshScripts();
