<template>
  <aside class="manage-sidebar">
    <div class="manage-sidebar-header">
      <h3 class="manage-sidebar-title">定时任务</h3>
    </div>
    <!-- 定时任务（只读展示，会频繁变化，单独入口） -->
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
          <div class="manage-timer-node">节点：{{ getNodeDisplayName(task.node_id) }}</div>
          <div class="manage-timer-schedule">{{ formatSchedule(task) }}</div>
          <div v-if="actionSummary(task)" class="manage-timer-content" :title="actionDetail(task)">
            {{ actionSummary(task) }}
          </div>
          <div v-if="!task.cancelled" class="manage-timer-next">下次触发：{{ formatRunAt(task.run_at) }}</div>
          <div class="manage-timer-actions">
            <button
              class="manage-timer-delete"
              title="删除此定时任务"
              @click="confirmDeleteTimer(task)"
            >删除</button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>

defineProps({
  // 定时任务列表：{task_id, run_at(ISO), interval_seconds, is_recurring, cancelled,
  //   metadata:{action:{type,params}, schedule:{type,run_at,delay_seconds,interval_seconds,cron}}}
  timers: { type: Array, default: () => [] },
  // 节点展示名解析函数：传入 node_id 返回展示名（默认回退 node_id / 'master'）
  getNodeDisplayName: { type: Function, default: (nodeId) => String(nodeId || '').trim() || 'master' }
})

const emit = defineEmits(['delete-timer'])

const ACTION_LABELS = {
  create_agent: '创建 Agent',
  run_shell_command: '执行命令',
  capability_call: '调用能力'
}

function actionLabel(task) {
  const type = task?.metadata?.action?.type
  return ACTION_LABELS[type] || type || '未知'
}

// 定时任务动作内容摘要（列表展示）
function actionSummary(task) {
  const action = task?.metadata?.action
  if (!action) return ''
  const params = action.params || {}
  switch (action.type) {
    case 'run_shell_command':
      return params.command || ''
    case 'create_agent':
      return params.task || params.name || ''
    case 'capability_call':
      return params.capability || ''
    default:
      return ''
  }
}

// 定时任务动作完整内容（悬浮提示）
function actionDetail(task) {
  const action = task?.metadata?.action
  if (!action) return ''
  const params = action.params || {}
  try {
    return JSON.stringify(params, null, 2)
  } catch (e) {
    return String(params)
  }
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

// 删除定时任务：交给父组件处理（父组件负责确认弹窗与 master / 子节点删除路径）
function confirmDeleteTimer(task) {
  if (!task || !task.task_id) return
  emit('delete-timer', task)
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

.manage-timer-node {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-bottom: 2px;
}

.manage-timer-actions {
  margin-top: 6px;
  text-align: right;
}

.manage-timer-delete {
  font-size: 11px;
  padding: 2px 10px;
  border: 1px solid var(--color-danger, #f56c6c);
  border-radius: 3px;
  background: transparent;
  color: var(--color-danger, #f56c6c);
  cursor: pointer;
}

.manage-timer-delete:hover {
  background: var(--color-danger, #f56c6c);
  color: #fff;
}

.manage-timer-schedule {
  font-size: 12px;
  color: var(--color-text-primary);
}

.manage-timer-content {
  margin-top: 4px;
  padding: 4px 6px;
  font-size: 11px;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manage-timer-next {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}
</style>
