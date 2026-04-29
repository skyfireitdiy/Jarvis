<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal session-modal">
      <div class="modal-header">
        <h2>选择会话恢复</h2>
        <button class="close-btn" @click="$emit('cancel')">×</button>
      </div>
      <div class="session-list" v-if="sessions.length > 0">
        <div
          v-for="session in sessions"
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
        <p>没有可恢复的会话</p>
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
defineProps({
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
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: rgba(22, 27, 34, 0.95);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 14px;
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
  color: #e6edf3;
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
  color: #8b949e;
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.close-btn:hover {
  color: #e6edf3;
}

.session-list {
  max-height: 300px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 20px;
}

.session-item {
  padding: 12px 14px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  border-radius: 6px;
  margin: 4px;
}

.session-item:last-child {
  border-bottom: none;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.session-item.active {
  background: rgba(63, 185, 80, 0.15);
  border-color: rgba(63, 185, 80, 0.3);
}

.session-name {
  font-size: 14px;
  color: #e6edf3;
  font-weight: 500;
  margin-bottom: 4px;
}

.session-time {
  font-size: 11px;
  color: #8b949e;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: #8b949e;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.ghost-btn {
  padding: 10px 20px;
  background: transparent;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #8b949e;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e6edf3;
}

.primary-btn {
  padding: 10px 20px;
  background: #238636;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.primary-btn:hover:not(:disabled) {
  background: #2ea043;
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>