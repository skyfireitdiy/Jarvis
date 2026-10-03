<template>
  <aside class="manage-sidebar">
    <div class="manage-sidebar-header">
      <h3 class="manage-sidebar-title">{{ view === 'timers' ? '定时任务' : '增强能力清单' }}</h3>
      <button
        v-if="view !== 'timers'"
        class="manage-sidebar-refresh"
        tabindex="-1"
        title="刷新增强能力清单"
        @click="$emit('refresh')"
      >⟳</button>
    </div>

    <!-- 定时任务（只读展示，会频繁变化，单独入口） -->
    <template v-if="view === 'timers'">
      <div class="manage-sidebar-content">
        <div v-if="!timers || timers.length === 0" class="manage-sidebar-empty">
          暂无定时任务
        </div>
        <div v-else class="manage-timer-list">
          <div v-for="task in timers" :key="task.task_id" class="manage-timer-item">
            <div class="manage-timer-head">
              <span class="manage-timer-type">{{ actionLabel(task) }}</span>
              <span class="manage-timer-status" :class="{ cancelled: !!task.cancelled }">
                {{ task.cancelled ? '已取消' : '运行中' }}
              </span>
            </div>
            <div class="manage-timer-id" :title="task.task_id">{{ shortTaskId(task.task_id) }}</div>
            <div class="manage-timer-schedule">{{ formatSchedule(task) }}</div>
            <div v-if="!task.cancelled" class="manage-timer-next">下次触发：{{ formatRunAt(task.run_at) }}</div>
          </div>
        </div>
      </div>
    </template>

    <!-- 能力清单（只读展示，缓存 + 手动刷新） -->
    <template v-else>
      <div class="manage-sidebar-content">
        <div
          v-if="(!daemonSessions || daemonSessions.length === 0) && (!extensionSessions || extensionSessions.length === 0) && (!installedScripts || installedScripts.length === 0) && (!gatewayScripts || gatewayScripts.length === 0)"
          class="manage-sidebar-empty"
        >暂无可用能力</div>

        <!-- Daemon 能力 -->
        <div v-if="daemonSessions && daemonSessions.length" class="manage-section">
          <div class="manage-section-title">Daemon 能力</div>
          <div class="manage-capability-list">
            <div
              v-for="session in daemonSessions"
              :key="session.session_id"
              class="manage-session"
            >
              <button
                class="manage-session-head"
                @click="toggleSession(session.session_id)"
              >
                <span class="manage-session-arrow">{{ isSessionExpanded(session.session_id) ? '▼' : '▶' }}</span>
                <span class="manage-session-name">{{ session.name || session.hostname || session.session_id }}</span>
                <span class="manage-session-meta">
                  {{ session.platform || 'unknown' }} · {{ session.daemon_version || '?' }}
                </span>
              </button>
              <div v-if="isSessionExpanded(session.session_id)" class="manage-session-body">
                <div v-if="!session.capabilities || session.capabilities.length === 0" class="manage-session-empty">
                  该会话未注册能力
                </div>
                <div
                  v-for="cap in session.capabilities || []"
                  :key="cap.name"
                  class="manage-capability"
                >
                  <button
                    class="manage-capability-head"
                    @click="toggleCapability(session.session_id, cap.name)"
                  >
                    <span class="manage-capability-arrow">{{ isCapabilityExpanded(session.session_id, cap.name) ? '▼' : '▶' }}</span>
                    <span class="manage-capability-name">{{ cap.name }}</span>
                    <span v-if="cap.platform" class="manage-capability-badge">{{ cap.platform }}</span>
                  </button>
                  <div v-if="isCapabilityExpanded(session.session_id, cap.name)" class="manage-capability-body">
                    <p v-if="cap.description" class="manage-capability-desc">{{ cap.description }}</p>
                    <div v-if="cap.parameters && Object.keys(cap.parameters).length" class="manage-capability-params">
                      <div class="manage-capability-params-title">参数</div>
                      <pre class="manage-capability-params-json">{{ formatParams(cap.parameters) }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 浏览器扩展 -->
        <div v-if="extensionSessions && extensionSessions.length" class="manage-section">
          <div class="manage-section-title">浏览器扩展</div>
          <div class="manage-capability-list">
            <div
              v-for="session in extensionSessions"
              :key="session.session_id"
              class="manage-session"
            >
              <button
                class="manage-session-head"
                @click="toggleSession('ext-' + session.session_id)"
              >
                <span class="manage-session-arrow">{{ isSessionExpanded('ext-' + session.session_id) ? '▼' : '▶' }}</span>
                <span class="manage-session-name">{{ session.name || '浏览器扩展' }}</span>
                <span class="manage-session-meta">
                  {{ browserLabel(session) }} · v{{ session.extension_version || '?' }}
                </span>
              </button>
              <div v-if="isSessionExpanded('ext-' + session.session_id)" class="manage-session-body">
                <div v-if="session.browser_info && Object.keys(session.browser_info).length" class="manage-capability-desc">
                  {{ formatBrowserInfo(session.browser_info) }}
                </div>
                <!-- 扩展能力清单（与 daemon 能力格式一致，由扩展动态上报） -->
                <div v-if="!session.capabilities || session.capabilities.length === 0" class="manage-session-empty">
                  该扩展未上报能力
                </div>
                <div
                  v-for="cap in session.capabilities || []"
                  :key="cap.name"
                  class="manage-capability"
                >
                  <button
                    class="manage-capability-head"
                    @click="toggleCapability('ext-' + session.session_id, cap.name)"
                  >
                    <span class="manage-capability-arrow">{{ isCapabilityExpanded('ext-' + session.session_id, cap.name) ? '▼' : '▶' }}</span>
                    <span class="manage-capability-name">{{ cap.name }}</span>
                    <span v-if="cap.platform" class="manage-capability-badge">{{ cap.platform }}</span>
                  </button>
                  <div v-if="isCapabilityExpanded('ext-' + session.session_id, cap.name)" class="manage-capability-body">
                    <p v-if="cap.description" class="manage-capability-desc">{{ cap.description }}</p>
                    <div v-if="cap.parameters && Object.keys(cap.parameters).length" class="manage-capability-params">
                      <div class="manage-capability-params-title">参数</div>
                      <pre class="manage-capability-params-json">{{ formatParams(cap.parameters) }}</pre>
                    </div>
                  </div>
                </div>
                <!-- 该扩展已安装的自定义脚本 -->
                <div v-if="getInstalledScripts(session.session_id).length" class="manage-scripts">
                  <div class="manage-capability-params-title">自定义脚本（{{ getInstalledScripts(session.session_id).length }}）</div>
                  <div v-for="script in getInstalledScripts(session.session_id)" :key="script.id || script.name" class="manage-script-item">
                    <div class="manage-script-head">
                      <span class="manage-script-name">{{ script.name }}</span>
                      <span class="manage-script-status" :class="{ disabled: script.enabled === false }">
                        {{ script.enabled === false ? '已停用' : '已启用' }}
                      </span>
                    </div>
                    <div v-if="script.description" class="manage-script-desc">{{ script.description }}</div>
                    <div class="manage-script-meta">
                      <span>v{{ script.version || '0.0.0' }}</span>
                      <span v-if="script.match && script.match.length" class="manage-script-match">{{ script.match.join(', ') }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 网关脚本库 -->
        <div v-if="gatewayScripts && gatewayScripts.length" class="manage-section">
          <div class="manage-section-title">网关脚本库</div>
          <div class="manage-gateway-scripts">
            <div v-for="s in gatewayScripts" :key="s.name" class="manage-script-item">
              <div class="manage-script-head">
                <span class="manage-script-name">{{ s.name }}</span>
                <span class="manage-script-status">{{ formatSize(s.size) }}</span>
              </div>
              <div class="manage-script-meta">
                <span>{{ formatDate(s.updated_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </aside>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  // 视图：'timers'（定时任务）或 'manage'（能力清单）
  view: { type: String, default: 'manage' },
  // 定时任务列表：{task_id, run_at(ISO), interval_seconds, is_recurring, cancelled,
  //   metadata:{action:{type,params}, schedule:{type,run_at,delay_seconds,interval_seconds,cron}}}
  timers: { type: Array, default: () => [] },
  // daemon 会话列表：{session_id, name, hostname, platform, daemon_version,
  //   capabilities:[{name, description, parameters, platform}]}
  daemonSessions: { type: Array, default: () => [] },
  // 浏览器扩展会话列表：{session_id, name, extension_version, browser_info, tabs}
  extensionSessions: { type: Array, default: () => [] },
  // 浏览器扩展已安装脚本：[{session_id, name, scripts:[{id,name,description,match,version,enabled}]}]
  installedScripts: { type: Array, default: () => [] },
  // 网关保存的脚本：[{name, size, updated_at}]
  gatewayScripts: { type: Array, default: () => [] }
})

defineEmits(['refresh'])

// 展开的会话 key 集合（daemon 用 session_id，浏览器扩展/脚本用前缀区分）
const expandedSessions = ref(new Set())
// 展开的能力 key：`${session_id}::${cap.name}` 集合
const expandedCapabilities = ref(new Set())

const ACTION_LABELS = {
  create_agent: '创建 Agent',
  run_shell_command: '执行命令',
  capability_call: '调用能力'
}

function actionLabel(task) {
  const type = task?.metadata?.action?.type
  return ACTION_LABELS[type] || type || '未知'
}

function shortTaskId(id) {
  if (!id) return ''
  return id.length > 8 ? id.slice(0, 8) : id
}

function formatRunAt(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString()
}

function formatSchedule(task) {
  const schedule = task?.metadata?.schedule
  if (schedule) {
    if (schedule.type === 'interval' && schedule.interval_seconds) {
      return `每 ${schedule.interval_seconds} 秒`
    }
    if (schedule.type === 'run_at' && schedule.run_at) {
      return `定时 ${formatRunAt(schedule.run_at)}`
    }
    if (schedule.type === 'delay' && schedule.delay_seconds != null) {
      return `延迟 ${schedule.delay_seconds} 秒`
    }
    if (schedule.type === 'cron' && schedule.cron) {
      return `cron: ${schedule.cron}`
    }
  }
  if (task?.interval_seconds) {
    return `每 ${task.interval_seconds} 秒`
  }
  if (task?.run_at) {
    return `定时 ${formatRunAt(task.run_at)}`
  }
  return '未知调度'
}

function formatParams(parameters) {
  try {
    return JSON.stringify(parameters, null, 2)
  } catch (e) {
    return String(parameters)
  }
}

function browserLabel(session) {
  const info = session.browser_info || {}
  return info.name || info.browser || '浏览器'
}

// 按 session_id 从 installedScripts 中取该扩展已安装的脚本列表
function getInstalledScripts(sessionId) {
  const found = (props.installedScripts || []).find((ext) => ext.session_id === sessionId)
  return (found && found.scripts) || []
}

function formatBrowserInfo(info) {
  const parts = []
  if (info.name) parts.push(info.name)
  if (info.version) parts.push(info.version)
  if (info.os) parts.push(info.os)
  return parts.join(' · ') || '未知浏览器'
}

function formatSize(size) {
  if (size == null) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString()
}

function toggleSession(key) {
  const next = new Set(expandedSessions.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedSessions.value = next
}

function isSessionExpanded(key) {
  return expandedSessions.value.has(key)
}

function toggleCapability(sessionId, capName) {
  const key = `${sessionId}::${capName}`
  const next = new Set(expandedCapabilities.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedCapabilities.value = next
}

function isCapabilityExpanded(sessionId, capName) {
  return expandedCapabilities.value.has(`${sessionId}::${capName}`)
}
</script>

<style scoped>
.manage-sidebar {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
  user-select: none;
}

.manage-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  min-height: 28px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.manage-sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.manage-sidebar-refresh {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.manage-sidebar-refresh:hover {
  color: var(--color-text-primary);
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.manage-sidebar-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

.manage-sidebar-empty {
  padding: 20px;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 13px;
}

/* —— 能力清单区块 —— */
.manage-section {
  margin-bottom: 12px;
}

.manage-section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
  padding: 0 2px;
}

/* —— 定时任务 —— */
.manage-timer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.manage-timer-item {
  padding: 8px 10px;
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  background: var(--color-bg-secondary);
}

.manage-timer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.manage-timer-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent);
}

.manage-timer-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--color-accent-subtle);
  color: var(--color-text-primary);
}

.manage-timer-status.cancelled {
  background: var(--color-danger, #f56c6c);
  color: #fff;
}

.manage-timer-id {
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-bottom: 2px;
}

.manage-timer-schedule {
  font-size: 12px;
  color: var(--color-text-primary);
}

.manage-timer-next {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

/* —— 会话/能力（daemon + 浏览器扩展共用） —— */
.manage-capability-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.manage-session {
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  background: var(--color-bg-secondary);
  overflow: hidden;
}

.manage-session-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.manage-session-head:hover {
  background: var(--color-accent-subtle);
}

.manage-session-arrow,
.manage-capability-arrow {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--color-text-secondary);
}

.manage-session-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manage-session-meta {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--color-text-secondary);
  font-weight: 400;
}

.manage-session-body {
  border-top: 1px solid var(--color-border-subtle);
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.manage-session-empty {
  padding: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.manage-capability {
  border-radius: 4px;
  overflow: hidden;
}

.manage-capability-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}

.manage-capability-head:hover {
  background: var(--color-accent-subtle);
}

.manage-capability-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
}

.manage-capability-badge {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--color-accent-subtle);
  color: var(--color-text-secondary);
}

.manage-capability-body {
  padding: 6px 8px 8px 20px;
  border-top: 1px solid var(--color-border-subtle);
}

.manage-capability-desc {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.manage-capability-params-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.manage-capability-params-json {
  margin: 0;
  padding: 6px 8px;
  border-radius: 4px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  overflow-x: auto;
  user-select: text;
}

/* —— 浏览器扩展标签页 —— */
.manage-tabs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 2px 0;
}

.manage-tab-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 6px;
  border-radius: 4px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
}

.manage-tab-title {
  font-size: 11px;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manage-tab-url {
  font-size: 10px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* —— 脚本扩展 —— */
.manage-gateway-scripts {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.manage-script-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 4px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
}

.manage-script-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.manage-script-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manage-script-status {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--color-accent-subtle);
  color: var(--color-text-primary);
}

.manage-script-status.disabled {
  background: var(--color-danger, #f56c6c);
  color: #fff;
}

.manage-script-desc {
  font-size: 11px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.manage-script-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: var(--color-text-secondary);
  overflow: hidden;
}

.manage-script-match {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
