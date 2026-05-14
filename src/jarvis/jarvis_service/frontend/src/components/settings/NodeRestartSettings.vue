<template>
  <!-- 节点重启服务 -->
  <div class="form-group" v-if="availableNodeOptions.length > 0">
    <label>重启节点服务</label>
    <select v-model="localRestartNodeId" class="node-select">
      <option value="">本节点 (master)</option>
      <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
        {{ formatNodeOptionLabel(node) }}
      </option>
    </select>
    <span class="form-help">选择要重启服务的节点，默认为本节点</span>
  </div>

  <div class="form-group" v-if="!localRestartNodeId || localRestartNodeId === 'master'">
    <label class="checkbox-label">
      <input type="checkbox" v-model="localRestartFrontendService" />
      <span>同时重启前端服务</span>
    </label>
    <span class="form-help">前端服务重启时间较长，通常只需重启后端</span>
  </div>
  <div class="form-group">
    <button class="ghost-btn" @click="confirmRestartGateway" :disabled="isRestartingGateway">
      {{ isRestartingGateway ? '请稍候...' : (localRestartNodeId ? `重启节点 ${localRestartNodeId} 服务` : '重启本节点服务') }}
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

/**
 * 节点重启设置组件
 * 包含节点选择、前端服务重启选项和重启按钮
 */
const props = defineProps({
  availableNodeOptions: {
    type: Array,
    default: () => []
  },
  isRestartingGateway: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'confirmRestartGateway'
])

// 本地状态
const localRestartNodeId = ref('')
const localRestartFrontendService = ref(false)

// 格式化节点选项标签
function formatNodeOptionLabel(node) {
  const nodeId = String(node?.node_id || '').trim()
  const status = String(node?.status || node?.runtime_status || '').trim()
  return status ? `${nodeId} (${status})` : nodeId
}

// 确认重启网关
function confirmRestartGateway() {
  emit('confirmRestartGateway', {
    nodeId: localRestartNodeId.value,
    restartFrontend: localRestartFrontendService.value
  })
}
</script>

<style scoped>
/* 使用全局样式，无需额外样式 */
</style>