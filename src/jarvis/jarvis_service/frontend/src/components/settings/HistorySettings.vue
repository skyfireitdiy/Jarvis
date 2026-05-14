<template>
  <!-- 历史消息管理组件 -->
  <div class="history-settings">
    <div class="form-group">
      <div class="history-info">
        <div class="history-stat">
          <span class="history-stat-label">历史消息数量:</span>
          <span class="history-stat-value">{{ historyStorage.getTotalCount() }}</span>
        </div>
        <div class="history-stat">
          <span class="history-stat-label">存储空间:</span>
          <span class="history-stat-value">{{ historyStorage.getStorageInfo().totalSizeFormatted }}</span>
        </div>
      </div>
    </div>
    <div class="form-group">
      <button class="danger-btn" @click="confirmClearHistory" :disabled="historyStorage.getTotalCount() === 0">
        清除历史记录
      </button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  historyStorage: {
    type: Object,
    required: true
  }
})

const emit = defineEmits([
  'confirmClearHistory'
])

// 确认清除历史
function confirmClearHistory() {
  emit('confirmClearHistory')
}
</script>

<style scoped>
/* 历史消息管理组件样式 */
.history-settings {
  margin-bottom: 16px;
}
</style>