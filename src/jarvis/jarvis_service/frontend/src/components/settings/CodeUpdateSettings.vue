<template>
  <!-- 代码更新 -->
  <div class="form-group">
    <label>代码更新</label>
    <span class="form-help">将所有节点的 Jarvis 代码切换到 main 分支并拉取最新代码</span>
    <button class="ghost-btn" @click="updateCodeToMain" :disabled="isUpdatingCode">
      {{ isUpdatingCode ? '更新中...' : '更新代码到 main 分支' }}
    </button>
  </div>
</template>

<script setup>
/**
 * 代码更新设置组件
 * 包含代码更新按钮和状态显示
 */
const props = defineProps({
  isUpdatingCode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'confirmUpdateCodeToMain'
])

// 更新代码到 main 分支
function updateCodeToMain() {
  emit('confirmUpdateCodeToMain')
}
</script>

<style scoped>
/* 使用全局样式，无需额外样式 */
</style>