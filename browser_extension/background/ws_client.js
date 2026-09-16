// WebSocket 连接管理：连接网关、心跳、指数退避重连。
//
// 连接 URL：{gateway}/api/browser-ext/ws
// 鉴权：子协议 ['jarvis-ext', 'jarvis-token.<urlencoded-token>']

const HEARTBEAT_INTERVAL_MS = 20000; // 20s 发送一次 ping
const RECONNECT_BASE_MS = 1000; // 首次重连 1s
const RECONNECT_MAX_MS = 30000; // 上限 30s

export class WsClient {
  /**
   * @param {object} opts
   * @param {(msg: object) => void} opts.onMessage 收到消息回调
   * @param {(state: string) => void} opts.onStateChange 连接状态变化回调
   */
  constructor({ onMessage, onStateChange }) {
    this.onMessage = onMessage;
    this.onStateChange = onStateChange;
    this.ws = null;
    this.state = "disconnected"; // disconnected | connecting | connected
    this.reconnectAttempts = 0;
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    this.manualClose = false;
  }

  setState(state) {
    if (this.state === state) return;
    this.state = state;
    try {
      this.onStateChange?.(state);
    } catch (e) {
      console.warn("[Jarvis] onStateChange error", e);
    }
  }

  /**
   * 建立连接。
   * @param {string} gateway 网关地址，如 https://jvs-ai.cn 或 http://127.0.0.1:8000
   * @param {string} token 网关 token
   */
  connect(gateway, token) {
    this.manualClose = false;
    this.gateway = normalizeGateway(gateway);
    this.token = token;
    this._open();
  }

  _open() {
    if (!this.gateway) {
      console.warn("[Jarvis] gateway not configured");
      return;
    }
    this._clearReconnect();
    this.setState("connecting");

    const wsUrl = toWsUrl(this.gateway) + "/api/browser-ext/ws";
    const protocols = ["jarvis-ext"];
    if (this.token) {
      protocols.push("jarvis-token." + encodeURIComponent(this.token));
    }

    let ws;
    try {
      ws = new WebSocket(wsUrl, protocols);
    } catch (e) {
      console.error("[Jarvis] WebSocket construct failed", e);
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      console.log("[Jarvis] ws connected");
      this.reconnectAttempts = 0;
      this.setState("connected");
      this._startHeartbeat();
      // 由上层（service_worker）在 open 后发送 hello
      try {
        this.onOpen?.();
      } catch (e) {
        console.warn("[Jarvis] onOpen error", e);
      }
    };

    ws.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (e) {
        console.warn("[Jarvis] invalid json from gateway", event.data);
        return;
      }
      if (msg && msg.type === "pong") {
        return; // 心跳响应，无需上报
      }
      try {
        this.onMessage?.(msg);
      } catch (e) {
        console.error("[Jarvis] onMessage error", e);
      }
    };

    ws.onclose = (event) => {
      console.log("[Jarvis] ws closed", event.code, event.reason);
      this._stopHeartbeat();
      this.setState("disconnected");
      if (!this.manualClose) {
        this._scheduleReconnect();
      }
    };

    ws.onerror = (event) => {
      console.warn("[Jarvis] ws error", event);
      // onclose 会随后触发，重连逻辑在那里处理
    };
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ type: "ping" }));
        } catch (e) {
          console.warn("[Jarvis] ping failed", e);
        }
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  _scheduleReconnect() {
    this._clearReconnect();
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, this.reconnectAttempts),
      RECONNECT_MAX_MS,
    );
    this.reconnectAttempts += 1;
    console.log(
      `[Jarvis] reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`,
    );
    this.reconnectTimer = setTimeout(() => {
      this._open();
    }, delay);
  }

  _clearReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  /** 发送消息；未连接时返回 false（断线期间不缓存指令）。 */
  send(obj) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    try {
      this.ws.send(JSON.stringify(obj));
      return true;
    } catch (e) {
      console.warn("[Jarvis] send failed", e);
      return false;
    }
  }

  /** 主动断开（不再自动重连）。 */
  close() {
    this.manualClose = true;
    this._clearReconnect();
    this._stopHeartbeat();
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {
        // ignore
      }
    }
    this.ws = null;
    this.setState("disconnected");
  }

  get isConnected() {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

/** 规范化网关地址：去掉尾部斜杠。 */
export function normalizeGateway(gateway) {
  if (!gateway) return "";
  let g = String(gateway).trim();
  if (!g) return "";
  if (!/^https?:\/\//i.test(g)) {
    // 默认补 https
    g = "https://" + g;
  }
  return g.replace(/\/+$/, "");
}

/** http(s) -> ws(s)。 */
export function toWsUrl(gateway) {
  return gateway.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:");
}
