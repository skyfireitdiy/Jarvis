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
  // 从context中解构依赖
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
  const socket = ref(null); // Gateway连接
  const sockets = ref(new Map()); // 多Agent连接存储：agent_id -> WebSocket
  const connecting = ref(false);
  const agentConnecting = ref(false); // Agent连接状态（独立于主网关连接状态）
  const connectErrorMessage = ref(""); // 连接错误信息

  // WebSocket重连相关状态
  const reconnecting = ref(false); // 是否正在重连
  const reconnectAttempts = ref(0); // 当前重连尝试次数
  const reconnectTimer = ref(null); // 重连定时器
  const reconnectInterval = 5000; // 固定重连间隔（毫秒）
  const userDisconnected = ref(false); // 用户主动断开连接标志

  // 心跳机制相关状态
  const heartbeatTimer = ref(null); // 心跳定时器
  const lastPongTime = ref(null); // 最后一次收到pong的时间
  const heartbeatInterval = 30000; // 心跳间隔（毫秒）
  const pongTimeout = 10000; // pong超时时间（毫秒）

  /**
   * 启动心跳机制
   */
  function startHeartbeat() {
    stopHeartbeat(); // 先停止现有心跳
    
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
      return;
    }

    console.log("[ws] Starting heartbeat mechanism");
    lastPongTime.value = Date.now();

    heartbeatTimer.value = setInterval(() => {
      if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
        stopHeartbeat();
        return;
      }

      // 检查是否超时
      const now = Date.now();
      if (lastPongTime.value && (now - lastPongTime.value) > pongTimeout) {
        console.warn("[ws] Heartbeat timeout, closing connection");
        socket.value.close();
        return;
      }

      // 发送ping消息
      try {
        const pingMessage = {
          type: "ping",
          timestamp: now,
        };
        socket.value.send(JSON.stringify(pingMessage));
        console.log("[ws] Sent ping message");
      } catch (error) {
        console.error("[ws] Failed to send ping:", error);
      }
    }, heartbeatInterval);
  }

  /**
   * 停止心跳机制
   */
  function stopHeartbeat() {
    if (heartbeatTimer.value) {
      clearInterval(heartbeatTimer.value);
      heartbeatTimer.value = null;
    }
    lastPongTime.value = null;
  }

  /**
   * 处理pong消息
   */
  function handlePongMessage(message) {
    if (message.type === "pong") {
      lastPongTime.value = Date.now();
      console.log("[ws] Received pong message");
    }
  }

  /**
   * 处理WebSocket消息
   */
  function handleWebSocketMessage(event) {
    let message = null;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      console.warn("[ws] message parse failed", event.data);
      return;
    }
    
    console.log("[ws] message", message);
    
    // 处理pong消息
    if (message.type === "pong") {
      handlePongMessage(message);
      return;
    }
    
    // 处理其他消息
    if (handleMessage) {
      handleMessage(message);
    }
  }

  /**
   * 处理WebSocket连接关闭
   */
  function handleWebSocketClose(event) {
    console.log("[ws] close", {
      code: event?.code,
      reason: event?.reason,
      wasClean: event?.wasClean,
      readyState: socket.value?.readyState,
    });
    
    socket.value = null;
    connecting.value = false;
    stopHeartbeat(); // 停止心跳

    // 判断是否需要自动重连（token存在时才重连）
    const shouldReconnect =
      !userDisconnected.value && !isAutoConnecting?.value && hasAuthToken?.();

    if (shouldReconnect) {
      // 启动自动重连（固定间隔，无上限）
      reconnecting.value = true;
      reconnectAttempts.value++;

      console.log(
        `[ws] Connection closed, attempting to reconnect (attempt ${reconnectAttempts.value}) in ${reconnectInterval}ms`,
      );

      // 设置重连定时器（固定5秒间隔）
      reconnectTimer.value = setTimeout(() => {
        console.log(
          `[ws] Reconnecting... attempt ${reconnectAttempts.value}`,
        );
        connect();
      }, reconnectInterval);
    } else {
      // 不需要重连
      reconnecting.value = false;

      if (isAutoConnecting?.value) {
        // 自动连接阶段失败，显示登录弹窗
        console.log("[ws] Auto connection failed, showing login modal");
        isAutoConnecting.value = false;
        if (showConnectModal) showConnectModal.value = true;
        // 清除失效的token
        localStorage.removeItem("jarvis_auth_token");
        connectErrorMessage.value = "自动登录失败，请重新登录";
      } else if (userDisconnected.value) {
        // 用户主动断开，不重连
        console.log("[ws] User disconnected, not reconnecting");
        userDisconnected.value = false; // 重置标志
      }
    }
    // 不清空连接错误信息，保留错误提示
  }

  /**
   * 连接到Gateway（无参数接口）
   */
  async function connect() {
    console.log("[ws] connect() called", {
      hasSocket: !!socket.value,
      socketState: socket.value?.readyState,
      connecting: connecting.value,
      gatewayUrl: gatewayUrl?.value,
    });

    // 清空之前的错误信息
    connectErrorMessage.value = "";
    if (socket.value) return;

    // 解析网关地址
    const gatewayUrlValue = gatewayUrl?.value || "";
    const parsed = parseGatewayAddress(gatewayUrlValue);
    if (!parsed) {
      connectErrorMessage.value = "无效的网关地址格式";
      return;
    }

    // 如果已有token（从localStorage加载的），跳过密码登录
    if (hasAuthToken && !hasAuthToken()) {
      try {
        if (loginWithPassword) {
          await loginWithPassword();
        }
      } catch (error) {
        connectErrorMessage.value = error.message || "登录失败";
        return;
      }
    } else {
      console.log("[AUTH] Using existing token, skipping password login");
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
    console.log("[ws] new WebSocket created", {
      url,
      readyState: ws.readyState,
    });

    ws.onopen = () => {
      console.log("[ws] open", { url, readyState: ws.readyState });
      connecting.value = false;
      socket.value = ws;
      if (showConnectModal) showConnectModal.value = false;

      // 重置重连状态
      reconnecting.value = false;
      reconnectAttempts.value = 0;
      userDisconnected.value = false;
      if (reconnectTimer.value) {
        clearTimeout(reconnectTimer.value);
        reconnectTimer.value = null;
      }
      console.log("[ws] Reconnect state reset");

      // 保存连接信息到localStorage
      localStorage.setItem("jarvis_gateway_url", gatewayUrlValue);
      console.log("[ws] Connection info saved:", gatewayUrlValue);

      if (startAgentListRefresh) startAgentListRefresh();
      // 获取模型组列表
      if (fetchModelGroups) fetchModelGroups();
      if (fetchNodeStatus) fetchNodeStatus();

      const currentOutputs = allOutputs?.value?.get(currentAgentId?.value) || [];
      if (currentOutputs.length === 0) {
        console.log("[HISTORY] Loading history on first connect");
        if (loadHistoryMessages) loadHistoryMessages(false);
      } else {
        console.log("[HISTORY] Skip loading history, messages already exist");
      }

      // 发送连接锁定设置
      if (connectionLockEnabled) {
        ws.send(
          JSON.stringify({
            type: "connection_lock",
            payload: { enabled: connectionLockEnabled.value },
          }),
        );
        console.log("[ws] connection_lock sent", connectionLockEnabled.value);
      }

      // 启动心跳机制
      startHeartbeat();
    };

    ws.onmessage = handleWebSocketMessage;

    ws.onclose = handleWebSocketClose;

    ws.onerror = (event) => {
      console.error("[ws] error", {
        event,
        readyState: ws.readyState,
        currentSocketMatched: socket.value === ws,
      });
      connecting.value = false;
    };
  }

  /**
   * 断开连接（无参数接口）
   */
  function disconnect() {
    // 设置用户主动断开标志，防止自动重连
    userDisconnected.value = true;

    // 清理重连定时器
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value);
      reconnectTimer.value = null;
    }
    reconnecting.value = false;
    reconnectAttempts.value = 0;

    // 停止心跳
    stopHeartbeat();

    if (socket.value) {
      socket.value.close();
    }
  }

  /**
   * 重新连接（无参数接口）
   */
  function reconnect() {
    // 断开现有连接
    if (socket.value) {
      socket.value.close();
    }
    // 重新连接
    connect();
  }

  /**
   * 断开所有连接（无参数接口）
   */
  function disconnectAll() {
    if (
      !confirm(
        "确定要断开与网关的连接吗？这将清除所有认证信息并断开所有Agent连接。",
      )
    ) {
      return;
    }
    console.log("[WS] Disconnecting all WebSocket connections");

    // 关闭设置弹窗
    if (showSettingsModal) {
      showSettingsModal.value = false;
    }

    // 关闭所有Agent WebSocket连接
    sockets.value.forEach((ws, agentId) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.log(`[WS] Closing WebSocket connection for agent ${agentId}`);
        ws.close();
      }
    });
    sockets.value.clear();

    // 关闭主Gateway连接
    if (socket.value) {
      console.log("[WS] Closing main Gateway WebSocket connection");
      socket.value.close();
      socket.value = null;
    }

    // 停止心跳
    stopHeartbeat();

    // 清空连接状态
    if (currentAgentId) {
      currentAgentId.value = null;
    }
    if (agentList) {
      agentList.value = [];
    }
    if (agentStatuses) {
      agentStatuses.value.clear();
    }

    // 清除保存的token和免登录状态
    localStorage.removeItem("jarvis_auth_token");
    localStorage.removeItem("jarvis_auto_login");
    console.log("[WS] Cleared saved token and auto login setting");

    // 强制刷新页面确保状态重置
    console.log("[WS] Forcing page refresh after disconnection");
    setTimeout(() => {
      window.location.reload();
    }, 500);
  }

  return {
    // 状态
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
    // 心跳相关状态
    heartbeatTimer,
    lastPongTime,
    heartbeatInterval,
    pongTimeout,

    // 方法
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
    // 心跳相关方法
    startHeartbeat,
    stopHeartbeat,
    handlePongMessage,
  };
}