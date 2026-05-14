<template>
  <!-- 连接管理 -->
  <div class="form-group">
    <label>连接管理</label>
    <div class="connection-management-section">
      <button class="danger-btn" @click="disconnectAll" :disabled="!socket">
        断开连接
      </button>
      <span class="form-help">断开所有 WebSocket 连接并刷新页面</span>
    </div>
  </div>
</template>

<script setup>
/**
 * 连接管理设置组件
 * 包含断开连接按钮
 */
const props = defineProps({
  socket: {
    type: Object,
    default: null
  }
})

const emit = defineEmits([
  'disconnectAll'
])

// 断开所有连接
function disconnectAll() {
  emit('disconnectAll')
}
</script>

<style scoped>
/* 使用全局样式，无需额外样式 */
</style>