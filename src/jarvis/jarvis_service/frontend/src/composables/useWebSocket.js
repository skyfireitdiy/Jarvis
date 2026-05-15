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