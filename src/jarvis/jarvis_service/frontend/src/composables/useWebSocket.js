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