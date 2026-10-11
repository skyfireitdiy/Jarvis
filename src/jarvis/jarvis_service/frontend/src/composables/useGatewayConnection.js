// 网关连接 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 7），保持行为完全一致：
// - 核心状态：gatewayUrl / socket / sockets / lastPongTime / HEARTBEAT_INTERVAL / HEARTBEAT_TIMEOUT /
//   connecting / agentConnecting / connectingAgents / connectErrorMessage / isRestartingGateway /
//   restartNodeId / restartFrontendService / reconnecting / reconnectAttempts / reconnectTimer /
//   reconnectInterval / userDisconnected / isAutoConnecting
// - 状态派生：connectionStatus / connectionLabel
// - 主网关连接：connect / disconnect / reconnect / disconnectAll
// - 网关重启：handleRestartGateway / confirmRestartGateway / restartGateway
// - Agent 连接：connectToAgent / autoConnectToOnlineAgents
// - 心跳：checkHeartbeatTimeout / sendHeartbeat / heartbeatTimer
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - 状态：auth / username / myClientId / terminalSessions / allOutputs / currentAgentId / agentList /
//   agentStatuses / showConnectModal / showSettingsModal / autoLoginEnabled / userAccessibleNodes /
//   gitCustomDir / agentMap
// - 函数：parseGatewayAddress / buildWebSocketUrl / buildWebSocketProtocols / buildAgentWebSocketUrl /
//   getGatewayAddress / buildNodeHttpUrl / fetchWithAuth / loginWithPassword / hasAuthToken /
//   startAgentListRefresh / startNodeStatusRefresh / restoreVirtualWorkspaceDirs / loadGitCustomDir /
//   refreshUserInfo / fetchUserPermissions / fetchModelGroups / fetchNodeStatus / fetchUserAccessibleNodes /
//   restoreTerminalSessions / getOrCreateClientId / sendChatMessageToServer / loadHistoryMessages /
//   closeTerminal / handleMessage / getAgentLastSeq / showToast / showConfirm
import { computed, ref } from 'vue'

export function useGatewayConnection({
  socket,
  sockets,
  auth,
  username,
  myClientId,
  terminalSessions,
  allOutputs,
  currentAgentId,
  agentList,
  agentStatuses,
  showConnectModal,
  showSettingsModal,
  autoLoginEnabled,
  userAccessibleNodes,
  gitCustomDir,
  parseGatewayAddress,
  buildWebSocketUrl,
  buildWebSocketProtocols,
  buildAgentWebSocketUrl,
  getGatewayAddress,
  buildNodeHttpUrl,
  fetchWithAuth,
  loginWithPassword,
  hasAuthToken,
  startAgentListRefresh,
  startNodeStatusRefresh,
  restoreVirtualWorkspaceDirs,
  loadGitCustomDir,
  refreshUserInfo,
  fetchUserPermissions,
  fetchModelGroups,
  fetchNodeStatus,
  fetchUserAccessibleNodes,
  restoreTerminalSessions,
  getOrCreateClientId,
  sendChatMessageToServer,
  loadHistoryMessages,
  closeTerminal,
  handleMessage,
  getAgentLastSeq,
  showToast,
  showConfirm,
}) {
// 默认网关地址：协议跟随当前页面（https → wss），域名为当前前端域名，端口固定 8000
function buildDefaultGatewayUrl() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${wsProtocol}://${window.location.hostname}:8000`
}
const gatewayUrl = ref(localStorage.getItem('jarvis_gateway_url') || buildDefaultGatewayUrl())

// Agent 心跳检测相关状态
const lastPongTime = ref(new Map()) // agentId -> 最后收到 pong 的时间戳
const HEARTBEAT_INTERVAL = 5000 // 心跳间隔：5 秒发送一次 ping
const HEARTBEAT_TIMEOUT = 15000 // 心跳超时时间：15 秒（3 次）未收到 pong 就重连
const connecting = ref(false)
const agentConnecting = ref(false) // Agent 连接状态（独立于主网关连接状态）
const connectingAgents = ref(new Set()) // Agent 连接锁：防止同一 agent 并发重连建多连接
const connectErrorMessage = ref('')  // 连接错误信息
const isRestartingGateway = ref(false)
const restartNodeId = ref('') // 重启服务时选择的节点ID
const restartFrontendService = ref(false) // 是否同时重启前端服务

// WebSocket重连相关状态
const reconnecting = ref(false) // 是否正在重连
const reconnectAttempts = ref(0) // 当前重连尝试次数
const reconnectTimer = ref(null) // 重连定时器
const reconnectInterval = 5000 // 固定重连间隔（毫秒）
const userDisconnected = ref(false) // 用户主动断开连接标志
const isAutoConnecting = ref(false) // 自动连接（免登录）阶段标志

// 连接状态派生
const connectionStatus = computed(() => {
  if (connecting.value) return 'connecting'
  if (reconnecting.value) return 'reconnecting'
  return socket.value ? 'online' : 'offline'
})

const connectionLabel = computed(() => {
  if (connecting.value) return '连接中'
  if (reconnecting.value) return '重连中'
  return socket.value ? '已连接' : '未连接'
})

// 连接到 Gateway
async function connect() {
  // 清空之前的错误信息
  connectErrorMessage.value = ''
  if (socket.value) return
  
  // 解析网关地址
  const parsed = parseGatewayAddress(gatewayUrl.value)
  if (!parsed) {
    connectErrorMessage.value = '无效的网关地址格式'
    return
  }
  
  const password = String(auth.value.password || '').trim()

  // 如果已有 token（从 localStorage 加载的），跳过密码登录
  if (!hasAuthToken()) {
    try {
      await loginWithPassword(password)
    } catch (error) {
      connectErrorMessage.value = error.message || '登录失败'
      return
    }
  } else {
  }
  
  if (!hasAuthToken()) {
    connectErrorMessage.value = '登录失败，请重试'
    return
  }
  
  const host = parsed.host || window.location.hostname || '127.0.0.1'
  const port = parsed.port || '8000'
  const url = buildWebSocketUrl(host, port, parsed.protocol)
  connecting.value = true
  const ws = new WebSocket(url, buildWebSocketProtocols())
  ws.onopen = () => {
    connecting.value = false
    socket.value = ws
    showConnectModal.value = false
    
    // 重置重连状态
    reconnecting.value = false
    reconnectAttempts.value = 0
    userDisconnected.value = false
    isAutoConnecting.value = false  // 连接成功，自动连接阶段结束
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }

    // 保存连接信息到 localStorage
    localStorage.setItem('jarvis_gateway_url', gatewayUrl.value)
    startAgentListRefresh()
    startNodeStatusRefresh()
    // 恢复上次「打开目录」的虚拟目录记录（鉴权已可用）
    restoreVirtualWorkspaceDirs()
    // 恢复 Git 面板上次指定的自定义 Git 管理目录
    gitCustomDir.value = loadGitCustomDir()
    // 刷新用户信息（确保display_name等字段最新），随后拉取权限（依赖 userInfo.user_id）
    refreshUserInfo().finally(() => { fetchUserPermissions() })
    // 登录成功后自动连接所有在线的 agent
    autoConnectToOnlineAgents()
    // 获取模型组列表
    fetchModelGroups()
    fetchNodeStatus()
    fetchUserAccessibleNodes()
    // 恢复当前用户的存活终端会话（方案A：断开不杀进程 + 输出缓冲回放）
    restoreTerminalSessions()
    // 自动注册聊天室（避免丢消息，不依赖用户手动打开聊天面板）
    if (!myClientId.value) {
      myClientId.value = getOrCreateClientId()
    }
    sendChatMessageToServer('chat_register', { client_id: myClientId.value, name: username.value })
    const currentOutputs = allOutputs.value.get(currentAgentId.value) || []
    if (currentOutputs.length === 0) {
      loadHistoryMessages(false)
    } else {
    }
    // 心跳机制已移除
  }
  ws.onmessage = (event) => {
    // 忽略非当前连接的消息（重连时旧连接可能仍收到消息）
    if (socket.value !== ws) {
      return
    }
    let message = null
    try {
      message = JSON.parse(event.data)
    } catch (error) {
      console.warn('[ws] message parse failed', event.data)
      return
    }

    // pong 消息处理已移除

    handleMessage(message)
  }
  ws.onclose = (event) => {
    socket.value = null
    connecting.value = false
    // 连接断开，销毁所有独立终端
    const allTerminalIds = terminalSessions.value.map(t => t.terminal_id)
    allTerminalIds.forEach(terminalId => closeTerminal(terminalId))
    
    // 判断是否需要自动重连（token存在时才重连）
    const shouldReconnect = !userDisconnected.value && !isAutoConnecting.value && hasAuthToken()

    if (shouldReconnect) {
      // 启动自动重连（固定间隔，无上限）
      reconnecting.value = true
      reconnectAttempts.value++


      // 设置重连定时器（固定5秒间隔）
      reconnectTimer.value = setTimeout(() => {
        connect()
      }, reconnectInterval)
    } else {
      // 不需要重连
      reconnecting.value = false

      if (isAutoConnecting.value) {
        // 自动连接阶段失败，显示登录弹窗
        isAutoConnecting.value = false
        showConnectModal.value = true
        // 清除失效的 token
        localStorage.removeItem('jarvis_auth_token')
        auth.value.token = ''
        connectErrorMessage.value = '自动登录失败，请重新登录'
      } else if (userDisconnected.value) {
        // 用户主动断开，不重连
        userDisconnected.value = false // 重置标志
      }
    }
    // 不清空连接错误信息，保留错误提示
  }
  ws.onerror = (event) => {
    console.error('[ws] error', {
      event,
      readyState: ws.readyState,
      currentSocketMatched: socket.value === ws,
    })
    connecting.value = false
  }
}

function disconnect() {
  // 设置用户主动断开标志，防止自动重连
  userDisconnected.value = true
  
  // 清理重连定时器
  if (reconnectTimer.value) {
    clearTimeout(reconnectTimer.value)
    reconnectTimer.value = null
  }
  reconnecting.value = false
  reconnectAttempts.value = 0
  
  if (socket.value) {
    socket.value.close()
  }
}

// 处理 SettingsModal 组件的重启事件
function handleRestartGateway({ nodeId, restartFrontend }) {
  restartNodeId.value = nodeId || ''
  restartFrontendService.value = restartFrontend || false
  confirmRestartGateway()
}

function confirmRestartGateway() {
  if (isRestartingGateway.value) {
    return
  }

  const targetNodeId = restartNodeId.value

  const confirmMessage = targetNodeId
    ? `确认重启节点 "${targetNodeId}" 的服务吗？这将短暂中断该节点的连接。`
    : '确认重启本节点服务吗？这将短暂中断当前连接。'
  showConfirm(
    confirmMessage,
    () => {
      restartGateway()
    },
    () => {},
    false
  )
}

async function restartGateway() {
  if (isRestartingGateway.value) {
    return
  }

  const targetNodeId = restartNodeId.value || 'master'
  
  try {
    isRestartingGateway.value = true
    const { host, port } = getGatewayAddress()
    
    // 发送重启请求，等待响应结果
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'service/restart'), {
      method: 'POST',
      body: JSON.stringify({
        node_id: targetNodeId,
        restart_frontend: restartFrontendService.value
      })
    })

    // 检查响应状态
    if (response.ok) {
      const data = await response.json().catch(() => ({}))
      if (data.success === false) {
        showToast(data.error?.message || '重启请求失败', 'error')
      } else {
        showToast(data.data?.message || `已向节点 "${targetNodeId}" 发送重启请求`, 'success')
      }
    } else {
      showToast(`重启请求失败: HTTP ${response.status}`, 'error')
    }
  } catch (error) {
    console.error('[SETTINGS] Failed to restart gateway:', error)
    showToast(error.message || '重启服务失败', 'error')
  } finally {
    // 延迟重置状态，防止用户重复点击
    setTimeout(() => {
      isRestartingGateway.value = false
    }, 3000)
  }
}

function reconnect() {
  // 断开现有连接
  if (socket.value) {
    socket.value.close()
  }
  // 关闭设置弹窗
  showSettingsModal.value = false
  // 重新连接
  connect()
}

function disconnectAll() {
  if (!confirm('确定要断开与网关的连接吗？这将清除所有认证信息并断开所有Agent连接。')) {
    return
  }
  
  // 关闭设置弹窗
  showSettingsModal.value = false
  
  // 关闭所有Agent WebSocket连接
  sockets.value.forEach((ws, agentId) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close()
    }
  })
  sockets.value.clear()
  
  // 关闭主Gateway连接
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
  
  // 清空连接状态
  currentAgentId.value = null
  agentList.value = []
  agentStatuses.value.clear()
  
  // 清除保存的 token 和免登录状态
  localStorage.removeItem('jarvis_auth_token')
  localStorage.removeItem('jarvis_auto_login')
  auth.value.token = ''
  userAccessibleNodes.value = null
  autoLoginEnabled.value = false
  // 强制刷新页面确保状态重置
  setTimeout(() => {
    window.location.reload()
  }, 500)
}

// 连接到指定的 Agent（建立独立的 WebSocket 连接）
async function connectToAgent(agent, retryCount = 0) {
  const agentId = agent.agent_id
  const maxRetries = 12  // 最多重试12次
  const retryDelay = 2000 // 2秒重试间隔
  const connectionTimeout = 10000 // 10秒连接超时（适应Agent启动时间）
  
  // 连接锁检查：防止同一 agent 并发重连建多连接
  if (connectingAgents.value.has(agentId)) {
    return Promise.resolve(null)
  }

  // 检查是否已有连接
  if (sockets.value.has(agentId)) {
    const existingWs = sockets.value.get(agentId)
    // 检查现有连接是否仍然有效
    if (existingWs && existingWs.readyState === WebSocket.OPEN) {
      // 已连接，发送 get_status 请求以同步当前状态
      existingWs.send(JSON.stringify({ type: 'get_status', payload: {} }))
      return Promise.resolve(existingWs)
    }
    // 连接已断开或正在关闭，确保完全关闭后再清理
    
    // 等待旧连接完全关闭（避免与后端连接冲突）
    if (existingWs && existingWs.readyState !== WebSocket.CLOSED) {
      existingWs.close()
      // 等待最多 1 秒让连接完全关闭
      await new Promise((resolve) => {
        if (existingWs.readyState === WebSocket.CLOSED) {
          resolve()
          return
        }
        const checkInterval = setInterval(() => {
          if (existingWs.readyState === WebSocket.CLOSED) {
            clearInterval(checkInterval)
            resolve()
          }
        }, 50)
        // 最多等待 1 秒
        setTimeout(() => {
          clearInterval(checkInterval)
          resolve()
        }, 1000)
      })
    }
    
    // 清理旧连接
    sockets.value.delete(agentId)
  }
  

  // 加连接锁
  connectingAgents.value.add(agentId)

  const { host, port } = getGatewayAddress()
  const url = buildAgentWebSocketUrl(host, agentId, null, port, String(agent?.node_id || 'master').trim())

  agentConnecting.value = true
  
  // 返回 Promise，等待连接真正建立
  return new Promise((resolve, reject) => {
    try {
      const ws = new WebSocket(url, buildWebSocketProtocols())
      let connectionHandled = false // 防止重复处理连接结果
      
      // 设置连接超时
      const timeoutId = setTimeout(() => {
        if (connectionHandled) return
        connectionHandled = true

        console.error(`[AGENT ${agentId}] Connection timeout after ${connectionTimeout}ms`)
        ws.close()
        sockets.value.delete(agentId)
        connectingAgents.value.delete(agentId) // 释放连接锁
        if (agentConnecting.value) agentConnecting.value = false

        // 只通知超时，不重连
        // 重连由switchAgent的稳定性循环统一管理
        reject(new Error(`Connection timeout after ${connectionTimeout}ms`))
      }, connectionTimeout)
      
      // 绑定消息处理
      ws.onmessage = (event) => {
        let message = null
        try {
          message = JSON.parse(event.data)
        } catch (error) {
          console.warn(`[AGENT ${agentId}] message parse failed`, event.data)
          return
        }
        
        // 处理 pong 响应（心跳机制）
        if (message.type === 'pong' || (message.success && message.pong)) {
          lastPongTime.value.set(agentId, Date.now())
          return // pong 消息不需要继续处理
        }
        
        handleMessage(message, agentId)
      }
      
      ws.onopen = () => {
        if (connectionHandled) {
          return
        }
        connectionHandled = true

        clearTimeout(timeoutId)
        connectingAgents.value.delete(agentId) // 释放连接锁
        agentConnecting.value = false

        // 保存连接
        sockets.value.set(agentId, ws)

        // 初始化消息记录
        if (!allOutputs.value.has(agentId)) {
          allOutputs.value.set(agentId, [])
        }

        // 发送该 Agent 的增量同步请求
        const lastSeq = getAgentLastSeq(agentId)
        const agent_seqs = { [agentId]: lastSeq }
        ws.send(JSON.stringify({
          type: 'sync_request',
          payload: { agent_seqs }
        }))

        // 标记连接已完成（在onclose中用于判断是否需要重试）
        ws._connectionCompleted = true

        // Agent 心跳机制已移除

        // 连接成功，resolve Promise
        resolve(ws)
      }

      
      ws.onclose = (event) => {
        // 心跳定时器清理代码已移除

        // 已建立的连接断开（connectionHandled=true 且 _connectionCompleted=true）
        // 需要触发重连，而不是忽略
        if (connectionHandled && !ws._connectionCompleted) {
          return
        }

        if (!connectionHandled) {
          connectionHandled = true
          clearTimeout(timeoutId)
        }

        sockets.value.delete(agentId)
        connectingAgents.value.delete(agentId) // 释放连接锁
        if (agentConnecting.value) agentConnecting.value = false

        // 如果断开的Agent不是当前活跃的Agent，静默重连（后台Agent需要保持消息接收）
        if (agentId !== currentAgentId.value) {
          // 检查主网关连接状态，如果主网关断开则不重连Agent
          if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
            if (!ws._connectionCompleted) {
              reject(new Error('Background agent disconnected (gateway offline)'))
            }
            return
          }
          if (retryCount < maxRetries) {
            setTimeout(() => {
              connectToAgent({ agent_id: agentId, name: agentId, node_id: agent?.node_id }, retryCount + 1)
                .catch(e => console.warn(`[AGENT ${agentId}] Background reconnect failed:`, e.message))
            }, retryDelay)
          }
          if (!ws._connectionCompleted) {
            reject(new Error('Background agent disconnected'))
          }
          return
        }

        // 当前Agent断开：自动重连
        // 检查主网关连接状态，如果主网关断开则不重连Agent
        if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
          if (!ws._connectionCompleted) {
            reject(new Error('Agent disconnected (gateway offline)'))
          }
          return
        }
        setTimeout(() => {
          // 检查是否已有新连接，避免重复重连
          const currentWs = sockets.value.get(agentId)
          if (currentWs && currentWs.readyState === WebSocket.OPEN) {
            return
          }
          connectToAgent({ agent_id: agentId, name: agentId, node_id: agent?.node_id }, 0)
            .catch(e => console.warn(`[AGENT ${agentId}] Auto-reconnect failed:`, e.message))
        }, retryDelay)

        if (!ws._connectionCompleted) {
          reject(new Error(`Connection closed: code=${event.code}, reason=${event.reason || 'unknown'}`))
        }
      }
      
      ws.onerror = (error) => {
        if (connectionHandled) {
          return
        }
        connectionHandled = true

        clearTimeout(timeoutId)
        console.error(`[AGENT ${agentId}] Connection error:`, error)
        connectingAgents.value.delete(agentId) // 释放连接锁
        if (agentConnecting.value) agentConnecting.value = false

        // 只清理和通知，不重连
        // 重连由switchAgent的稳定性循环统一管理
        ws.close()
        sockets.value.delete(agentId)
        reject(new Error('Connection error'))
      }
      
    } catch (error) {
      console.error(`[AGENT ${agentId}] Failed to connect:`, error)
      connectingAgents.value.delete(agentId) // 释放连接锁
      agentConnecting.value = false
      
      if (retryCount < maxRetries) {
        setTimeout(() => {
          connectToAgent(agent, retryCount + 1).then(resolve).catch(reject)
        }, retryDelay)
      } else {
        reject(error)
      }
    }
  })
}

// 自动连接所有在线的 Agent（不切换当前选中的 Agent）
async function autoConnectToOnlineAgents() {
  // 获取所有在线的 agent（status 为 running）
  const onlineAgents = agentList.value.filter(agent => agent.status === 'running')
  
  if (onlineAgents.length === 0) {
    return
  }
  
  
  // 记录当前选中的 agent，确保不切换
  const savedCurrentAgentId = currentAgentId.value
  
  // 逐个连接在线 agent，添加延迟避免同时建立过多连接
  for (const agent of onlineAgents) {
    // 检查是否已经连接
    if (sockets.value.has(agent.agent_id)) {
      const existingWs = sockets.value.get(agent.agent_id)
      if (existingWs && existingWs.readyState === WebSocket.OPEN) {
        continue
      }
    }
    
    try {
      await connectToAgent(agent)
      // 连接间隔 500ms，避免同时建立过多连接
      await new Promise(resolve => setTimeout(resolve, 500))
    } catch (error) {
      console.warn(`[AUTO_CONNECT] Failed to connect to ${agent.name || agent.agent_id}:`, error.message)
      // 单个连接失败不影响其他连接
    }
  }
  
  // 确保当前选中的 agent 没有被改变
  if (currentAgentId.value !== savedCurrentAgentId) {
    currentAgentId.value = savedCurrentAgentId
  }
  
}

// Agent 心跳定时器
// 检查心跳超时并触发重连
function checkHeartbeatTimeout() {
  const now = Date.now()
  sockets.value.forEach((ws, agentId) => {
    const lastPong = lastPongTime.value.get(agentId)
    // 如果超过超时时间未收到 pong，认为连接已断
    if (!lastPong || (now - lastPong > HEARTBEAT_TIMEOUT)) {
      console.warn(`[HEARTBEAT] Timeout for agent ${agentId}, last pong: ${lastPong ? new Date(lastPong).toLocaleTimeString() : 'never'}, triggering reconnect...`)
      // 关闭旧连接，触发重连
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
      sockets.value.delete(agentId)
      connectingAgents.value.delete(agentId) // 释放连接锁
      lastPongTime.value.delete(agentId)
      // 如果是当前活跃 Agent，触发重连
      if (agentId === currentAgentId.value) {
        const agent = agentList.value.find(a => a.agent_id === agentId)
        if (agent && !connectingAgents.value.has(agentId)) {
          connectToAgent(agent).catch(e => console.warn(`[HEARTBEAT] Reconnect failed for ${agentId}:`, e.message))
        }
      }
    }
  })
}

// 发送心跳到所有 Agent 连接
function sendHeartbeat() {
  const now = Date.now()
  sockets.value.forEach((ws, agentId) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      // 记录发送时间（用于超时检测）
      lastPongTime.value.set(agentId, now) // 先更新为发送时间，收到 pong 后会再次更新
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  })
  
  // 检查是否有连接超时
  checkHeartbeatTimeout()
}

  return {
    // 状态
    gatewayUrl,
    socket,
    sockets,
    lastPongTime,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    connecting,
    agentConnecting,
    connectingAgents,
    connectErrorMessage,
    isRestartingGateway,
    restartNodeId,
    restartFrontendService,
    reconnecting,
    reconnectAttempts,
    reconnectTimer,
    reconnectInterval,
    userDisconnected,
    isAutoConnecting,
    // 派生
    connectionStatus,
    connectionLabel,
    // 主网关连接
    connect,
    disconnect,
    reconnect,
    disconnectAll,
    // 网关重启
    handleRestartGateway,
    confirmRestartGateway,
    restartGateway,
    // Agent 连接
    connectToAgent,
    autoConnectToOnlineAgents,
    // 心跳
    checkHeartbeatTimeout,
    sendHeartbeat,
  }
}
