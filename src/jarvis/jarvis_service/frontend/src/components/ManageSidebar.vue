<template>
  <aside class="manage-sidebar">
    <div class="manage-sidebar-header">
      <h3 class="manage-sidebar-title">管理</h3>
    </div>
    <div class="manage-sidebar-tabs">
      <button
        class="manage-sidebar-tab"
        :class="{ active: activeTab === 'timers' }"
        @click="activeTab = 'timers'"
      >定时任务</button>
      <button
        class="manage-sidebar-tab"
        :class="{ active: activeTab === 'capabilities' }"
        @click="activeTab = 'capabilities'"
      >Daemon 能力</button>
    </div>

    <!-- 定时任务（只读展示） -->
    <div v-if="activeTab === 'timers'" class="manage-sidebar-content">
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

    <!-- Daemon 能力（只读展示） -->
    <div v-else class="manage-sidebar-content">
      <div v-if="!daemonSessions || daemonSessions.length === 0" class="manage-sidebar-empty">
        暂无在线 daemon
      </div>
      <div v-else class="manage-capability-list">
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
  </aside>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  // 定时任务列表：{task_id, run_at(ISO), interval_seconds, is_recurring, cancelled,
  //   metadata:{action:{type,params}, schedule:{type,run_at,delay_seconds,interval_seconds}}}
  timers: { type: Array, default: () => [] },
  // daemon 会话列表：{session_id, name, hostname, platform, daemon_version,
  //   capabilities:[{name, description, parameters, platform}]}
  daemonSessions: { type: Array, default: () => [] }
})

const activeTab = ref('timers')
// 展开的会话 session_id 集合
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

function toggleSession(sessionId) {
  const next = new Set(expandedSessions.value)
  if (next.has(sessionId)) {
    next.delete(sessionId)
  } else {
    next.add(sessionId)
  }
  expandedSessions.value = next
}

function isSessionExpanded(sessionId) {
  return expandedSessions.value.has(sessionId)
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

.manage-sidebar-tabs {
  display: flex;
  gap: 2px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border-subtle);
  flex-shrink: 0;
}

.manage-sidebar-tab {
  flex: 1;
  padding: 4px 6px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.manage-sidebar-tab:hover {
  color: var(--color-text-primary);
  background: var(--color-accent-subtle);
}

.manage-sidebar-tab.active {
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

/* —— Daemon 能力 —— */
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
</style>
