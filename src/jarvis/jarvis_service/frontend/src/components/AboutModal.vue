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
        <div class="about-logo-wrap">
          <img src="/icons/jarvis-pet.svg" alt="Jarvis" class="about-logo" />
        </div>
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
/* 与 SettingsModal 保持一致的弹窗基础样式 */
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

.modal-overlay .modal {
  background: rgba(9, 16, 28, 0.86);
  border: 1px solid var(--color-border-subtle);
  border-radius: 14px;
  padding: 28px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.about-modal {
  max-width: 460px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 10px 14px;
  border-left: 2px solid var(--color-accent);
  border-radius: 10px;
  background: linear-gradient(160deg, rgba(32, 200, 255, 0.10) 0%, transparent 46%),
    var(--color-bg-tertiary);
}

.modal-header h2 {
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

.close-btn {
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius);
  font-size: 22px;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: var(--color-error-subtle);
  color: var(--color-error);
  transform: rotate(90deg);
}

.form-group {
  margin-bottom: 16px;
  padding: 16px;
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius-sm);
  box-shadow: 0 2px 8px var(--color-shadow);
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}

.ghost-btn {
  padding: 10px 20px;
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--color-border-subtle);
  transform: translateY(-1px);
}

/* 关于内容样式 */
.about-brand {
  text-align: center;
  padding: 8px 0 20px;
  border-bottom: 1px solid var(--color-border-subtle);
  margin-bottom: 20px;
}
.about-logo-wrap {
  position: relative;
  width: 52px;
  height: 52px;
  margin: 0 auto 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.about-logo {
  width: 46px;
  height: 46px;
  object-fit: contain;
  filter: drop-shadow(0 0 10px rgba(32, 200, 255, 0.55));
}
.about-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.about-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
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
  background: var(--color-accent-subtle);
  color: var(--color-accent);
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
  font-size: 14px;
  color: var(--color-text-primary);
}
.about-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.about-item-value {
  color: var(--color-accent);
  font-weight: 600;
  white-space: nowrap;
}
.about-item-detail {
  color: var(--color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}
.about-item-status {
  color: var(--color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}
.about-item-status.online {
  color: #4ade80;
}
.about-empty {
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 8px 0;
}
</style>
