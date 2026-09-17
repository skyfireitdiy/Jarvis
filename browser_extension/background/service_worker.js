// Background service worker：连接管理 + 指令分发入口（支持多网关）。
//
// 职责：
// 1. 从 chrome.storage 读取已配置的网关列表，为每个网关建立独立 WebSocket 连接
// 2. 连接后发送 hello（扩展版本、浏览器信息、标签页快照）
// 3. 收到 command 后交给 CommandRouter 执行，并回传 result
// 4. 向 popup 广播各网关的连接状态
//
// Token 来源：通过 chrome.scripting.executeScript({ world: "MAIN" }) 在页面主世界
// 读取 Jarvis 网页暴露的 window.__jarvisAuthBridge（getToken / getGateway），
// 从而复用浏览器登录态自动连接网关，无需用户手填 Token。
// 注意：不可用 content script 注入 inline script 的方式桥接主世界，MV3 下会被页面 CSP 拦截。
//
// 多网关说明：同一浏览器可同时连接多个 Jarvis 网关，各自独立连接、独立会话、独立 Token。
// 注意：所有网关共享同一批浏览器标签页（浏览器扩展架构的固有特性）。

import { WsClient } from "./ws_client.js";
import { CommandRouter } from "./command_router.js";

// 扩展版本：从 manifest 动态读取，避免与 manifest.json 中的版本号漂移
const EXTENSION_VERSION = chrome.runtime.getManifest().version;

const router = new CommandRouter();

// 按网关索引的状态（key 为规范化后的网关地址，如 http://127.0.0.1:8000）
const clients = new Map(); // gateway -> WsClient
const tokens = new Map(); // gateway -> token
const sessions = new Map(); // gateway -> session_id
const states = new Map(); // gateway -> 'disconnected' | 'connecting' | 'connected'
// gatewayKey -> 连续鉴权失败次数，用于避免无效重连空转（连接成功后清零）
const authErrorAttempts = new Map();

// 鉴权失败后最多自动重试次数：超过则停止重连，提示用户重新登录
const AUTH_ERROR_MAX_RETRIES = 3;

// 扩展有新版本时的通知 ID（同一 ID 重复创建会自动替换，避免堆叠）
const UPDATE_NOTIFICATION_ID = "jarvis-extension-update";

// chrome.storage.local 中记录「已提示过的新版本号」的键。
// 同一版本只提示一次，避免每次重连/唤醒都弹通知。
const NOTIFIED_VERSION_KEY = "notified_extension_version";

/** 读取已配置的网关列表。 */
async function loadGateways() {
  const cfg = await chrome.storage.local.get(["gateways"]);
  const list = cfg.gateways;
  return Array.isArray(list) ? list : [];
}

/** 保存网关列表。 */
async function saveGateways(list) {
  await chrome.storage.local.set({ gateways: list });
}

/** 规范化网关地址：去掉尾部斜杠。 */
function normalizeGateway(gateway) {
  if (!gateway) return "";
  let g = String(gateway).trim();
  if (!g) return "";
  if (!/^https?:\/\//i.test(g)) {
    g = "http://" + g;
  }
  return g.replace(/\/+$/, "");
}

/** 收集 hello 帧所需的浏览器信息。 */
async function buildHello() {
  const tabs = await chrome.tabs.query({});
  return {
    type: "hello",
    client_id: await getClientId(),
    extension_version: EXTENSION_VERSION,
    browser_info: {
      user_agent: navigator.userAgent,
      platform: navigator.platform,
    },
    tabs: tabs.map((t) => ({
      tab_id: t.id,
      url: t.url,
      title: t.title,
      active: t.active,
      window_id: t.windowId,
    })),
  };
}

/** 稳定的客户端 ID（首次生成后持久化）。 */
async function getClientId() {
  const cfg = await chrome.storage.local.get(["client_id"]);
  if (cfg.client_id) return cfg.client_id;
  const id =
    "ext-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  await chrome.storage.local.set({ client_id: id });
  return id;
}

/** 广播状态给 popup（popup 可能未打开，忽略失败）。 */
function broadcastState() {
  chrome.runtime
    .sendMessage({ type: "jarvis_state", gateways: listStatus() })
    .catch(() => {
      // popup 未打开时会报错，忽略
    });
}

/**
 * 根据连接状态切换扩展工具栏图标。
 *
 * - 任一网关处于 connected：使用原色图标（青色高亮，表示在线）
 * - 否则（无网关 / 全部断开或连接中）：使用灰暗图标（表示离线）
 *
 * setIcon 在 service worker 被回收后不会自动恢复，因此每次状态变化都重新设置；
 * 失败时仅告警，不影响连接逻辑。
 */
function updateActionIcon() {
  const connected = Array.from(states.values()).some((s) => s === "connected");
  const suffix = connected ? "" : "_off";
  const path = {
    16: `icons/icon16${suffix}.png`,
    32: `icons/icon32${suffix}.png`,
    48: `icons/icon48${suffix}.png`,
    128: `icons/icon128${suffix}.png`,
  };
  const title = connected
    ? "Jarvis Browser Bridge（已连接）"
    : "Jarvis Browser Bridge（未连接）";
  try {
    chrome.action
      .setIcon({ path })
      .catch((e) => console.warn("[Jarvis] setIcon failed", e));
    chrome.action.setTitle({ title }).catch(() => {});
  } catch (e) {
    console.warn("[Jarvis] updateActionIcon error", e);
  }
}

/** 汇总所有网关的状态。 */
function listStatus() {
  const all = new Set([...clients.keys(), ...states.keys()]);
  return Array.from(all).map((gateway) => ({
    gateway,
    state: states.get(gateway) || "disconnected",
    session_id: sessions.get(gateway) || null,
    has_token: Boolean(tokens.get(gatewayKey(gateway))),
  }));
}

/**
 * 比对网关打包版本与本地版本，落后时弹系统通知提示用户升级。
 *
 * 同一新版本只提示一次（记录在 chrome.storage.local），避免每次重连或
 * service worker 唤醒都重复弹出。通知创建失败（如用户关闭了通知权限）时
 * 仅告警，不影响连接流程。
 *
 * @param {string} gateway 网关地址，用于通知文案定位
 * @param {string} latest 网关打包的扩展最新版本
 */
async function maybeNotifyUpdate(gateway, latest) {
  const latestVersion = String(latest || "").trim();
  if (!latestVersion) return;
  if (latestVersion === String(EXTENSION_VERSION).trim()) return;

  let notified = null;
  try {
    const cfg = await chrome.storage.local.get([NOTIFIED_VERSION_KEY]);
    notified = cfg[NOTIFIED_VERSION_KEY] || null;
  } catch (e) {
    console.warn("[Jarvis] read notified version failed", e);
  }
  if (notified === latestVersion) return;

  try {
    await chrome.notifications.create(UPDATE_NOTIFICATION_ID, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Jarvis 浏览器插件有新版本",
      message:
        `当前 v${EXTENSION_VERSION} → 最新 v${latestVersion}。` +
        `请打开 Jarvis 网页，在「安装浏览器插件」中重新下载并重新加载扩展。`,
      priority: 1,
    });
  } catch (e) {
    console.warn("[Jarvis] create update notification failed", e);
    return;
  }
  console.log("[Jarvis] update notification shown", gateway, latestVersion);

  // 记录已提示版本，避免重复打扰；写入失败不影响主流程
  try {
    await chrome.storage.local.set({ [NOTIFIED_VERSION_KEY]: latestVersion });
  } catch (e) {
    console.warn("[Jarvis] save notified version failed", e);
  }
}

/** 处理某个网关下发的消息。 */
async function handleMessage(gateway, msg) {
  if (!msg || typeof msg !== "object") return;
  switch (msg.type) {
    case "hello_ack":
      sessions.set(gateway, msg.session_id || null);
      console.log("[Jarvis] hello_ack", gateway, "session_id=", msg.session_id);
      // 握手成功说明 Token 有效，清零鉴权失败计数
      authErrorAttempts.delete(gatewayKey(gateway));
      setState(gateway, "connected");
      // 网关随握手下发最新版本：无需打开 Jarvis 网页也能发现新版本
      maybeNotifyUpdate(gateway, msg.latest_extension_version).catch((e) =>
        console.warn("[Jarvis] maybeNotifyUpdate error", e),
      );
      break;
    case "command": {
      const result = await router.handle(msg);
      const client = clients.get(gateway);
      const ok = client && client.send(result);
      if (!ok) {
        console.warn(
          "[Jarvis] failed to send result (disconnected)",
          gateway,
          result.id,
        );
      }
      break;
    }
    case "error":
      console.warn("[Jarvis] gateway error", gateway, msg.payload);
      break;
    default:
      console.log("[Jarvis] unknown message", gateway, msg.type);
  }
}

/**
 * 更新某网关状态并广播。
 *
 * 状态未变化时直接返回：MV3 的 service worker 每次被唤醒都会重跑模块顶层代码
 * （含 connectAll），会为每个网关新建 WsClient 并重新走 connecting → connected
 * → hello_ack，若不去重则每次唤醒都向 popup 连发多次广播，形成广播风暴。
 */
function setState(gateway, state) {
  if (states.get(gateway) === state) return;
  states.set(gateway, state);
  updateActionIcon();
  broadcastState();
}

/**
 * 处理网关鉴权失败（WebSocket 以 4401/4403 关闭）。
 *
 * 典型场景：网关重启后 JWT 签名密钥变更（未设置 JARVIS_JWT_SECRET 时每次启动随机生成），
 * 浏览器页面 localStorage 里缓存的旧 Token 随即失效；若继续用旧 Token 重连，
 * 会陷入「断开—重连」无限循环。
 *
 * 处理策略：清空该网关的 Token 缓存，重新从页面探测一次（用户若已重新登录可拿到新
 * Token）；探测成功则重连，失败则停止自动重连并提示用户重新登录，避免空转。
 */
async function handleAuthError(gateway, code, reason) {
  const g = normalizeGateway(gateway);
  const tokenKey = gatewayKey(g);
  console.warn(
    "[Jarvis] auth error, clearing cached token",
    g,
    "code=",
    code,
    "reason=",
    reason,
  );
  tokens.delete(tokenKey);
  // 丢弃持有失效 Token 的旧连接，避免后续 connect 复用到它
  const stale = clients.get(g);
  if (stale) {
    clients.delete(g);
    stale.close();
  }
  sessions.delete(g);
  setState(g, "disconnected");

  // 连续鉴权失败计数：页面里的 Token 可能同样是失效的（用户尚未重新登录），
  // 此时重新探测会拿到同一个旧 Token，必须限制重试次数，否则仍会形成循环。
  const attempts = (authErrorAttempts.get(tokenKey) || 0) + 1;
  authErrorAttempts.set(tokenKey, attempts);
  if (attempts > AUTH_ERROR_MAX_RETRIES) {
    console.warn(
      "[Jarvis] auth failed repeatedly, stop reconnecting. " +
        "请在浏览器中重新登录该网关的 Jarvis 页面后，再点击「连接」。",
      g,
    );
    broadcastState();
    return;
  }

  let token = null;
  try {
    token = await refreshTokenFromPages(g);
  } catch (e) {
    console.warn("[Jarvis] token re-probe failed", g, e);
  }
  if (!token) {
    console.warn(
      "[Jarvis] no valid token after auth error, stop reconnecting:",
      g,
    );
    broadcastState();
    return;
  }
  console.log(
    "[Jarvis] reconnecting with refreshed token for",
    g,
    `(attempt ${attempts}/${AUTH_ERROR_MAX_RETRIES})`,
  );
  try {
    await connect(g, true);
  } catch (e) {
    console.warn("[Jarvis] reconnect after auth error failed", g, e);
  }
}

/**
 * 为指定网关建立连接。
 *
 * @param {string} gateway 网关地址
 * @param {boolean} force 为 true 时强制重建连接（用户显式点击「连接」用于重试）；
 *   为 false 时若已有处于 connecting/connected 的连接则直接复用，
 *   避免 service worker 被唤醒重跑 connectAll 时把健康连接掐断重建。
 */
async function connect(gateway, force = false) {
  const g = normalizeGateway(gateway);
  if (!g) {
    console.warn("[Jarvis] empty gateway, skip connect");
    return;
  }
  if (!force) {
    const current = clients.get(g);
    if (current && current.isAlive()) {
      console.log("[Jarvis] connect: reuse existing connection for", g);
      return;
    }
  } else {
    // 用户显式发起的连接（force=true）：重置鉴权失败计数，允许重新尝试
    authErrorAttempts.delete(gatewayKey(g));
  }
  // Token 优先使用当前登录态；若尚未获取，则主动向页面请求一次
  const tokenKey = gatewayKey(g);
  let token = tokens.get(tokenKey);
  if (!token) {
    console.log("[Jarvis] connect: no cached token, probing pages for", g);
    token = await requestTokenFromPages(g);
    console.log("[Jarvis] connect: probe done, has_token=", Boolean(token));
    if (token) {
      tokens.set(tokenKey, token);
    }
  }
  if (!token) {
    console.warn(
      "[Jarvis] no auth token yet for",
      g,
      ", waiting for Jarvis page",
    );
    setState(g, "disconnected");
    throw new Error(
      `未获取到 ${g} 的登录态 Token。请先在浏览器中打开并登录该网关的 Jarvis 页面，再重试。`,
    );
  }

  const existing = clients.get(g);
  if (existing) {
    existing.close();
  }

  const client = new WsClient({
    onMessage: (msg) => handleMessage(g, msg),
    onStateChange: (state) => setState(g, state),
    onAuthError: (code, reason) => handleAuthError(g, code, reason),
  });
  client.onOpen = async () => {
    try {
      const hello = await buildHello();
      client.send(hello);
    } catch (e) {
      console.error("[Jarvis] send hello failed", g, e);
    }
  };
  clients.set(g, client);
  client.connect(g, token);
}

/**
 * 断开指定网关连接。
 *
 * 断开后立即清空该网关的 Token 缓存，避免下次连接复用可能已失效的旧 Token；
 * 随后异步从页面重新探测一次登录态，探测到则写回缓存，供下次 connect 直接使用
 * （探测结果不触发连接，用户点「连接」时才真正建立 WebSocket）。
 *
 * @param {string} gateway 网关地址
 * @param {boolean} skipProbe 为 true 时不重新探测 Token（用于移除网关等场景）
 */
function disconnect(gateway, skipProbe = false) {
  const g = normalizeGateway(gateway);
  const client = clients.get(g);
  if (client) {
    client.close();
    clients.delete(g);
  }
  sessions.delete(g);
  const tokenKey = gatewayKey(g);
  // 清空 Token 缓存，避免复用失效 Token
  tokens.delete(tokenKey);
  // 主动断开视为用户意图，重置鉴权失败计数
  authErrorAttempts.delete(tokenKey);
  setState(g, "disconnected");
  if (skipProbe) return;
  // 异步重新探测页面登录态，不阻塞断开流程
  refreshTokenFromPages(g).catch((e) =>
    console.warn("[Jarvis] refresh token after disconnect failed", g, e),
  );
}

/**
 * 从页面重新探测 Token 并写回缓存（不建立连接）。
 * 探测不到时不写入，保持缓存为空，由后续 connect 决定如何提示。
 */
async function refreshTokenFromPages(gateway) {
  const g = normalizeGateway(gateway);
  if (!g) return null;
  let token = null;
  try {
    token = await requestTokenFromPages(g);
  } catch (e) {
    console.warn("[Jarvis] token probe failed", g, e);
    return null;
  }
  if (token) {
    tokens.set(gatewayKey(g), token);
    console.log("[Jarvis] token refreshed from page for", g);
  } else {
    console.log("[Jarvis] no token available from page for", g);
  }
  return token;
}

/**
 * 归一化为 host:port 用于比对。
 * 前端页面声明的网关与用户填写的网关可能在协议上不一致
 * （如页面写 http://host:443、用户写 https://host:443），
 * 比对时忽略协议差异，只比较 host 与端口。
 */
function gatewayKey(gateway) {
  const g = normalizeGateway(gateway);
  if (!g) return "";
  try {
    const url = new URL(g);
    const port = url.port || (url.protocol === "https:" ? "443" : "80");
    return `${url.hostname}:${port}`;
  } catch (e) {
    return g;
  }
}

/**
 * 在标签页主世界读取 __jarvisAuthBridge 暴露的 Token 与网关地址。
 * 必须通过 chrome.scripting.executeScript({ world: "MAIN" }) 注入：
 * MV3 中隔离世界（content script）动态插入的 inline script 不会在主世界执行。
 * 该函数会被序列化后注入，禁止引用外部变量。
 * @returns {{token: string|null, gateway: string|null}|null}
 */
function readAuthBridgeInMainWorld() {
  try {
    const bridge = window.__jarvisAuthBridge;
    if (!bridge) return null;
    const token =
      typeof bridge.getToken === "function" ? bridge.getToken() || null : null;
    let gateway = null;
    if (typeof bridge.getGateway === "function") {
      gateway = bridge.getGateway() || null;
    }
    return { token, gateway: gateway || location.origin };
  } catch (e) {
    return null;
  }
}

/**
 * 主动向已打开的 Jarvis 页面读取指定网关的登录态 Token。
 * 通过主世界注入读取页面暴露的 __jarvisAuthBridge，
 * 其中 gateway 由页面通过 __jarvisAuthBridge.getGateway() 声明（网关与前端可不同域名）。
 */
async function requestTokenFromPages(gateway) {
  const g = normalizeGateway(gateway);
  const gKey = gatewayKey(g);
  try {
    const tabs = await chrome.tabs.query({});
    console.log("[Jarvis] token probe start, tabs=", tabs.length);
    for (const tab of tabs) {
      if (!tab.id || !/^https?:/i.test(tab.url || "")) continue;
      try {
        const results = await withTimeout(
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: readAuthBridgeInMainWorld,
            world: "MAIN",
          }),
          3000,
          `executeScript timeout: ${tab.url}`,
        );
        const resp = results && results[0] ? results[0].result : null;
        if (!resp) continue;
        console.log(
          "[Jarvis] token probe",
          tab.url,
          "gateway=",
          resp.gateway,
          "has_token=",
          Boolean(resp.token),
        );
        if (!resp.token) continue;
        // 只接受声明网关与目标网关一致的响应（忽略协议差异）
        if (gatewayKey(resp.gateway) === gKey) {
          return resp.token;
        }
      } catch (e) {
        // 该标签页无法注入（受限页面等），跳过
        console.log(
          "[Jarvis] token probe skipped",
          tab.url,
          "reason=",
          (e && e.message) || String(e),
        );
      }
    }
  } catch (e) {
    console.warn("[Jarvis] requestTokenFromPages failed", g, e);
  }
  return null;
}

/** 为 Promise 添加超时保护，避免个别标签页注入挂起拖垮整体流程。 */
function withTimeout(promise, ms, message) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

/** 添加网关到配置列表（去重）。 */
async function addGateway(gateway) {
  const g = normalizeGateway(gateway);
  if (!g) return;
  const list = await loadGateways();
  const normalized = list.map(normalizeGateway);
  if (!normalized.includes(g)) {
    list.push(g);
    await saveGateways(list);
  }
}

// ---------------- 与 popup 的交互 ----------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) return false;

  if (message.type === "jarvis_connect") {
    const gateway = message.gateway;
    if (!gateway) {
      sendResponse({ success: false, error: "gateway is required" });
      return true;
    }
    addGateway(gateway)
      .then(() => connect(gateway, true))
      .then(() => sendResponse({ success: true }))
      .catch((e) =>
        sendResponse({ success: false, error: (e && e.message) || String(e) }),
      );
    return true; // 异步响应
  }
  if (message.type === "jarvis_disconnect") {
    if (message.gateway) {
      disconnect(message.gateway);
    } else {
      // 未指定则断开全部
      for (const g of Array.from(clients.keys())) {
        disconnect(g);
      }
    }
    sendResponse({ success: true });
    return true;
  }
  if (message.type === "jarvis_get_status") {
    sendResponse({ success: true, gateways: listStatus() });
    return true;
  }
  if (message.type === "jarvis_remove_gateway") {
    const g = normalizeGateway(message.gateway);
    // 网关已被移除，无需再探测 Token
    disconnect(g, true);
    // disconnect 会重新写入 states，需在其后再清理，避免残留幽灵条目
    clients.delete(g);
    sessions.delete(g);
    tokens.delete(gatewayKey(g));
    states.delete(g);
    loadGateways()
      .then((list) =>
        saveGateways(list.filter((x) => normalizeGateway(x) !== g)),
      )
      .then(() => {
        broadcastState();
        sendResponse({ success: true });
      })
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  // ---------------- 脚本管理（类油猴） ----------------
  // popup 通过以下 message 管理已安装脚本，统一转发给 CommandRouter 的 script.* 路由。
  if (message.type === "jarvis_script_list") {
    router
      .handle({ id: "popup", action: "script.list", params: {} })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  if (message.type === "jarvis_script_get") {
    router
      .handle({ id: "popup", action: "script.get", params: { id: message.id } })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  if (message.type === "jarvis_script_install") {
    router
      .handle({
        id: "popup",
        action: "script.install",
        params: {
          name: message.name,
          source: message.source,
          description: message.description,
          match: message.match,
          version: message.version,
        },
      })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  // 从 URL 下载并安装脚本（source 由 background 侧 fetch，popup 不接触源码）
  if (message.type === "jarvis_script_install_from_url") {
    router
      .handle({
        id: "popup",
        action: "script.install_from_url",
        params: {
          url: message.url,
          name: message.name,
          description: message.description,
          match: message.match,
          version: message.version,
        },
      })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  if (message.type === "jarvis_script_uninstall") {
    router
      .handle({
        id: "popup",
        action: "script.uninstall",
        params: { id: message.id },
      })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  if (message.type === "jarvis_script_export") {
    router
      .handle({
        id: "popup",
        action: "script.export",
        params: { id: message.id },
      })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  if (message.type === "jarvis_script_set_enabled") {
    router
      .handle({
        id: "popup",
        action: "script.set_enabled",
        params: { id: message.id, enabled: message.enabled },
      })
      .then(sendResponse)
      .catch((e) => sendResponse({ success: false, error: String(e) }));
    return true;
  }
  // content script 注入上报（诊断用）
  if (message.type === "jarvis_cs_loaded") {
    console.log("[Jarvis] content script loaded:", message.url);
    return false;
  }
  return false;
});

/** 冷启动：为所有已配置网关建立连接。 */
async function connectAll() {
  const list = await loadGateways();
  for (const gateway of list) {
    await connect(gateway);
  }
}

// 扩展安装/启动时自动连接
chrome.runtime.onStartup.addListener(() => {
  connectAll();
});

chrome.runtime.onInstalled.addListener(() => {
  connectAll();
});

// service worker 冷启动时也尝试连接
updateActionIcon(); // 冷启动先把图标置为离线态，连接成功后再由 setState 切换
connectAll();
