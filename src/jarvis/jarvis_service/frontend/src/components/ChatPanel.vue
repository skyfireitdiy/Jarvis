<template>
  <aside
    v-show="visible"
    class="chat-panel"
    :class="{ 'chat-panel-dragging': interaction.active }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'chat')"
  >
    <div v-show="!collapsed" class="chat-panel-header" @mousedown="$emit('startMove', $event)" @dblclick.stop="$emit('toggleMaximize')">
      <div class="chat-panel-title-group">
        <h3>聊天室</h3>
        <span v-if="unreadCount > 0" class="chat-unread-badge">{{ unreadCount }}</span>
      </div>
      <button class="icon-btn small chat-collapse-btn" @click.stop="$emit('toggleCollapse')" :title="collapsed ? '展开侧边栏' : '收起侧边栏'">
        {{ collapsed ? '▶' : '◀' }}
      </button>
      <div class="chat-name-edit">
        <input
          v-model="myName"
          class="chat-name-input"
          placeholder="输入昵称..."
          @keyup.enter="saveName"
        />
        <button class="icon-btn small chat-name-confirm" @click="saveName" title="确认昵称">✓</button>
      </div>
      <div class="chat-panel-actions">
        <button class="icon-btn" @click="$emit('toggleMaximize')" :title="isMaximized ? '还原' : '最大化'">
          {{ isMaximized ? '🗗' : '🗖' }}
        </button>
        <button class="icon-btn" @click="$emit('close')" title="关闭面板">✕</button>
      </div>
    </div>

    <!-- 折叠状态：只显示窄条 -->
    <div v-if="collapsed" class="chat-collapsed-bar" @click="$emit('toggleCollapse')" title="展开侧边栏">
      <span>💬</span>
    </div>

    <!-- 主体区域：侧边栏 + 消息区 横向排列 -->
    <div v-show="!collapsed" class="chat-body">
      <!-- 左侧侧边栏：聊天室列表 + 在线用户列表 -->
      <div class="chat-sidebar" :style="{ width: sidebarWidth + 'px' }">
        <div class="chat-sidebar-header">
          <span>聊天室</span>
          <button class="icon-btn small" @click="$emit('createRoom')" title="创建聊天室">➕</button>
        </div>
        <div class="chat-room-list">
          <div
            v-for="room in rooms"
            :key="room.room_id"
            class="chat-room-item"
            :class="{ active: activeRoomId === room.room_id, joined: joinedRooms?.includes?.(room.room_id) }"
            @click="$emit('joinRoom', room.room_id)"
          >
            <span class="chat-room-name">{{ room.name }}</span>
            <span v-if="unreadMap[room.room_id]" class="chat-unread-badge chat-room-unread">{{ unreadMap[room.room_id] }}</span>
            <div class="chat-room-actions">
              <span class="chat-room-count">{{ room.member_count }}</span>
              <button v-if="activeRoomId === room.room_id" class="icon-btn small chat-room-action-btn" @click.stop="$emit('leaveRoom', room.room_id)" title="退出聊天室">🚪</button>
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
              <span class="chat-client-name">{{ member.name }}</span>
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
              <span class="chat-client-name">{{ client.name }}</span>
              <span v-if="unreadMap['private_' + client.client_id]" class="chat-unread-badge chat-client-unread">{{ unreadMap['private_' + client.client_id] }}</span>
            </div>
            <div v-if="clients.length === 0" class="chat-empty">暂无在线用户</div>
          </div>
        </div>
      </div>

      <!-- 侧边栏拖拽调整宽度 -->
      <div class="chat-sidebar-resize" @mousedown="$emit('startSidebarResize', $event)"></div>

      <!-- 消息区域 -->
      <div class="chat-main">
        <div class="chat-messages" ref="messagesRef">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            class="chat-message"
            :class="{ mine: msg.client_id === myClientId, 'chat-message-new': idx === messages.length - 1 && msg.client_id !== myClientId }"
          >
            <span class="chat-message-sender">{{ msg.sender_name }}</span>
            <div class="chat-message-bubble">
              <span class="chat-message-content">{{ msg.content }}</span>
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
            placeholder="输入消息... (Enter发送, Shift+Enter换行)"
            rows="2"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.enter.shift.prevent="insertNewline"
          ></textarea>
          <button class="icon-btn" @click="sendMessage" :disabled="!socket" title="发送">➤</button>
        </div>
      </div>
    </div>

    <div
      v-for="direction in resizeDirections"
      v-show="!collapsed"
      :key="direction"
      :class="['chat-resize-handle', `chat-resize-${direction}`]"
      @mousedown="$emit('startResize', $event, direction)"
    ></div>
  </aside>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

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
  'updateName',
  'toggleCollapse',
  'leaveRoom',
  'deleteRoom',
  'startSidebarResize',
])

const draftMessage = ref('')
const messagesRef = ref(null)
const myName = ref(props.myName || '')

// 同步父组件传入的myName变化
watch(() => props.myName, (val) => {
  if (val !== undefined && val !== myName.value) {
    myName.value = val
  }
})

// 保存自定义名字
function saveName() {
  const name = myName.value.trim()
  if (name) {
    emit('updateName', name)
  }
}

function sendMessage() {
  if (!draftMessage.value.trim()) return
  emit('sendMessage', draftMessage.value)
  draftMessage.value = ''
}

// Shift+Enter 插入换行
function insertNewline() {
  draftMessage.value += '\n'
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

// 监听外部名字变化
watch(
  () => props.myName,
  (val) => {
    if (val) myName.value = val
  }
)

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

.chat-collapsed-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 100%;
  cursor: pointer;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  flex-shrink: 0;
  font-size: 18px;
  color: var(--color-text-secondary);
  transition: background 0.2s;
}

.chat-collapsed-bar:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.chat-collapse-btn {
  width: 24px;
  height: 24px;
  font-size: 12px;
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

.chat-name-edit {
  flex: 1;
  margin: 0 8px;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-name-confirm {
  flex-shrink: 0;
  color: var(--color-accent);
}

.chat-name-input {
  width: 100%;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  padding: 3px 8px;
  font-size: 12px;
  color: var(--color-text-primary);
  outline: none;
}

.chat-name-input:focus {
  border: 1px solid var(--color-accent);
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
}

.chat-room-item:hover,
.chat-client-item:hover {
  background: var(--color-bg-hover);
}

.chat-room-item.active,
.chat-client-item.active {
  background: var(--color-bg-active);
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
  border: none;
  border-radius: var(--tile-radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--color-text-primary);
  outline: none;
  resize: none;
  min-height: 32px;
  max-height: 80px;
  line-height: 1.4;
  font-family: inherit;
}

.chat-input:focus {
  border: 1px solid var(--color-accent);
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
</style>