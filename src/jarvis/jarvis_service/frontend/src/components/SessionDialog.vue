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