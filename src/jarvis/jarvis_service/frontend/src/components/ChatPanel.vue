<template>
  <aside
    v-show="visible"
    class="chat-panel"
    :class="{ 'chat-panel-dragging': interaction.active }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'chat')"
  >
    <div class="chat-panel-header" @mousedown="$emit('startMove', $event)" @dblclick.stop="$emit('toggleMaximize')">
      <div class="chat-panel-title-group">
        <h3>聊天室</h3>
        <span v-if="unreadCount > 0" class="chat-unread-badge">{{ unreadCount }}</span>
      </div>
      <span class="chat-username">{{ myName }}</span>
      <div class="chat-panel-actions">
        <button class="icon-btn" @click="$emit('toggleMaximize')" :title="isMaximized ? '还原' : '最大化'">
          {{ isMaximized ? '🗗' : '🗖' }}
        </button>
        <button class="icon-btn" @click="$emit('close')" title="关闭面板">✕</button>
      </div>
    </div>

    <!-- 主体区域：侧边栏 + 消息区 横向排列 -->
    <div class="chat-body">
      <!-- 左侧侧边栏：聊天室列表 + 在线用户列表 -->
      <div v-show="!sidebarCollapsed" class="chat-sidebar" :style="{ width: sidebarWidth + 'px' }">
        <div class="chat-sidebar-header">
          <span>聊天室</span>
          <div class="chat-sidebar-actions">
            <button class="icon-btn small" @click="showCreateRoomInput" title="创建聊天室">➕</button>
            <button class="icon-btn small" @click="$emit('clearMessages', 'all')" title="清空全部记录">🗑</button>
            <button class="icon-btn small" @click="sidebarCollapsed = true" title="收起侧边栏">◀</button>
          </div>
        </div>

        <!-- 创建聊天室内联输入框 -->
        <div v-if="creatingRoom" class="chat-create-room-inline">
          <input
            v-model="newRoomName"
            class="chat-create-room-input"
            placeholder="输入聊天室名称..."
            @keydown.enter.exact="confirmCreateRoom"
            @keydown.escape="cancelCreateRoom"
            ref="createRoomInputRef"
          />
          <div class="chat-create-room-actions">
            <button class="icon-btn small chat-create-confirm" @click="confirmCreateRoom" title="确认">✓</button>
            <button class="icon-btn small chat-create-cancel" @click="cancelCreateRoom" title="取消">✕</button>
          </div>
        </div>
        <div class="chat-room-list">
          <div
            v-for="room in rooms"
            :key="room.room_id"
            class="chat-room-item"
            :class="{ active: activeRoomId === room.room_id, joined: joinedRooms?.includes?.(room.room_id) }"
            @click="$emit('joinRoom', room.room_id)"
          >
            <template v-if="renamingRoomId === room.room_id">
              <input
                v-model="renameRoomName"
                class="chat-create-room-input chat-rename-room-input"
                placeholder="输入新的聊天室名称..."
                @keydown.enter.exact="confirmRenameRoom"
                @keydown.escape="cancelRenameRoom"
                @click.stop
                ref="renameRoomInputRef"
              />
              <div class="chat-create-room-actions">
                <button class="icon-btn small chat-create-confirm" @click.stop="confirmRenameRoom" title="确认">✓</button>
                <button class="icon-btn small chat-create-cancel" @click.stop="cancelRenameRoom" title="取消">✕</button>
              </div>
            </template>
            <template v-else>
              <span class="chat-room-name">{{ room.name }}</span>
              <span v-if="unreadMap[room.room_id]" class="chat-unread-badge chat-room-unread">{{ unreadMap[room.room_id] }}</span>
            </template>
            <div v-if="renamingRoomId !== room.room_id" class="chat-room-actions">
              <span class="chat-room-count">{{ room.member_count }}</span>
              <button v-if="activeRoomId === room.room_id" class="icon-btn small chat-room-action-btn" @click.stop="$emit('leaveRoom', room.room_id)" title="退出聊天室">🚪</button>
              <button class="icon-btn small chat-room-action-btn" @click.stop="handleRenameRoom(room)" title="重命名聊天室">✏️</button>
              <button class="icon-btn small chat-room-action-btn" @click.stop="$emit('deleteRoom', room.room_id)" title="删除聊天室">🗑</button>
            </div>
          </div>
          <div v-if="rooms.length === 0" class="chat-empty">暂无聊天室</div>
        </div>

        <!-- 聊天室成员（仅加入房间时显示） -->
        <div v-if="activeRoomId && roomMembers.length > 0" class="chat-members-panel">
          <div class="chat-sidebar-header">
            <span>聊天室成员</span>
          </div>
          <div class="chat-client-list">
            <div
              v-for="member in roomMembers"
              :key="member.client_id"
              class="chat-client-item"
              :class="{ active: activePrivateId === member.client_id }"
              @click="$emit('selectPrivate', member.client_id)"
            >
              <span class="chat-client-name">{{ member.display_name && member.display_name !== member.name ? member.display_name + ' (' + member.name + ')' : member.name }}</span>
              <span v-if="unreadMap['private_' + member.client_id]" class="chat-unread-badge chat-client-unread">{{ unreadMap['private_' + member.client_id] }}</span>
            </div>
          </div>
        </div>

        <!-- 在线用户列表（始终显示） -->
        <div class="chat-users-panel">
          <div class="chat-sidebar-header">
            <span>在线用户</span>
          </div>
          <div class="chat-client-list">
            <div
              v-for="client in clients"
              :key="client.client_id"
              class="chat-client-item"
              :class="{ active: activePrivateId === client.client_id }"
              @click="$emit('selectPrivate', client.client_id)"
            >
              <span class="chat-client-name">{{ client.display_name && client.display_name !== client.name ? client.display_name + ' (' + client.name + ')' : client.name }}</span>
              <span v-if="unreadMap['private_' + client.client_id]" class="chat-unread-badge chat-client-unread">{{ unreadMap['private_' + client.client_id] }}</span>
            </div>
            <div v-if="clients.length === 0" class="chat-empty">暂无在线用户</div>
          </div>
        </div>
      </div>

      <!-- 侧边栏拖拽调整宽度 -->
      <div v-show="!sidebarCollapsed" class="chat-sidebar-resize" @mousedown="$emit('startSidebarResize', $event)"></div>

      <!-- 侧边栏收起时的展开按钮 -->
      <div v-if="sidebarCollapsed" class="chat-sidebar-expand" @click="sidebarCollapsed = false" title="展开侧边栏">
        <span>▶</span>
      </div>

      <!-- 消息区域 -->
      <div class="chat-main">
        <div class="chat-main-header">
          <span class="chat-main-title">{{ activeRoomId ? '聊天室消息' : (activePrivateId ? '私聊消息' : '消息') }}</span>
          <button v-if="activeRoomId || activePrivateId" class="icon-btn small" @click="$emit('clearMessages', 'current')" title="清空当前记录">🗑</button>
        </div>
        <div class="chat-messages" ref="messagesRef">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            class="chat-message"
            :class="{ mine: msg.client_id === myClientId, 'chat-message-new': idx === messages.length - 1 && msg.client_id !== myClientId }"
          >
            <span class="chat-message-sender">{{ msg.sender_display_name || msg.sender_name }}</span>
            <div class="chat-message-bubble">
              <img v-if="msg.image_url" :src="msg.image_url" class="chat-message-image" @click="openImage(msg.image_url)" />
              <span v-if="msg.content" class="chat-message-content">{{ msg.content }}</span>
            </div>
            <span class="chat-message-time">{{ formatTime(msg.timestamp) }}</span>
          </div>
          <div v-if="messages.length === 0" class="chat-empty">暂无消息</div>
        </div>

        <!-- 输入区域 -->
        <div class="chat-input-area">
          <textarea
            v-model="draftMessage"
            class="chat-input"
            placeholder="输入消息... (Ctrl+Enter / Ctrl+D 发送)"
            rows="1"
            @input="autoResizeInput"
            @keydown="handleInputKeydown"
            @paste="handleChatPaste"
            ref="chatInputRef"
          ></textarea>
          <div v-if="pendingImageUrl" class="chat-pending-image-wrapper">
            <img :src="pendingImageUrl" class="chat-pending-image" />
            <button class="chat-pending-image-remove" @click="pendingImageUrl = ''" title="取消图片">✕</button>
          </div>
          <button class="icon-btn chat-image-btn" @click="triggerImageUpload" title="发送图片">🖼</button>
          <input type="file" ref="imageInputRef" accept="image/*" style="display:none" @change="handleImageSelect" />
          <button class="icon-btn chat-send-btn" @click="sendMessage" :disabled="!socket || (!draftMessage.trim() && !pendingImageUrl)" title="发送">➤</button>
        </div>
      </div>
    </div>

    <div
      v-for="direction in resizeDirections"
      v-show="true"
      :key="direction"
      :class="['chat-resize-handle', `chat-resize-${direction}`]"
      @mousedown="$emit('startResize', $event, direction)"
    ></div>
  </aside>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  visible: Boolean,
  interaction: Object,
  panelStyle: Object,
  socket: [Object, null],
  isMaximized: Boolean,
  rooms: Array,
  messages: Array,
  clients: Array,
  roomMembers: Array,
  myClientId: String,
  activeRoomId: String,
  activePrivateId: String,
  resizeDirections: Array,
  unreadCount: Number,
  unreadMap: Object,
  joinedRooms: Object,
  myName: String,
  collapsed: Boolean,
  sidebarWidth: { type: Number, default: 160 },
})

const emit = defineEmits([
  'focus',
  'startMove',
  'toggleMaximize',
  'close',
  'createRoom',
  'joinRoom',
  'sendMessage',
  'selectPrivate',
  'startResize',
  'toggleCollapse',
  'leaveRoom',
  'deleteRoom',
  'renameRoom',
  'startSidebarResize',
  'clearMessages',
])

const draftMessage = ref('')
const messagesRef = ref(null)
const chatInputRef = ref(null)
const imageInputRef = ref(null)
const createRoomInputRef = ref(null)
const myName = computed(() => props.myName || '')
const sidebarCollapsed = ref(false)
const creatingRoom = ref(false)
const newRoomName = ref('')
const pendingImageUrl = ref('')
const renamingRoomId = ref('')
const renameRoomName = ref('')
const renameRoomInputRef = ref(null)

function handleRenameRoom(room) {
  renamingRoomId.value = room.room_id
  renameRoomName.value = room.name
  nextTick(() => {
    if (renameRoomInputRef.value) {
      renameRoomInputRef.value.focus()
      renameRoomInputRef.value.select()
    }
  })
}

function confirmRenameRoom() {
  const newName = renameRoomName.value.trim()
  if (!newName) return
  // 需要找到当前重命名的房间名做比较
  const room = props.rooms.find(r => r.room_id === renamingRoomId.value)
  if (room && newName === room.name) {
    cancelRenameRoom()
    return
  }
  emit('renameRoom', renamingRoomId.value, newName)
  cancelRenameRoom()
}

function cancelRenameRoom() {
  renamingRoomId.value = ''
  renameRoomName.value = ''
}

function sendMessage() {
  if (!draftMessage.value.trim() && !pendingImageUrl.value) return
  emit('sendMessage', draftMessage.value, pendingImageUrl.value)
  draftMessage.value = ''
  pendingImageUrl.value = ''
  // 重置输入框高度
  nextTick(() => {
    if (chatInputRef.value) {
      chatInputRef.value.style.height = 'auto'
    }
  })
}

function triggerImageUpload() {
  imageInputRef.value?.click()
}

async function handleImageSelect(event) {
  const file = event.target.files?.[0]
  if (!file) return
  await uploadChatImage(file)
  event.target.value = ''
}

async function handleChatPaste(event) {
  const items = event.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      event.preventDefault()
      const file = item.getAsFile()
      if (file) {
        await uploadChatImage(file)
      }
      return
    }
  }
}

async function uploadChatImage(file) {
  if (file.size > 20 * 1024 * 1024) {
    alert('图片大小不能超过 20MB')
    return
  }
  const reader = new FileReader()
  reader.onload = async (e) => {
    const base64Data = e.target.result
    try {
      const { host, port } = getGatewayAddress()
      const protocol = window.location.protocol === 'https:' ? 'https' : 'http'
      const url = `${protocol}://${host}:${port}/api/node/master/upload`
      const token = localStorage.getItem('jarvis_auth_token') || ''
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          file_name: file.name,
          file_data: base64Data,
        }),
      })
      const result = await response.json()
      if (result.success && result.data?.file_url) {
        // 将相对路径转换为完整 URL（uploads 挂载在后端网关）
        const fileUrl = result.data.file_url
        pendingImageUrl.value = fileUrl.startsWith('/uploads/')
          ? `${protocol}://${host}:${port}${fileUrl}`
          : fileUrl
      } else {
        alert('上传失败: ' + (result.error || '未知错误'))
      }
    } catch (error) {
      console.error('上传图片失败:', error)
      alert('上传图片失败: ' + error.message)
    }
  }
  reader.readAsDataURL(file)
}

function getGatewayAddress() {
  const saved = localStorage.getItem('jarvis_gateway_url') || '127.0.0.1:8000'
  const address = saved.trim()
  if (address.includes('://')) {
    try {
      const u = new URL(address)
      return { host: u.hostname, port: u.port || (u.protocol === 'https:' ? '443' : '80') }
    } catch { return { host: '127.0.0.1', port: '8000' } }
  }
  if (address.includes(':')) {
    const parts = address.split(':')
    return { host: parts[0], port: parts[1] }
  }
  return { host: address, port: '8000' }
}

function openImage(url) {
  window.open(url, '_blank')
}

// 自动调整输入框高度
function autoResizeInput() {
  const el = chatInputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

// 处理输入框键盘事件
function handleInputKeydown(event) {
  // Ctrl+Enter / Ctrl+D 发送
  if (event.ctrlKey && (event.key === 'Enter' || event.key.toLowerCase() === 'd')) {
    event.preventDefault()
    sendMessage()
    return
  }
}

// 显示创建聊天室输入框
function showCreateRoomInput() {
  creatingRoom.value = true
  newRoomName.value = ''
  nextTick(() => {
    if (createRoomInputRef.value) {
      createRoomInputRef.value.focus()
    }
  })
}

// 确认创建聊天室
function confirmCreateRoom() {
  const name = newRoomName.value.trim()
  if (!name) return
  emit('createRoom', name)
  creatingRoom.value = false
  newRoomName.value = ''
}

// 取消创建聊天室
function cancelCreateRoom() {
  creatingRoom.value = false
  newRoomName.value = ''
}

// 格式化消息时间
function formatTime(timestamp) {
  if (!timestamp) return ''
  // 兼容秒和毫秒两种时间戳单位
  const ts = timestamp > 1e12 ? timestamp : timestamp * 1000
  const date = new Date(ts)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  if (isToday) {
    return `${hh}:${mm}`
  }
  const MM = String(date.getMonth() + 1).padStart(2, '0')
  const DD = String(date.getDate()).padStart(2, '0')
  return `${MM}-${DD} ${hh}:${mm}`
}

// 自动滚动到底部
watch(
  () => props.messages?.length,
  async () => {
    await nextTick()
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  }
)
</script>

<style scoped>
.icon-btn {
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  color: var(--color-text-secondary);
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  transform: translateY(-1px);
}

.icon-btn:active:not(:disabled) {
  transform: translateY(0);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn.small {
  width: 24px;
  height: 24px;
  font-size: 14px;
}

.chat-panel {
  position: fixed;
  background: var(--color-bg-primary);
  border: none;
  border-radius: var(--tile-radius);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-panel-dragging {
  user-select: none;
}

/* 侧边栏展开按钮 */
.chat-sidebar-expand {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 100%;
  cursor: pointer;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  transition: background 0.2s;
}

.chat-sidebar-expand:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.chat-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  cursor: move;
  flex-shrink: 0;
}

.chat-panel-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-panel-title-group h3 {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-primary);
}

.chat-unread-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ff4d4f;
  color: #fff;
  font-size: 11px;
  font-weight: bold;
  line-height: 1;
  animation: chat-badge-pulse 1s ease-in-out infinite;
}

@keyframes chat-badge-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}

.chat-message-new {
  animation: chat-message-slide-in 0.4s ease-out;
  background: rgba(64, 158, 255, 0.08);
  border-radius: 6px;
}

@keyframes chat-message-slide-in {
  from {
    opacity: 0;
    transform: translateY(-8px);
    background: rgba(64, 158, 255, 0.25);
  }
  to {
    opacity: 1;
    transform: translateY(0);
    background: rgba(64, 158, 255, 0.08);
  }
}

.chat-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-username {
  flex: 1;
  margin: 0 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-body {
  display: flex;
  flex-direction: row;
  flex: 1;
  min-height: 0;
}

.chat-sidebar {
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  overflow: hidden;
}

.chat-sidebar-resize {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
  transition: background 0.2s;
}

.chat-sidebar-resize:hover {
  background: var(--color-accent);
}

.chat-users-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-top: 1px solid var(--color-border);
}

.chat-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.chat-sidebar-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* 创建聊天室内联输入框 */
.chat-create-room-inline {
  padding: 8px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-create-room-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  font-size: 13px;
  outline: none;
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.chat-create-room-input:focus {
  border-color: var(--color-accent, #4a9eff);
}

.chat-create-room-input::placeholder {
  color: var(--color-text-secondary);
}

.chat-create-room-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

.chat-create-confirm {
  color: var(--color-accent, #4a9eff) !important;
}

.chat-create-cancel {
  color: var(--color-text-secondary) !important;
}

/* 重命名聊天室内联输入框 */
.chat-rename-room-input {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  font-size: 12px;
}

.chat-room-list,
.chat-client-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.chat-room-item,
.chat-client-item {
  padding: 6px 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: var(--color-text-primary);
  transition: all 0.15s ease;
  border-left: 3px solid transparent;
}

.chat-room-item:hover,
.chat-client-item:hover {
  background: var(--color-bg-hover);
}

.chat-room-item.active {
  background: var(--color-bg-active);
  border-left: 3px solid var(--color-accent, #4a9eff);
  font-weight: 600;
}

.chat-client-item.active {
  background: var(--color-bg-active);
  border-left: 3px solid var(--color-accent, #4a9eff);
}

.chat-room-item.joined:not(.active) {
  background: var(--color-bg-secondary);
  border-left: 3px solid var(--color-primary, #4a9eff);
}

.chat-room-item:not(.joined) {
  opacity: 0.6;
}

.chat-room-name,
.chat-client-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.chat-room-unread,
.chat-client-unread {
  flex-shrink: 0;
  margin-left: 4px;
  font-size: 10px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
}

.chat-room-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.chat-room-action-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.chat-room-item:hover .chat-room-action-btn,
.chat-room-item.active .chat-room-action-btn {
  opacity: 1;
}

.chat-room-count {
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border-radius: 8px;
  padding: 1px 6px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-bottom: 1px solid var(--border-color, #333);
  flex-shrink: 0;
}

.chat-main-title {
  font-size: 12px;
  color: var(--text-secondary, #888);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.chat-message {
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.chat-message.mine {
  align-items: flex-end;
}

.chat-message-sender {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-bottom: 2px;
  padding: 0 4px;
}

.chat-message-bubble {
  max-width: 80%;
  border-radius: 8px;
  padding: 6px 10px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
}

.chat-message.mine .chat-message-bubble {
  background: var(--color-accent);
  color: #fff;
  border-color: var(--color-accent);
}

.chat-message-content {
  font-size: 13px;
  color: inherit;
  word-break: break-word;
  white-space: pre-wrap;
}

.chat-message-time {
  font-size: 10px;
  color: var(--color-text-secondary);
  margin-top: 2px;
  padding: 0 4px;
}

.chat-input-area {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px;
  border-top: 1px solid var(--color-border);
}

.chat-input {
  flex: 1;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--color-text-primary);
  outline: none;
  resize: none;
  overflow-y: auto;
  min-height: 36px;
  max-height: 120px;
  line-height: 1.5;
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: var(--color-accent, #4a9eff);
}

.chat-input::placeholder {
  color: var(--color-text-secondary);
}



.chat-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
  text-align: center;
}

.chat-resize-handle {
  position: absolute;
  z-index: 10;
}

.chat-resize-n {
  top: -3px;
  left: 0;
  right: 0;
  height: 6px;
  cursor: n-resize;
}

.chat-resize-s {
  bottom: -3px;
  left: 0;
  right: 0;
  height: 6px;
  cursor: s-resize;
}

.chat-resize-e {
  right: -3px;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: e-resize;
}

.chat-resize-w {
  left: -3px;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: w-resize;
}

.chat-resize-ne {
  top: -3px;
  right: -3px;
  width: 6px;
  height: 6px;
  cursor: ne-resize;
}

.chat-resize-nw {
  top: -3px;
  left: -3px;
  width: 6px;
  height: 6px;
  cursor: nw-resize;
}

.chat-resize-se {
  bottom: -3px;
  right: -3px;
  width: 6px;
  height: 6px;
  cursor: se-resize;
}

.chat-resize-sw {
  bottom: -3px;
  left: -3px;
  width: 6px;
  height: 6px;
  cursor: sw-resize;
}
.chat-image-btn {
  color: var(--text-secondary, #888);
  font-size: 1.1em;
  padding: 4px 6px;
}
.chat-image-btn:hover {
  color: var(--accent-color, #4a9eff);
}

.chat-message-image {
  max-width: 280px;
  max-height: 280px;
  border-radius: 8px;
  cursor: pointer;
  display: block;
  margin-bottom: 4px;
  object-fit: contain;
}
.chat-message-image:hover {
  opacity: 0.85;
}
.chat-pending-image-wrapper {
  position: relative;
  display: inline-block;
  margin: 4px 0;
}
.chat-pending-image {
  max-width: 120px;
  max-height: 80px;
  border-radius: 6px;
  object-fit: contain;
  border: 2px solid var(--accent-color, #4a9eff);
}
.chat-pending-image-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e74c3c;
  color: #fff;
  border: none;
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
}
.chat-pending-image-remove:hover {
  background: #c0392b;
}
</style>