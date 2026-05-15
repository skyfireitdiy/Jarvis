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
 * 负责WebSocket连接、重连、消息处理等功能
 */
export function useWebSocket() {
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

  // 连接到Gateway
  async function connect(options = {}) {
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
    } = options;

    console.log("[ws] connect() called", {
      hasSocket: !!socket.value,
      socketState: socket.value?.readyState,
      connecting: connecting.value,
      gatewayUrl: gatewayUrl,
    });

    // 清空之前的错误信息
    connectErrorMessage.value = "";
    if (socket.value) return;

    // 解析网关地址
    const parsed = parseGatewayAddress(gatewayUrl);
    if (!parsed) {
      connectErrorMessage.value = "无效的网关地址格式";
      return;
    }

    // 如果已有token（从localStorage加载的），跳过密码登录
    if (!hasAuthToken()) {
      try {
        await loginWithPassword();
      } catch (error) {
        connectErrorMessage.value = error.message || "登录失败";
        return;
      }
    } else {
      console.log("[AUTH] Using existing token, skipping password login");
    }

    if (!hasAuthToken()) {
      connectErrorMessage.value = "登录失败，请重试";
      return;
    }

    const host = parsed.host || window.location.hostname || "127.0.0.1";
    const port = parsed.port || "8000";
    const url = buildWebSocketUrl(host, port, parsed.protocol);
    connecting.value = true;

    const ws = new WebSocket(url, buildWebSocketProtocols(authToken));
    console.log("[ws] new WebSocket created", {
      url,
      readyState: ws.readyState,
    });

    ws.onopen = () => {
      console.log("[ws] open", { url, readyState: ws.readyState });
      connecting.value = false;
      socket.value = ws;
      showConnectModal.value = false;

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
      localStorage.setItem("jarvis_gateway_url", gatewayUrl);
      console.log("[ws] Connection info saved:", gatewayUrl);

      startAgentListRefresh();
      // 获取模型组列表
      fetchModelGroups();
      fetchNodeStatus();

      const currentOutputs = allOutputs.value.get(currentAgentId.value) || [];
      if (currentOutputs.length === 0) {
        console.log("[HISTORY] Loading history on first connect");
        loadHistoryMessages(false);
      } else {
        console.log("[HISTORY] Skip loading history, messages already exist");
      }

      // 发送连接锁定设置
      ws.send(
        JSON.stringify({
          type: "connection_lock",
          payload: { enabled: connectionLockEnabled.value },
        }),
      );
      console.log("[ws] connection_lock sent", connectionLockEnabled.value);
    };

    ws.onmessage = (event) => {
      let message = null;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        console.warn("[ws] message parse failed", event.data);
        return;
      }
      console.log("[ws] message", message);
      handleMessage(message);
    };

    ws.onclose = (event) => {
      console.log("[ws] close", {
        code: event?.code,
        reason: event?.reason,
        wasClean: event?.wasClean,
        readyState: ws.readyState,
        currentSocketMatched: socket.value === ws,
      });
      socket.value = null;
      connecting.value = false;

      // 判断是否需要自动重连（token存在时才重连）
      const shouldReconnect =
        !userDisconnected.value && !isAutoConnecting.value && hasAuthToken();

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
          connect(options);
        }, reconnectInterval);
      } else {
        // 不需要重连
        reconnecting.value = false;

        if (isAutoConnecting.value) {
          // 自动连接阶段失败，显示登录弹窗
          console.log("[ws] Auto connection failed, showing login modal");
          isAutoConnecting.value = false;
          showConnectModal.value = true;
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
    };

    ws.onerror = (event) => {
      console.error("[ws] error", {
        event,
        readyState: ws.readyState,
        currentSocketMatched: socket.value === ws,
      });
      connecting.value = false;
    };
  }

  // 断开连接
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

    if (socket.value) {
      socket.value.close();
    }
  }

  // 重新连接
  function reconnect(options) {
    // 断开现有连接
    if (socket.value) {
      socket.value.close();
    }
    // 重新连接
    connect(options);
  }

  // 断开所有连接
  function disconnectAll(options = {}) {
    const { showSettingsModal, currentAgentId, agentList, agentStatuses } =
      options;

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
  };
}
