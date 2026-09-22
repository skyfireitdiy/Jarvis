<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal session-modal">
      <div class="modal-header">
        <h2>选择会话恢复</h2>
        <button class="close-btn" @click="$emit('cancel')">×</button>
      </div>
      <div class="session-search" v-if="sessions.length > 0">
        <input
          v-model="query"
          type="text"
          placeholder="搜索会话名称…"
          class="session-search-input"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
      <div class="session-list" v-if="filteredSessions.length > 0">
        <div
          v-for="session in filteredSessions"
          :key="session.file"
          class="session-item"
          :class="{ active: selectedSession === session.file }"
          @click="$emit('update:selectedSession', session.file)"
        >
          <div class="session-name">{{ session.name || '未命名会话' }}</div>
          <div class="session-time">{{ session.timestamp }}</div>
        </div>
      </div>
      <div class="empty-state" v-else>
        <p v-if="sessions.length > 0 && query">没有匹配「{{ query }}」的会话</p>
        <p v-else>没有可恢复的会话</p>
      </div>
      <div class="modal-actions">
        <button class="ghost-btn" @click="$emit('cancel')">跳过</button>
        <button class="primary-btn" @click="$emit('restore', selectedSession)" :disabled="!selectedSession">
          恢复会话
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
const props = defineProps({
  visible: Boolean,
  sessions: {
    type: Array,
    default: () => []
  },
  selectedSession: {
    type: String,
    default: null
  }
})

defineEmits(['update:visible', 'update:selectedSession', 'restore', 'cancel'])

// 搜索关键词（大小写不敏感，匹配会话名称/时间戳/文件名）
const query = ref('')
// 按关键词过滤后的会话列表
const filteredSessions = computed(() => {
  const q = String(query.value || '').trim().toLowerCase()
  if (!q) return props.sessions
  return (props.sessions || []).filter((s) => {
    const haystack = [s?.name, s?.timestamp, s?.file].filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(q)
  })
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3000;
  padding: 20px;
}

.modal {
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius-sm);
  padding: 28px;
  width: 100%;
}

.session-modal {
  max-width: 450px;
  width: 90%;
}

.session-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--color-text-primary);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.close-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.close-btn:hover {
  color: var(--color-text-primary);
}

.session-list {
  max-height: 300px;
  overflow-y: auto;
  background: var(--color-bg-primary);
  border-radius: var(--tile-radius);
  border: none;
  margin-bottom: 20px;
}

.session-search {
  margin-bottom: 12px;
}

.session-search-input {
  width: 100%;
  padding: 10px 14px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
}

.session-search-input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-primary);
}

.session-item {
  padding: 12px 14px;
  border-bottom: 0.5px solid var(--color-border-subtle);
  cursor: pointer;
  border-radius: var(--tile-radius-xs);
  margin: 4px;
}

.session-item:last-child {
  border-bottom: none;
}

.session-item:hover {
  background: var(--color-bg-tertiary);
}

.session-item.active {
  background: var(--color-accent-subtle);
  border-color: var(--color-accent);
}

.session-name {
  font-size: 14px;
  color: var(--color-text-primary);
  font-weight: 500;
  margin-bottom: 4px;
}

.session-time {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: var(--color-text-secondary);
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.ghost-btn {
  padding: 10px 20px;
  background: transparent;
  border: none;
  border-radius: var(--tile-radius);
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.primary-btn {
  padding: 10px 20px;
  background: var(--color-success);
  border: none;
  border-radius: var(--tile-radius);
  color: #060911;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.primary-btn:hover:not(:disabled) {
  background: var(--color-success);
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>