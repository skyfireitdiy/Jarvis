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
      </div>
      <div class="chat-panel-actions">
        <button class="icon-btn" @click="$emit('toggleMaximize')" :title="isMaximized ? '还原' : '最大化'">
          {{ isMaximized ? '🗗' : '🗖' }}
        </button>
        <button class="icon-btn" @click="$emit('close')" title="关闭面板">✕</button>
      </div>
    </div>

    <!-- 聊天室列表 -->
    <div class="chat-sidebar">
      <div class="chat-sidebar-header">
        <span>聊天室</span>
        <button class="icon-btn small" @click="$emit('createRoom')" title="创建聊天室">➕</button>
      </div>
      <div class="chat-room-list">
        <div
          v-for="room in rooms"
          :key="room.room_id"
          class="chat-room-item"
          :class="{ active: activeRoomId === room.room_id }"
          @click="$emit('joinRoom', room.room_id)"
        >
          <span class="chat-room-name">{{ room.name }}</span>
          <span class="chat-room-count">{{ room.member_count }}</span>
        </div>
        <div v-if="rooms.length === 0" class="chat-empty">暂无聊天室</div>
      </div>
    </div>

    <!-- 消息区域 -->
    <div class="chat-main">
      <div class="chat-messages" ref="messagesRef">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="chat-message"
          :class="{ mine: msg.client_id === myClientId }"
        >
          <span class="chat-message-sender">{{ msg.sender_name }}</span>
          <span class="chat-message-content">{{ msg.content }}</span>
        </div>
        <div v-if="messages.length === 0" class="chat-empty">暂无消息</div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <input
          v-model="draftMessage"
          class="chat-input"
          placeholder="输入消息..."
          @keyup.enter="sendMessage"
        />
        <button class="icon-btn" @click="sendMessage" :disabled="!socket" title="发送">➤</button>
      </div>
    </div>

    <!-- 在线终端列表 -->
    <div class="chat-clients-panel">
      <div class="chat-sidebar-header">
        <span>在线终端</span>
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
        </div>
        <div v-if="clients.length === 0" class="chat-empty">暂无在线终端</div>
      </div>
    </div>

    <div
      v-for="direction in resizeDirections"
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
  myClientId: String,
  activeRoomId: String,
  activePrivateId: String,
  resizeDirections: Array
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
  'startResize'
])

const draftMessage = ref('')
const messagesRef = ref(null)

function sendMessage() {
  if (!draftMessage.value.trim()) return
  emit('sendMessage', draftMessage.value)
  draftMessage.value = ''
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

.chat-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chat-sidebar {
  width: 160px;
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
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

.chat-room-name,
.chat-client-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
}

.chat-message.mine {
  align-items: flex-end;
}

.chat-message-sender {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-bottom: 2px;
}

.chat-message-content {
  font-size: 13px;
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  border-radius: 8px;
  padding: 4px 8px;
  max-width: 80%;
  word-break: break-word;
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
}

.chat-input:focus {
  border: 1px solid var(--color-accent);
}

.chat-clients-panel {
  width: 140px;
  border-left: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
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