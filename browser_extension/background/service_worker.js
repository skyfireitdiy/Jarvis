// Background service worker：连接管理 + 指令分发入口（支持多网关）。
//
// 职责：
// 1. 从 chrome.storage 读取已配置的网关列表，为每个网关建立独立 WebSocket 连接
// 2. 连接后发送 hello（扩展版本、浏览器信息、标签页快照）
// 3. 收到 command 后交给 CommandRouter 执行，并回传 result
// 4. 向 popup 广播各网关的连接状态
//
// Token 来源：content script 桥接 Jarvis 网页暴露的登录态，
// 通过 jarvis_ext_token / jarvis_ext_token_changed 消息推送至此（携带来源网关地址）。
//
// 多网关说明：同一浏览器可同时连接多个 Jarvis 网关，各自独立连接、独立会话、独立 Token。
// 注意：所有网关共享同一批浏览器标签页（浏览器扩展架构的固有特性）。

import { WsClient } from "./ws_client.js";
import { CommandRouter } from "./command_router.js";

const EXTENSION_VERSION = "0.1.0";

const router = new CommandRouter();

// 按网关索引的状态（key 为规范化后的网关地址，如 http://127.0.0.1:8000）
const clients = new Map(); // gateway -> WsClient
const tokens = new Map(); // gateway -> token
const sessions = new Map(); // gateway -> session_id
const states = new Map(); // gateway -> 'disconnected' | 'connecting' | 'connected'

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

/** 处理某个网关下发的消息。 */
async function handleMessage(gateway, msg) {
  if (!msg || typeof msg !== "object") return;
  switch (msg.type) {
    case "hello_ack":
      sessions.set(gateway, msg.session_id || null);
      console.log("[Jarvis] hello_ack", gateway, "session_id=", msg.session_id);
      setState(gateway, "connected");
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

/** 更新某网关状态并广播。 */
function setState(gateway, state) {
  states.set(gateway, state);
  broadcastState();
}

/** 为指定网关建立连接（若已连接则先关闭）。 */
async function connect(gateway) {
  const g = normalizeGateway(gateway);
  if (!g) {
    console.warn("[Jarvis] empty gateway, skip connect");
    return;
  }
  // Token 优先使用当前登录态；若尚未获取，则主动向页面请求一次
  const tokenKey = gatewayKey(g);
  let token = tokens.get(tokenKey);
  if (!token) {
    token = await requestTokenFromPages(g);
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

/** 断开指定网关连接。 */
function disconnect(gateway) {
  const g = normalizeGateway(gateway);
  const client = clients.get(g);
  if (client) {
    client.close();
    clients.delete(g);
  }
  sessions.delete(g);
  setState(g, "disconnected");
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
 * 主动向已打开的 Jarvis 页面请求指定网关的登录态 Token。
 * content script 收到请求后会读取页面暴露的 __jarvisAuthBridge 并回传，
 * 其中 gateway 由页面通过 __jarvisAuthBridge.getGateway() 声明（网关与前端可不同域名）。
 */
async function requestTokenFromPages(gateway) {
  const g = normalizeGateway(gateway);
  const gKey = gatewayKey(g);
  try {
    const tabs = await chrome.tabs.query({});
    for (const tab of tabs) {
      if (!tab.id) continue;
      try {
        const resp = await chrome.tabs.sendMessage(tab.id, {
          type: "jarvis_request_token",
        });
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
        // 该标签页无 content script（非 Jarvis 页面），跳过
      }
    }
  } catch (e) {
    console.warn("[Jarvis] requestTokenFromPages failed", g, e);
  }
  return null;
}

/**
 * 处理来自 content script 的登录态 Token（按网关独立处理）。
 * Token 变化时重连该网关；Token 为空（未登录/已登出）时断开该网关。
 * 注意：token 以 host:port 为键存储，避免前端声明与用户填写在协议上的差异
 * （如 http://host:443 与 https://host:443）导致取不到 token。
 */
async function handleAuthToken(gateway, token) {
  const g = normalizeGateway(gateway);
  if (!g) {
    console.warn("[Jarvis] auth token without gateway, ignored");
    return;
  }
  const key = gatewayKey(g);
  const next = token || null;
  if (next === (tokens.get(key) || null)) {
    return; // 无变化
  }
  if (next) {
    tokens.set(key, next);
  } else {
    tokens.delete(key);
  }

  if (!next) {
    console.log("[Jarvis] auth token cleared, disconnecting", g);
    disconnect(g);
    return;
  }
  console.log("[Jarvis] auth token updated, reconnecting", g);
  await connect(g);
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
      .then(() => connect(gateway))
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
    disconnect(g);
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
  // 来自 content script 的登录态 Token（首次获取或发生变化）
  if (
    message.type === "jarvis_ext_token" ||
    message.type === "jarvis_ext_token_changed"
  ) {
    handleAuthToken(message.gateway, message.token).catch((e) => {
      console.error("[Jarvis] handleAuthToken failed", e);
    });
    sendResponse({ success: true });
    return true;
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
connectAll();
