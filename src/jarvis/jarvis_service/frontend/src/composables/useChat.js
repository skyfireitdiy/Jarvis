// 聊天室 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原 handleChatMessage 16409-16653 + 聊天室面板 17598-18147），保持行为完全一致：
// - 聊天室面板：chatPanelRect / chatPanelCollapsed / chatPanelInteraction / chatPanelStyle（浮动面板布局）
// - 聊天室数据：chatRooms / chatMessages / chatClients / chatRoomMembers / myClientId / activeChatRoomId /
//   activePrivateClientId / chatUnreadCount / chatName / myUserId / chatSidebarWidth / chatUnreadMap / chatJoinedRooms
// - 聊天功能：toggleChatPanel / sendChatMessageToServer / createChatRoom / joinChatRoom / leaveChatRoom /
//   deleteChatRoom / renameChatRoom / clearChatMessages / sendChatMessage / selectPrivateClient / toggleChatPanelCollapse
// - 面板交互：startChatSidebarResize / startChatPanelMove / startChatPanelResize
// - 消息处理：handleChatMessage（WebSocket chat_* 消息分发）
// - 工具：getOrCreateClientId / restoreChatRoomsFromServer
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - socket：ref(WebSocket|null)（主网关连接）
// - auth：ref（用户认证信息，含 userInfo）
// - username：ref(string)（当前用户名）
// - windowWidth：ref(number)（窗口宽度，响应式判断）
// - activeWindow：ref(string|null)（当前焦点窗口）
// - showChatPanel：ref(boolean)（聊天室面板是否显示）
// - focusWindow：函数（聚焦窗口）
// - showToast：函数（提示消息）
// - showConfirm：函数（确认对话框）
// - playChatNotificationSound：函数（聊天消息提示音）
// - getGatewayAddress：函数（返回 { host, port }）
// - workspaceHostsChat：computed(boolean)（工作区是否承载聊天）
// - setWorkspaceMainView：函数（设置工作区主视图）
// - showWorkspaceHostView：函数（在工作区显示指定视图）
// - clamp：函数（数值钳制）
// - PANEL_DRAG_ACTIVATION_DISTANCE：number（拖拽激活距离）
// - ACTIVE_Z_INDEX / BASE_Z_INDEX：number（层级常量）
import { computed, ref, watch } from 'vue'

export function useChat({
  socket,
  auth,
  username,
  windowWidth,
  activeWindow,
  showChatPanel,
  focusWindow,
  showToast,
  showConfirm,
  playChatNotificationSound,
  getGatewayAddress,
  workspaceHostsChat,
  setWorkspaceMainView,
  showWorkspaceHostView,
  clamp,
  PANEL_DRAG_ACTIVATION_DISTANCE,
  ACTIVE_Z_INDEX,
  BASE_Z_INDEX,
}) {

// 聊天室面板
const CHAT_PANEL_MIN_WIDTH = 400
const CHAT_PANEL_MIN_HEIGHT = 300
const CHAT_PANEL_STORAGE_KEY = 'jarvis_chat_panel_rect'
const chatResizeDirections = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function getDefaultChatPanelRect() {
  return {
    top: 88,
    left: Math.max(window.innerWidth - 824, 16),
    width: 800,
    height: 500,
  }
}

function loadChatPanelRect() {
  const defaultChatPanelRect = getDefaultChatPanelRect()
  const savedValue = localStorage.getItem(CHAT_PANEL_STORAGE_KEY)
  if (!savedValue) {
    return defaultChatPanelRect
  }

  try {
    const parsedValue = JSON.parse(savedValue)
    if (
      typeof parsedValue.top !== 'number' ||
      typeof parsedValue.left !== 'number' ||
      typeof parsedValue.width !== 'number' ||
      typeof parsedValue.height !== 'number'
    ) {
      return defaultChatPanelRect
    }

    return parsedValue
  } catch {
    return defaultChatPanelRect
  }
}

function saveChatPanelRect() {
  localStorage.setItem(CHAT_PANEL_STORAGE_KEY, JSON.stringify(chatPanelRect.value))
}

const chatPanelRect = ref(loadChatPanelRect())
const chatPanelCollapsed = ref(false)
const chatPanelInteraction = ref({
  active: false,
  mode: null,
  direction: null,
  startX: 0,
  startY: 0,
  startTop: 0,
  startLeft: 0,
  startWidth: 0,
  startHeight: 0,
})

const chatPanelStyle = computed(() => {
  // 移动端全屏显示
  if (windowWidth.value <= 768) {
    return {
      top: '0',
      left: '0',
      width: '100vw',
      height: 'var(--app-height, 100vh)',
      zIndex: activeWindow.value === 'chat' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
    }
  }
  // 折叠状态：只显示窄条
  if (chatPanelCollapsed.value) {
    return {
      top: `${chatPanelRect.value.top}px`,
      left: `${chatPanelRect.value.left}px`,
      width: '40px',
      height: `${chatPanelRect.value.height}px`,
      zIndex: activeWindow.value === 'chat' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
    }
  }
  return {
    top: `${chatPanelRect.value.top}px`,
    left: `${chatPanelRect.value.left}px`,
    width: `${chatPanelRect.value.width}px`,
    height: `${chatPanelRect.value.height}px`,
    zIndex: activeWindow.value === 'chat' ? ACTIVE_Z_INDEX : BASE_Z_INDEX,
  }
})

// 聊天室数据状态
const CHAT_MESSAGES_STORAGE_KEY = 'jarvis_chat_messages'

function loadChatMessages() {
  try {
    const saved = localStorage.getItem(CHAT_MESSAGES_STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      // 兼容旧格式（数组）和新格式（对象）
      if (Array.isArray(parsed)) {
        const map = {}
        parsed.forEach(msg => {
          const key = msg.room_id || 'private'
          if (!map[key]) map[key] = []
          map[key].push(msg)
        })
        return map
      }
      return parsed
    }
    return {}
  } catch {
    return {}
  }
}

function saveChatMessages() {
  try {
    const toSave = {}
    for (const [roomId, msgs] of Object.entries(chatMessages.value)) {
      toSave[roomId] = msgs.slice(-200)
    }
    localStorage.setItem(CHAT_MESSAGES_STORAGE_KEY, JSON.stringify(toSave))
  } catch (e) {
    console.warn('[CHAT] Failed to save messages:', e)
  }
}

const chatRooms = ref([])
const chatMessages = ref(loadChatMessages())
const chatClients = ref([])
const chatRoomMembers = ref([])
const myClientId = ref('')
const activeChatRoomId = ref('')
const activePrivateClientId = ref('')
const chatUnreadCount = ref(0)
const chatName = computed(() => auth.value.userInfo?.display_name || username.value)
const myUserId = computed(() => auth.value.userInfo?.user_id || myClientId.value)
const chatSidebarWidth = ref(parseInt(localStorage.getItem('jarvis_chat_sidebar_width') || '160'))
const chatUnreadMap = ref({})
const CHAT_JOINED_ROOMS_KEY = 'jarvis_chat_joined_rooms'
const chatJoinedRooms = ref(JSON.parse(localStorage.getItem(CHAT_JOINED_ROOMS_KEY) || '[]'))

function saveChatJoinedRooms() {
  localStorage.setItem(CHAT_JOINED_ROOMS_KEY, JSON.stringify(chatJoinedRooms.value))
}

async function restoreChatRoomsFromServer() {
  // 从API获取用户已加入的房间，用于登录后恢复
  try {
    const resp = await fetch('/api/chat/user-rooms', { headers: { 'Authorization': `Bearer ${auth.value.token}` } })
    const data = await resp.json()
    if (data.success && data.rooms) {
      const serverRoomIds = data.rooms.map(r => r.room_id)
      // 合并服务端房间与本地缓存
      const merged = [...new Set([...serverRoomIds, ...chatJoinedRooms.value.filter(rid => rid)])]
      chatJoinedRooms.value = merged
      saveChatJoinedRooms()
      // 自动重新加入所有房间
      if (merged.length > 0) {
        chatAutoRejoining = true
        chatAutoRejoinCount = merged.length
        merged.forEach(rid => {
          sendChatMessageToServer('chat_join_room', { room_id: rid, client_id: myClientId.value })
        })
      }
    }
  } catch (e) {
    // API失败时回退到localStorage缓存
    const savedRooms = chatJoinedRooms.value.filter(rid => rid)
    if (savedRooms.length > 0) {
      chatAutoRejoining = true
      chatAutoRejoinCount = savedRooms.length
      savedRooms.forEach(rid => {
        sendChatMessageToServer('chat_join_room', { room_id: rid, client_id: myClientId.value })
      })
    }
  }
}

let chatAutoRejoining = false
let chatAutoRejoinCount = 0

function startChatSidebarResize(event) {
  const startX = event.clientX
  const startWidth = chatSidebarWidth.value
  const onMove = (e) => {
    const delta = e.clientX - startX
    chatSidebarWidth.value = Math.max(120, Math.min(400, startWidth + delta))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    localStorage.setItem('jarvis_chat_sidebar_width', String(chatSidebarWidth.value))
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function getOrCreateClientId() {
  let clientId = localStorage.getItem('jarvis_chat_client_id')
  if (!clientId) {
    clientId = 'client_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
    localStorage.setItem('jarvis_chat_client_id', clientId)
  }
  return clientId
}



// 聊天室面板交互
function getChatPanelBounds() {
  const HEADER_HEIGHT = 32 // 标题栏高度
  const MIN_VISIBLE_WIDTH = 100 // 至少保留100px面板宽度可见
  return {
    minTop: 0,
    minLeft: 0,
    maxLeft: window.innerWidth - MIN_VISIBLE_WIDTH,
    maxTop: window.innerHeight - HEADER_HEIGHT,
    maxWidth: window.innerWidth,
    maxHeight: window.innerHeight,
  }
}

function ensureChatPanelInViewport() {
  const HEADER_HEIGHT = 32
  const MIN_VISIBLE_WIDTH = 100
  const maxWidth = Math.max(window.innerWidth, CHAT_PANEL_MIN_WIDTH)
  const maxHeight = Math.max(window.innerHeight, CHAT_PANEL_MIN_HEIGHT)

  chatPanelRect.value.width = clamp(chatPanelRect.value.width, CHAT_PANEL_MIN_WIDTH, maxWidth)
  chatPanelRect.value.height = clamp(chatPanelRect.value.height, CHAT_PANEL_MIN_HEIGHT, maxHeight)

  chatPanelRect.value.left = clamp(
    chatPanelRect.value.left,
    0,
    window.innerWidth - MIN_VISIBLE_WIDTH
  )
  chatPanelRect.value.top = clamp(
    chatPanelRect.value.top,
    0,
    window.innerHeight - HEADER_HEIGHT
  )
}

function startChatPanelMove(event) {
  if (windowWidth.value <= 768) return
  if (event.target.closest('.chat-panel-actions')) return

  focusWindow('chat')

  chatPanelInteraction.value = {
    active: false,
    mode: 'move',
    direction: null,
    startX: event.clientX,
    startY: event.clientY,
    startTop: chatPanelRect.value.top,
    startLeft: chatPanelRect.value.left,
    startWidth: chatPanelRect.value.width,
    startHeight: chatPanelRect.value.height,
  }

  document.addEventListener('mousemove', onChatPanelPointerMove)
  document.addEventListener('mouseup', stopChatPanelInteraction)
}

function startChatPanelResize(event, direction) {
  if (windowWidth.value <= 768) return

  chatPanelInteraction.value = {
    active: true,
    mode: 'resize',
    direction,
    startX: event.clientX,
    startY: event.clientY,
    startTop: chatPanelRect.value.top,
    startLeft: chatPanelRect.value.left,
    startWidth: chatPanelRect.value.width,
    startHeight: chatPanelRect.value.height,
  }

  document.addEventListener('mousemove', onChatPanelPointerMove)
  document.addEventListener('mouseup', stopChatPanelInteraction)
  event.preventDefault()
  event.stopPropagation()
}

function onChatPanelPointerMove(event) {
  const deltaX = event.clientX - chatPanelInteraction.value.startX
  const deltaY = event.clientY - chatPanelInteraction.value.startY

  if (chatPanelInteraction.value.mode === 'move' && !chatPanelInteraction.value.active) {
    const dragDistance = Math.hypot(deltaX, deltaY)
    if (dragDistance < PANEL_DRAG_ACTIVATION_DISTANCE) {
      return
    }

    chatPanelInteraction.value = {
      ...chatPanelInteraction.value,
      active: true,
    }
    event.preventDefault()
  }

  if (!chatPanelInteraction.value.active) return

  if (chatPanelInteraction.value.mode === 'move') {
    const bounds = getChatPanelBounds()
    chatPanelRect.value.left = clamp(chatPanelInteraction.value.startLeft + deltaX, bounds.minLeft, bounds.maxLeft)
    chatPanelRect.value.top = clamp(chatPanelInteraction.value.startTop + deltaY, bounds.minTop, bounds.maxTop)
    return
  }

  const direction = chatPanelInteraction.value.direction || ''
  const startLeft = chatPanelInteraction.value.startLeft
  const startTop = chatPanelInteraction.value.startTop
  const startWidth = chatPanelInteraction.value.startWidth
  const startHeight = chatPanelInteraction.value.startHeight

  let nextLeft = startLeft
  let nextTop = startTop
  let nextWidth = startWidth
  let nextHeight = startHeight

  if (direction.includes('e')) {
    nextWidth = clamp(startWidth + deltaX, CHAT_PANEL_MIN_WIDTH, Math.max(window.innerWidth - startLeft, CHAT_PANEL_MIN_WIDTH))
  }

  if (direction.includes('s')) {
    nextHeight = clamp(startHeight + deltaY, CHAT_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - startTop, CHAT_PANEL_MIN_HEIGHT))
  }

  if (direction.includes('w')) {
    const desiredLeft = clamp(startLeft + deltaX, 0, startLeft + startWidth - CHAT_PANEL_MIN_WIDTH)
    nextLeft = desiredLeft
    nextWidth = startWidth - (desiredLeft - startLeft)
  }

  if (direction.includes('n')) {
    const desiredTop = clamp(startTop + deltaY, 0, startTop + startHeight - CHAT_PANEL_MIN_HEIGHT)
    nextTop = desiredTop
    nextHeight = startHeight - (desiredTop - startTop)
  }

  if (nextLeft + nextWidth > window.innerWidth) {
    nextWidth = Math.max(CHAT_PANEL_MIN_WIDTH, window.innerWidth - nextLeft)
  }

  if (nextTop + nextHeight > window.innerHeight) {
    nextHeight = Math.max(CHAT_PANEL_MIN_HEIGHT, window.innerHeight - nextTop)
  }

  chatPanelRect.value.left = clamp(nextLeft, 0, Math.max(window.innerWidth - nextWidth, 0))
  chatPanelRect.value.top = clamp(nextTop, 0, Math.max(window.innerHeight - nextHeight, 0))
  chatPanelRect.value.width = clamp(nextWidth, CHAT_PANEL_MIN_WIDTH, Math.max(window.innerWidth - chatPanelRect.value.left, CHAT_PANEL_MIN_WIDTH))
  chatPanelRect.value.height = clamp(nextHeight, CHAT_PANEL_MIN_HEIGHT, Math.max(window.innerHeight - chatPanelRect.value.top, CHAT_PANEL_MIN_HEIGHT))
}

function stopChatPanelInteraction() {
  chatPanelInteraction.value = {
    active: false,
    mode: null,
    direction: null,
    startX: 0,
    startY: 0,
    startTop: 0,
    startLeft: 0,
    startWidth: 0,
    startHeight: 0,
  }

  document.removeEventListener('mousemove', onChatPanelPointerMove)
  document.removeEventListener('mouseup', stopChatPanelInteraction)
  saveChatPanelRect()
}

// 聊天室功能方法
function toggleChatPanelCollapse() {
  chatPanelCollapsed.value = !chatPanelCollapsed.value
}

function toggleChatPanel() {
  // 工作区正在显示聊天室时，语义为「收起」：切回文件视图
  if (workspaceHostsChat.value) {
    setWorkspaceMainView('file')
    return
  }
  showWorkspaceHostView('chat')
  focusWindow('chat')
  chatUnreadCount.value = 0
  // 首次打开时注册客户端并获取聊天室列表
  if (!myClientId.value) {
    myClientId.value = getOrCreateClientId()
    sendChatMessageToServer('chat_register', { client_id: myClientId.value, name: username.value })
  }
  sendChatMessageToServer('chat_get_rooms', {})
  sendChatMessageToServer('chat_get_clients', {})
}

// username变更时同步更新聊天室注册名
watch(username, (val) => {
  if (myClientId.value && val) {
    sendChatMessageToServer('chat_register', { client_id: myClientId.value, name: val })
    sendChatMessageToServer('chat_get_clients', {})
    if (activeChatRoomId.value) {
      sendChatMessageToServer('chat_get_room_members', { room_id: activeChatRoomId.value })
    }
  }
})

function sendChatMessageToServer(type, payload) {
  if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
    console.warn('[CHAT] No socket connection')
    return
  }
  socket.value.send(JSON.stringify({ type, payload }))
}

function createChatRoom(roomName) {
  if (!roomName || !roomName.trim()) return
  sendChatMessageToServer('chat_create_room', { name: roomName.trim(), client_id: myClientId.value })
}

function joinChatRoom(roomId) {
  activeChatRoomId.value = roomId
  // 切换到群聊时清空私聊选中
  activePrivateClientId.value = ''
  // 清除房间未读计数
  const { [roomId]: _, ...rest } = chatUnreadMap.value
  chatUnreadMap.value = rest
  // 已加入的房间仅切换查看，未加入的才发送join请求
  if (!chatJoinedRooms.value.includes(roomId)) {
    sendChatMessageToServer('chat_join_room', { room_id: roomId, client_id: myClientId.value })
  } else {
    sendChatMessageToServer('chat_get_room_members', { room_id: roomId })
  }
}

function leaveChatRoom(roomId) {
  sendChatMessageToServer('chat_leave_room', { room_id: roomId, client_id: myClientId.value })
}

function deleteChatRoom(roomId) {
  showConfirm('确定要删除此聊天室吗？此操作不可撤销。', () => {
    sendChatMessageToServer('chat_delete_room', { room_id: roomId, client_id: myClientId.value })
  })
}

function renameChatRoom(roomId, newName) {
  sendChatMessageToServer('chat_rename_room', { room_id: roomId, client_id: myClientId.value, new_name: newName })
}

function clearChatMessages(scope) {
  if (scope === 'all') {
    showConfirm('确定要清空全部聊天记录吗？此操作不可撤销。', () => {
      chatMessages.value = {}
      saveChatMessages()
    })
  } else if (scope === 'current') {
    const key = activePrivateClientId.value
      ? `private_${activePrivateClientId.value}`
      : activeChatRoomId.value
    if (key) {
      showConfirm('确定要清空当前聊天记录吗？此操作不可撤销。', () => {
        const { [key]: _, ...rest } = chatMessages.value
        chatMessages.value = rest
        saveChatMessages()
      })
    }
  }
}

// 将相对路径的图片 URL 转换为完整 URL（uploads 挂载在后端网关）
function resolveImageUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/uploads/')) {
    const { host, port } = getGatewayAddress()
    const protocol = window.location.protocol === 'https:' ? 'https' : 'http'
    return `${protocol}://${host}:${port}${url}`
  }
  return url
}

function sendChatMessage(content, imageUrl) {
  if ((!content || !content.trim()) && !imageUrl) return
  const trimmed = (content || '').trim()
  if (activePrivateClientId.value) {
    // 私聊模式
    const payload = {
      sender_id: myClientId.value,
      receiver_id: activePrivateClientId.value,
      content: trimmed,
    }
    if (imageUrl) payload.image_url = resolveImageUrl(imageUrl)
    sendChatMessageToServer('chat_send_private', payload)
    // 本地追加自己的消息
    const selfMsgKey = `private_${activePrivateClientId.value}`
    if (!chatMessages.value[selfMsgKey]) chatMessages.value[selfMsgKey] = []
    const selfMsg = {
      client_id: myClientId.value,
      client_name: chatName.value || myClientId.value,
      sender_name: username.value || myClientId.value,
      sender_display_name: chatName.value || username.value,
      content: trimmed,
      private: true,
      timestamp: Date.now(),
    }
    if (imageUrl) selfMsg.image_url = resolveImageUrl(imageUrl)
    chatMessages.value[selfMsgKey].push(selfMsg)
    saveChatMessages()
  } else if (activeChatRoomId.value) {
    // 聊天室模式
    const payload = {
      room_id: activeChatRoomId.value,
      client_id: myClientId.value,
      content: trimmed,
    }
    if (imageUrl) payload.image_url = resolveImageUrl(imageUrl)
    sendChatMessageToServer('chat_send_message', payload)
    // 本地追加自己的消息
    if (!chatMessages.value[activeChatRoomId.value]) chatMessages.value[activeChatRoomId.value] = []
    const selfMsg = {
      client_id: myClientId.value,
      client_name: chatName.value || myClientId.value,
      sender_name: username.value || myClientId.value,
      sender_display_name: chatName.value || username.value,
      content: trimmed,
      room_id: activeChatRoomId.value,
      timestamp: Date.now(),
    }
    if (imageUrl) selfMsg.image_url = resolveImageUrl(imageUrl)
    chatMessages.value[activeChatRoomId.value].push(selfMsg)
    saveChatMessages()
  } else {
    showToast('请先加入聊天室或选择私聊对象', 'warning')
  }
}

function selectPrivateClient(clientId) {
  if (activePrivateClientId.value === clientId) {
    activePrivateClientId.value = ''
  } else {
    activePrivateClientId.value = clientId
    // 不清空activeChatRoomId，保持群聊加入状态
    // 清除私聊未读计数
    const privKey = `private_${clientId}`
    const { [privKey]: _, ...rest } = chatUnreadMap.value
    chatUnreadMap.value = rest
    // 获取私聊历史
    sendChatMessageToServer('chat_get_private_history', {
      client_id: myUserId.value,
      other_id: clientId,
    })
  }
}
function handleChatMessage(type, payload) {
  switch (type) {
    case 'chat_register_response':
      if (payload?.success) {
        myClientId.value = payload.client_id || myClientId.value
        // 将自身加入在线用户列表（使用display_name，按user_id去重）
        if (payload.client_id) {
          const uid = payload.user_id || payload.client_id
          const existing = chatClients.value.find(c => (c.user_id || c.client_id) === uid)
          if (existing) {
            existing.client_id = payload.client_id
            existing.name = payload.name
            existing.display_name = payload.display_name || payload.name
          } else {
            chatClients.value = [...chatClients.value, { client_id: payload.client_id, user_id: uid, name: payload.name, display_name: payload.display_name || payload.name }]
          }
        }
        // 从API恢复用户已加入的房间（优先于localStorage缓存）
        restoreChatRoomsFromServer()
      } else {
        // 注册失败，清空缓存
        chatJoinedRooms.value = []
        saveChatJoinedRooms()
      }
      break
    case 'chat_get_rooms_response':
      chatRooms.value = payload?.rooms || []
      break
    case 'chat_create_room_response':
      if (payload?.success && payload.room_id) {
        chatRooms.value.push({
          room_id: payload.room_id,
          name: payload.name || '未命名聊天室',
          member_count: 1,
          created_by: auth.value.userInfo?.user_id || '',
        })
        if (!chatJoinedRooms.value.includes(payload.room_id)) { chatJoinedRooms.value = [...chatJoinedRooms.value, payload.room_id]; saveChatJoinedRooms() }
        showToast('聊天室创建成功', 'success')
      } else {
        showToast(payload?.error || '创建聊天室失败', 'error')
      }
      break
    case 'chat_join_room_response':
      if (payload?.success) {
        if (!chatAutoRejoining) showToast('已加入聊天室', 'success')
        const joinedRoomId = payload?.room_id || activeChatRoomId.value
        if (joinedRoomId && !chatJoinedRooms.value.includes(joinedRoomId)) { chatJoinedRooms.value = [...chatJoinedRooms.value, joinedRoomId]; saveChatJoinedRooms() }
        // 获取聊天室成员列表
        if (joinedRoomId) sendChatMessageToServer('chat_get_room_members', { room_id: joinedRoomId })
      } else {
        if (!chatAutoRejoining) showToast(payload?.error || '加入聊天室失败', 'error')
        // 加入失败（房间可能已删除），从缓存中移除
        const failedRoomId = payload?.room_id || activeChatRoomId.value
        if (failedRoomId && chatJoinedRooms.value.includes(failedRoomId)) {
          chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== failedRoomId)
          saveChatJoinedRooms()
        }
      }
      // 自动重连加入完成计数
      if (chatAutoRejoining) {
        chatAutoRejoinCount--
        if (chatAutoRejoinCount <= 0) chatAutoRejoining = false
      }
      break
    case 'chat_get_clients_response':
      chatClients.value = payload?.clients || []
      break
    case 'chat_client_joined':
      if (payload?.client_id && payload?.client_id !== myClientId.value) {
        const uid = payload.user_id || payload.client_id
        const existing = chatClients.value.find(c => (c.user_id || c.client_id) === uid)
        if (existing) {
          existing.client_id = payload.client_id
          existing.name = payload.name
          existing.display_name = payload.display_name || payload.name
        } else {
          chatClients.value = [...chatClients.value, { client_id: payload.client_id, user_id: uid, name: payload.name, display_name: payload.display_name || payload.name }]
        }
      }
      break
    case 'chat_client_left':
      if (payload?.client_id && !payload?.still_online) {
        const uid = payload.user_id || payload.client_id
        chatClients.value = chatClients.value.filter(c => (c.user_id || c.client_id) !== uid)
      }
      break
    case 'chat_get_room_members_response':
      chatRoomMembers.value = payload?.members || []
      break
    case 'chat_message':
      // 聊天室广播消息（过滤自己发送的，本地已追加）
      if (payload?.client_id === myClientId.value) break
      const roomId = payload?.room_id || 'general'
      if (!chatMessages.value[roomId]) chatMessages.value[roomId] = []
      const roomMsg = {
        client_id: payload?.client_id,
        client_name: payload?.sender_display_name || payload?.sender_name || payload?.client_id,
        sender_name: payload?.sender_name || payload?.client_id,
        sender_display_name: payload?.sender_display_name || payload?.sender_name,
        content: payload?.content,
        room_id: roomId,
        timestamp: payload?.timestamp || Date.now(),
      }
      if (payload?.image_url) roomMsg.image_url = resolveImageUrl(payload.image_url)
      chatMessages.value[roomId].push(roomMsg)
      saveChatMessages()
      // 新消息提醒：非自己发送的消息触发提醒
      if (payload?.client_id !== myClientId.value) {
        playChatNotificationSound()
        if (!showChatPanel.value || activeWindow.value !== 'chat') {
          chatUnreadCount.value++
        }
        // 按房间维度记录未读数
        const roomKey = payload?.room_id || 'general'
        if (activeChatRoomId.value !== roomKey || activePrivateClientId.value) {
          chatUnreadMap.value = { ...chatUnreadMap.value, [roomKey]: (chatUnreadMap.value[roomKey] || 0) + 1 }
        }
      }
      break
    case 'chat_private_message':
      // 私聊消息（过滤自己发送的，本地已追加）
      if (payload?.message?.sender_id === myClientId.value) break
      const privPeerId = payload?.message?.sender_user_id || payload?.sender_user_id || payload?.message?.sender_id
      const privMsgKey = `private_${privPeerId}`
      if (!chatMessages.value[privMsgKey]) chatMessages.value[privMsgKey] = []
      const privMsg = {
        client_id: payload?.message?.sender_id,
        client_name: payload?.message?.sender_display_name || payload?.message?.sender_name || payload?.message?.sender_id,
        sender_name: payload?.message?.sender_name || payload?.message?.sender_id,
        sender_display_name: payload?.message?.sender_display_name || payload?.message?.sender_name,
        content: payload?.message?.content,
        private: true,
        timestamp: payload?.message?.timestamp || Date.now(),
      }
      if (payload?.message?.image_url) privMsg.image_url = resolveImageUrl(payload.message.image_url)
      chatMessages.value[privMsgKey].push(privMsg)
      saveChatMessages()
      // 新消息提醒：非自己发送的消息触发提醒
      if (payload?.message?.sender_id !== myClientId.value) {
        playChatNotificationSound()
        if (!showChatPanel.value || activeWindow.value !== 'chat') {
          chatUnreadCount.value++
        }
        // 按私聊维度记录未读数
        const privUnreadKey = `private_${privPeerId}`
        if (activePrivateClientId.value !== privPeerId) {
          chatUnreadMap.value = { ...chatUnreadMap.value, [privUnreadKey]: (chatUnreadMap.value[privUnreadKey] || 0) + 1 }
        }
      }
      break
    case 'chat_get_private_history_response':
      if (payload?.messages) {
        const histKey = `private_${payload?.other_id || activePrivateClientId.value}`
        chatMessages.value[histKey] = payload.messages.map(msg => {
          const m = {
            client_id: msg.sender_id,
            client_name: msg.sender_name || msg.sender_id,
            sender_name: msg.sender_name || msg.sender_id,
            content: msg.content,
            private: true,
            timestamp: msg.timestamp || Date.now(),
          }
          if (msg.image_url) m.image_url = resolveImageUrl(msg.image_url)
          return m
        })
        saveChatMessages()
      }
      break
    case 'chat_leave_room_response':
      if (payload?.success) {
        showToast('已退出聊天室', 'success')
        const leftRoomId = payload?.room_id || activeChatRoomId.value
        chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== leftRoomId)
        saveChatJoinedRooms()
        delete chatMessages.value[leftRoomId]
        if (activeChatRoomId.value === leftRoomId) {
          activeChatRoomId.value = ''
        }
        saveChatMessages()
      } else {
        showToast(payload?.error || '退出聊天室失败', 'error')
      }
      break
    case 'chat_delete_room_response':
      if (payload?.success) {
        showToast('聊天室已删除', 'success')
        const deletedRoomId = payload?.room_id || activeChatRoomId.value
        chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== deletedRoomId)
        saveChatJoinedRooms()
        delete chatMessages.value[deletedRoomId]
        chatRooms.value = chatRooms.value.filter(r => r.room_id !== deletedRoomId)
        if (activeChatRoomId.value === deletedRoomId) {
          activeChatRoomId.value = ''
        }
        saveChatMessages()
      } else {
        showToast(payload?.error || '删除聊天室失败', 'error')
      }
      break
    case 'chat_room_created':
      // 其他用户创建的新房间通知
      if (payload?.room_id) {
        chatRooms.value = [...chatRooms.value, {
          room_id: payload.room_id,
          name: payload.name || '未命名聊天室',
          member_count: payload.member_count || 1,
          created_by: payload.created_by || '',
        }]
      }
      break
    case 'chat_rename_room_response':
      if (payload?.success) {
        showToast('聊天室已重命名', 'success')
      } else {
        showToast(payload?.error || '重命名聊天室失败', 'error')
      }
      break
    case 'chat_room_renamed':
      // 广播通知：更新本地房间名
      if (payload?.room_id && payload?.new_name) {
        chatRooms.value = chatRooms.value.map(r =>
          r.room_id === payload.room_id ? { ...r, name: payload.new_name } : r
        )
      }
      break
    case 'chat_room_deleted':
      const removedRoomId = payload?.room_id
      if (removedRoomId) {
        chatJoinedRooms.value = chatJoinedRooms.value.filter(r => r !== removedRoomId)
        saveChatJoinedRooms()
        delete chatMessages.value[removedRoomId]
        chatRooms.value = chatRooms.value.filter(r => r.room_id !== removedRoomId)
        if (activeChatRoomId.value === removedRoomId) {
          activeChatRoomId.value = ''
        }
        saveChatMessages()
        showToast('聊天室已被创建者删除', 'warning')
      }
      break
    case 'chat_error':
      showToast(payload?.error || '聊天室操作失败', 'error')
      break
  }
}

  return {
    // 面板布局
    chatPanelRect,
    chatPanelCollapsed,
    chatPanelInteraction,
    chatPanelStyle,
    // 聊天室数据
    chatRooms,
    chatMessages,
    chatClients,
    chatRoomMembers,
    myClientId,
    activeChatRoomId,
    activePrivateClientId,
    chatUnreadCount,
    chatName,
    myUserId,
    chatSidebarWidth,
    chatUnreadMap,
    chatJoinedRooms,
    // 面板交互
    startChatSidebarResize,
    startChatPanelMove,
    startChatPanelResize,
    // 聊天功能
    toggleChatPanel,
    toggleChatPanelCollapse,
    sendChatMessageToServer,
    createChatRoom,
    joinChatRoom,
    leaveChatRoom,
    deleteChatRoom,
    renameChatRoom,
    clearChatMessages,
    sendChatMessage,
    selectPrivateClient,
    // 消息处理
    handleChatMessage,
    // 工具
    getOrCreateClientId,
    restoreChatRoomsFromServer,
  }
}
