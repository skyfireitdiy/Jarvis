import { ref } from "vue";
import {
  getWebSocketProtocol,
  parseGatewayAddress,
  buildNodeWebSocketUrl,
  buildWebSocketUrl,
  buildAgentWebSocketUrl,
  buildWebSocketProtocols,
  getGatewayAddress,
} from "./useWebSocketUrls";
import { connectToAgent } from "./useAgentConnection";

/**
 * WebSocket连接管理Composable
 * 负责WebSocket连接、重连、消息处理、心跳机制等功能
 * @param {Object} context - 依赖上下文
 */
export function useWebSocket(context = {}) {
  const {
    gatewayUrl,
    authToken,
    hasAuthToken,
    loginWithPassword,
    connectionLockEnabled,
    showConnectModal,
    startAgentListRefresh,
    fetchModelGroups,
    fetchNodeStatus,
    loadHistoryMessages,
    allOutputs,
    currentAgentId,
    isAutoConnecting,
    handleMessage,
    showSettingsModal,
    agentList,
    agentStatuses,
  } = context;

  // WebSocket连接状态
  const socket = ref(null);
  const sockets = ref(new Map());
  const connecting = ref(false);
  const agentConnecting = ref(false);
  const connectErrorMessage = ref("");

  // 重连相关状态
  const reconnecting = ref(false);
  const reconnectAttempts = ref(0);
  const reconnectTimer = ref(null);
  const reconnectInterval = 5000;
  const userDisconnected = ref(false);

  // 心跳机制相关状态
  const heartbeatTimer = ref(null);
  const lastPongTime = ref(null);
  const heartbeatInterval = 30000;
  const pongTimeout = 10000;

  // 启动心跳机制
  function startHeartbeat() {
    stopHeartbeat();
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return;
    lastPongTime.value = Date.now();
    heartbeatTimer.value = setInterval(() => {
      if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
        stopHeartbeat();
        return;
      }
      const now = Date.now();
      if (lastPongTime.value && now - lastPongTime.value > pongTimeout) {
        socket.value.close();
        return;
      }
      try {
        socket.value.send(JSON.stringify({ type: "ping", timestamp: now }));
      } catch (error) {
        console.error("[ws] Failed to send ping:", error);
      }
    }, heartbeatInterval);
  }

  // 停止心跳机制
  function stopHeartbeat() {
    if (heartbeatTimer.value) {
      clearInterval(heartbeatTimer.value);
      heartbeatTimer.value = null;
    }
    lastPongTime.value = null;
  }

  // 处理pong消息
  function handlePongMessage(message) {
    if (message.type === "pong") {
      lastPongTime.value = Date.now();
    }
  }

  // 处理WebSocket消息
  function handleWebSocketMessage(event) {
    let message = null;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      console.warn("[ws] message parse failed", event.data);
      return;
    }
    if (message.type === "pong") {
      handlePongMessage(message);
      return;
    }
    if (handleMessage) handleMessage(message);
  }

  // 处理WebSocket连接关闭
  function handleWebSocketClose(event) {
    socket.value = null;
    connecting.value = false;
    stopHeartbeat();
    const shouldReconnect =
      !userDisconnected.value && !isAutoConnecting?.value && hasAuthToken?.();
    if (shouldReconnect) {
      reconnecting.value = true;
      reconnectAttempts.value++;
      reconnectTimer.value = setTimeout(() => connect(), reconnectInterval);
    } else {
      reconnecting.value = false;
      if (isAutoConnecting?.value) {
        isAutoConnecting.value = false;
        if (showConnectModal) showConnectModal.value = true;
        localStorage.removeItem("jarvis_auth_token");
        connectErrorMessage.value = "自动登录失败，请重新登录";
      } else if (userDisconnected.value) {
        userDisconnected.value = false;
      }
    }
  }

  // 连接到Gateway（无参数接口）
  async function connect() {
    connectErrorMessage.value = "";
    if (socket.value) return;
    const gatewayUrlValue = gatewayUrl?.value || "";
    const parsed = parseGatewayAddress(gatewayUrlValue);
    if (!parsed) {
      connectErrorMessage.value = "无效的网关地址格式";
      return;
    }
    if (hasAuthToken && !hasAuthToken()) {
      try {
        if (loginWithPassword) await loginWithPassword();
      } catch (error) {
        connectErrorMessage.value = error.message || "登录失败";
        return;
      }
    }
    if (hasAuthToken && !hasAuthToken()) {
      connectErrorMessage.value = "登录失败，请重试";
      return;
    }
    const host = parsed.host || window.location.hostname || "127.0.0.1";
    const port = parsed.port || "8000";
    const url = buildWebSocketUrl(host, port, parsed.protocol);
    connecting.value = true;
    const authTokenValue = authToken?.value || "";
    const ws = new WebSocket(url, buildWebSocketProtocols(authTokenValue));
    ws.onopen = () => {
      connecting.value = false;
      socket.value = ws;
      if (showConnectModal) showConnectModal.value = false;
      reconnecting.value = false;
      reconnectAttempts.value = 0;
      userDisconnected.value = false;
      if (reconnectTimer.value) {
        clearTimeout(reconnectTimer.value);
        reconnectTimer.value = null;
      }
      localStorage.setItem("jarvis_gateway_url", gatewayUrlValue);
      if (startAgentListRefresh) startAgentListRefresh();
      if (fetchModelGroups) fetchModelGroups();
      if (fetchNodeStatus) fetchNodeStatus();
      const currentOutputs =
        allOutputs?.value?.get(currentAgentId?.value) || [];
      if (currentOutputs.length === 0 && loadHistoryMessages) {
        loadHistoryMessages(false);
      }
      if (connectionLockEnabled) {
        ws.send(
          JSON.stringify({
            type: "connection_lock",
            payload: { enabled: connectionLockEnabled.value },
          }),
        );
      }
      startHeartbeat();
    };
    ws.onmessage = handleWebSocketMessage;
    ws.onclose = handleWebSocketClose;
    ws.onerror = () => {
      connecting.value = false;
    };
  }

  // 断开连接（无参数接口）
  function disconnect() {
    userDisconnected.value = true;
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value);
      reconnectTimer.value = null;
    }
    reconnecting.value = false;
    reconnectAttempts.value = 0;
    stopHeartbeat();
    if (socket.value) socket.value.close();
  }

  // 重新连接（无参数接口）
  function reconnect() {
    if (socket.value) socket.value.close();
    connect();
  }

  // 断开所有连接（无参数接口）
  function disconnectAll() {
    if (
      !confirm(
        "确定要断开与网关的连接吗？这将清除所有认证信息并断开所有Agent连接。",
      )
    )
      return;
    if (showSettingsModal) showSettingsModal.value = false;
    sockets.value.forEach((ws) => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    });
    sockets.value.clear();
    if (socket.value) {
      socket.value.close();
      socket.value = null;
    }
    stopHeartbeat();
    if (currentAgentId) currentAgentId.value = null;
    if (agentList) agentList.value = [];
    if (agentStatuses) agentStatuses.value.clear();
    localStorage.removeItem("jarvis_auth_token");
    localStorage.removeItem("jarvis_auto_login");
    setTimeout(() => window.location.reload(), 500);
  }

  return {
    socket,
    sockets,
    connecting,
    agentConnecting,
    connectErrorMessage,
    reconnecting,
    reconnectAttempts,
    reconnectTimer,
    reconnectInterval,
    userDisconnected,
    heartbeatTimer,
    lastPongTime,
    heartbeatInterval,
    pongTimeout,
    getWebSocketProtocol,
    parseGatewayAddress,
    buildNodeWebSocketUrl,
    buildWebSocketUrl,
    buildAgentWebSocketUrl,
    buildWebSocketProtocols,
    getGatewayAddress,
    connect,
    disconnect,
    reconnect,
    disconnectAll,
    connectToAgent,
    startHeartbeat,
    stopHeartbeat,
    handlePongMessage,
  };
}
