<template>
  <!-- 配置同步 -->
  <div class="form-group" v-if="availableNodeOptions.length > 0">
    <label>配置同步</label>
    <div class="config-sync-section">
      <div class="config-sync-row">
        <span class="config-sync-label">源节点:</span>
        <select v-model="localSyncConfigSourceNode" class="node-select">
          <option value="">本节点 (master)</option>
          <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
            {{ formatNodeOptionLabel(node) }}
          </option>
        </select>
      </div>
      <div class="form-group">
        <button class="ghost-btn" @click="syncConfig" :disabled="isSyncingConfig">
          {{ isSyncingConfig ? '同步中...' : '同步配置到其他节点' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

/**
 * 配置同步设置组件
 * 包含源节点选择和同步按钮
 */
const props = defineProps({
  availableNodeOptions: {
    type: Array,
    default: () => []
  },
  isSyncingConfig: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'syncConfig'
])

// 本地状态
const localSyncConfigSourceNode = ref('')

// 格式化节点选项标签
function formatNodeOptionLabel(node) {
  const nodeId = String(node?.node_id || '').trim()
  const status = String(node?.status || node?.runtime_status || '').trim()
  return status ? `${nodeId} (${status})` : nodeId
}

// 同步配置
function syncConfig() {
  emit('syncConfig', {
    sourceNodeId: localSyncConfigSourceNode.value
  })
}
</script>

<style scoped>
/* 使用全局样式，无需额外样式 */
</style>