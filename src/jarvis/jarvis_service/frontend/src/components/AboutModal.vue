<template>
  <!-- 关于弹窗 -->
  <div class="modal-overlay" v-if="visible" @click.self="close">
    <div class="modal about-modal">
      <div class="modal-header">
        <h2>关于</h2>
        <button class="close-btn" @click="close">×</button>
      </div>

      <!-- 软件信息 -->
      <div class="about-brand">
        <div class="about-logo">J</div>
        <div class="about-title">Jarvis Web Gateway</div>
        <div class="about-subtitle">版本 {{ frontendVersion }}<span v-if="backendVersion && backendVersion !== frontendVersion"> / 后端 {{ backendVersion }}</span></div>
        <div class="about-meta">
          <span class="about-tag">MIT 开源协议</span>
          <span class="about-tag">作者：skyfire</span>
        </div>
      </div>

      <!-- 各节点版本 -->
      <div class="form-group">
        <label>节点版本</label>
        <div v-if="nodes.length" class="about-list">
          <div v-for="node in nodes" :key="node.node_id" class="about-item">
            <span class="about-item-name">{{ node.node_id }}</span>
            <span class="about-item-value">{{ node.version || '-' }}</span>
            <span class="about-item-status" :class="{ online: node.status === 'online' || node.status === 'running' }">{{ node.status || '-' }}</span>
          </div>
        </div>
        <div v-else class="about-empty">暂无节点信息</div>
      </div>

      <!-- 后台服务（daemon）版本 -->
      <div class="form-group">
        <label>后台服务（daemon）版本</label>
        <div v-if="daemonSessions.length" class="about-list">
          <div v-for="daemon in daemonSessions" :key="daemon.session_id" class="about-item">
            <span class="about-item-name">{{ daemon.name || daemon.hostname || daemon.session_id }}</span>
            <span class="about-item-value">{{ daemon.daemon_version || '-' }}</span>
            <span class="about-item-detail">{{ daemon.platform || '' }}</span>
          </div>
        </div>
        <div v-else class="about-empty">暂无在线后台服务</div>
      </div>

      <!-- 浏览器扩展版本 -->
      <div class="form-group">
        <label>浏览器扩展版本</label>
        <div v-if="browserExtSessions.length" class="about-list">
          <div v-for="ext in browserExtSessions" :key="ext.session_id" class="about-item">
            <span class="about-item-name">{{ ext.name || ext.session_id }}</span>
            <span class="about-item-value">{{ ext.extension_version || '-' }}</span>
            <span class="about-item-detail">{{ ext.browser_info?.name || '' }}</span>
          </div>
        </div>
        <div v-else class="about-empty">暂无在线浏览器扩展</div>
      </div>

      <div class="modal-actions">
        <button class="ghost-btn" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  visible: { type: Boolean, default: false },
  frontendVersion: { type: String, default: '' },
  backendVersion: { type: String, default: '' },
  nodes: { type: Array, default: () => [] },
  daemonSessions: { type: Array, default: () => [] },
  browserExtSessions: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:visible'])

function close() {
  emit('update:visible', false)
}
</script>

<style scoped>
.about-modal {
  max-width: 460px;
}
.about-brand {
  text-align: center;
  padding: 8px 0 20px;
  border-bottom: 1px solid rgba(139, 163, 184, 0.15);
  margin-bottom: 20px;
}
.about-logo {
  width: 52px;
  height: 52px;
  margin: 0 auto 12px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--color-accent, #4f8cff), #7c5cff);
  color: #fff;
  font-size: 28px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.about-title {
  font-size: 18px;
  font-weight: 600;
  color: #e6edf3;
}
.about-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #8ba3b8;
}
.about-meta {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}
.about-tag {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(79, 140, 255, 0.12);
  color: #8fb4ff;
  font-size: 12px;
}
.about-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.about-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  background: var(--color-bg-tertiary);
  border-radius: 8px;
  font-size: 13px;
}
.about-item-name {
  flex: 1;
  color: #e6edf3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.about-item-value {
  color: #8fb4ff;
  font-weight: 600;
  white-space: nowrap;
}
.about-item-detail {
  color: #8ba3b8;
  font-size: 12px;
  white-space: nowrap;
}
.about-item-status {
  color: #8ba3b8;
  font-size: 12px;
  white-space: nowrap;
}
.about-item-status.online {
  color: #4ade80;
}
.about-empty {
  color: #8ba3b8;
  font-size: 13px;
  padding: 8px 0;
}
</style>
