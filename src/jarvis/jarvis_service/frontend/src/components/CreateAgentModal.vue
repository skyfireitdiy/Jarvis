<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal create-agent-modal">
      <h2>创建 Agent</h2>
      <div class="form-grid create-agent-layout">
        <div class="form-column create-agent-column create-agent-column-left">
          <div class="form-group" v-if="nodeOptions.length > 0">
            <label>目标节点</label>
            <select :value="nodeId" @change="$emit('update:nodeId', $event.target.value)" class="form-control">
              <option value="">默认节点（当前网关决定）</option>
              <option v-for="node in nodeOptions" :key="node.node_id" :value="node.node_id">
                {{ formatNodeLabel(node) }}
              </option>
            </select>
            <div class="form-help">未选择时使用默认节点；复制 Agent 时默认继承源节点。</div>
          </div>
          <div class="form-group">
            <label>Agent 类型</label>
            <div class="radio-group">
              <label class="radio-label">
                <input type="radio" :checked="agentType === 'agent'" @change="$emit('update:agentType', 'agent')" />
                <span class="radio-text">通用 Agent</span>
                <span class="radio-desc">适用于日常任务和通用操作</span>
              </label>
              <label class="radio-label">
                <input type="radio" :checked="agentType === 'codeagent'" @change="$emit('update:agentType', 'codeagent')" />
                <span class="radio-text">代码 Agent</span>
                <span class="radio-desc">专注于代码分析和开发任务</span>
              </label>
            </div>
          </div>
        </div>
        <div class="form-column create-agent-column create-agent-column-right">
          <div class="form-group">
            <label>Agent 名称（可选）</label>
            <input :value="agentName" @input="$emit('update:agentName', $event.target.value)" type="text" class="form-control" placeholder="例如：开发环境Agent" />
          </div>
          <div class="form-group">
            <label>模型组</label>
            <select :value="modelGroup" @change="$emit('update:modelGroup', $event.target.value)" class="form-control">
              <option v-for="group in modelGroups" :key="group.name" :value="group.name">
                {{ group.name }} ({{ group.smart_model }}, {{ group.normal_model }}, {{ group.cheap_model }})
              </option>
            </select>
          </div>
          <div class="form-group">
            <label>工作目录</label>
            <div class="input-with-button">
              <input :value="workDir" @input="$emit('update:workDir', $event.target.value)" type="text" class="form-control" placeholder="/path/to/workspace" />
              <button class="btn select-dir-btn" @click="$emit('selectDir')">选择目录</button>
            </div>
          </div>
          <div class="form-column create-agent-options-column">
            <div v-if="agentType === 'codeagent'" class="form-group">
              <div class="toggle-wrapper">
                <label class="toggle-switch">
                  <input :checked="codeAgentWorktree" @change="$emit('update:codeAgentWorktree', $event.target.checked)" type="checkbox" class="toggle-input" />
                  <span class="toggle-slider"></span>
                </label>
                <div class="toggle-info">
                  <span class="toggle-label-text">启用 worktree</span>
                  <span class="form-help">为代码 Agent 使用独立 git worktree 进行隔离开发。</span>
                </div>
              </div>
            </div>
            <div class="form-group">
              <div class="toggle-wrapper">
                <label class="toggle-switch">
                  <input :checked="quickMode" @change="$emit('update:quickMode', $event.target.checked)" type="checkbox" class="toggle-input" />
                  <span class="toggle-slider"></span>
                </label>
                <div class="toggle-info">
                  <span class="toggle-label-text">极速模式</span>
                  <span class="form-help">跳过任务分类、规则加载、上下文推荐等，直接执行任务。</span>
                </div>
              </div>
            </div>
            <div class="form-group">
              <div class="toggle-wrapper">
                <label class="toggle-switch">
                  <input :checked="restoreSession" @change="$emit('update:restoreSession', $event.target.checked)" type="checkbox" class="toggle-input" />
                  <span class="toggle-slider"></span>
                </label>
                <div class="toggle-info">
                  <span class="toggle-label-text">启动时恢复会话</span>
                  <span class="form-help">启动时自动恢复上次会话。</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn secondary" @click="$emit('cancel')">取消</button>
        <button class="btn primary" @click="$emit('create')" :disabled="!workDir.trim()">创建</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  visible: Boolean,
  nodeOptions: { type: Array, default: () => [] },
  nodeId: { type: String, default: '' },
  agentType: { type: String, default: 'codeagent' },
  agentName: { type: String, default: '' },
  modelGroups: { type: Array, default: () => [] },
  modelGroup: { type: String, default: 'default' },
  workDir: { type: String, default: '~' },
  codeAgentWorktree: { type: Boolean, default: false },
  quickMode: { type: Boolean, default: false },
  restoreSession: { type: Boolean, default: false },
  formatNodeLabel: { type: Function, default: (node) => node.node_id }
})

const emit = defineEmits([
  'update:nodeId',
  'update:agentType',
  'update:agentName',
  'update:modelGroup',
  'update:workDir',
  'update:codeAgentWorktree',
  'update:quickMode',
  'update:restoreSession',
  'cancel',
  'create',
  'selectDir'
])
</script>

<style scoped>

/* 模态框遮罩层 */
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
  z-index: 1000;
  padding: 20px;
}

/* 模态框基础样式 */
.modal-overlay .modal {
  background: var(--color-bg-secondary);
  border: 0.5px solid var(--color-border);
  border-radius: 14px;
  padding: 28px;
}

.modal-overlay .modal.create-agent-modal {
  max-width: min(50vw, 960px) !important;
  width: min(50vw, 960px);
  max-height: calc(var(--app-height, 100vh) - 40px);
  overflow-y: auto;
}

.create-agent-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--color-text-primary);
}

/* 响应式网格布局 */
.create-agent-modal .form-grid {
  display: grid;
  gap: 20px;
}

.create-agent-modal .form-grid.create-agent-layout {
  grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.2fr);
  align-items: start;
}

.create-agent-modal .form-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.create-agent-modal .create-agent-options-column {
  gap: 12px;
}

/* 平板及以下：保持双列但允许更紧凑 */
@media (max-width: 1023px) {
  .modal-overlay .modal.create-agent-modal {
    width: 90%;
    max-width: 900px !important;
  }

  .create-agent-modal .form-grid.create-agent-layout {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* 移动端：单列布局 */
@media (max-width: 768px) {
  .modal-overlay .modal.create-agent-modal {
    width: 100%;
    max-width: 100% !important;
  }

  .create-agent-modal .form-grid.create-agent-layout {
    grid-template-columns: 1fr;
  }
}

.create-agent-modal .form-control {
  width: 100%;
  padding: 10px 12px;
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-primary);
  font-size: 14px;
}

.create-agent-modal .form-control:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-tertiary);
}

.create-agent-modal select.form-control option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.create-agent-modal .modal-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.create-agent-modal .btn {
  flex: 1;
  padding: 10px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}

.create-agent-modal .btn.secondary {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.create-agent-modal .btn.secondary:hover {
  background: var(--color-bg-tertiary);
}

.create-agent-modal .btn.primary {
  background: var(--color-success);
  color: var(--color-text-primary);
}

.create-agent-modal .btn.primary:hover {
  transform: translateY(-1px);
}

.create-agent-modal .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none !important;
}

/* 单选框组样式 */
.create-agent-modal .radio-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.create-agent-modal .radio-label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  background: var(--color-bg-secondary);
  border: 0.5px solid var(--color-border);
  border-radius: 10px;
  cursor: pointer;
}

.create-agent-modal .radio-label:hover {
  background: var(--color-bg-primary);
  border-color: var(--color-border);
  transform: translateY(-1px);
}

.create-agent-modal .radio-label:has(input:checked) {
  background: var(--color-accent-subtle);
  border-color: var(--color-accent);
}

.create-agent-modal .radio-label input[type="radio"] {
  appearance: none;
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-bg-primary);
  cursor: pointer;
  position: relative;
}

.create-agent-modal .radio-label input[type="radio"]:hover {
  border-color: var(--color-border);
}

.create-agent-modal .radio-label input[type="radio"]:checked {
  border-color: var(--color-accent);
  background: var(--color-accent-subtle);
}

.create-agent-modal .radio-label input[type="radio"]:checked::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  background: var(--color-accent);
  border-radius: 50%;
}

.create-agent-modal .radio-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.create-agent-modal .radio-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

/* 表单帮助文字样式 */
.form-help {
  display: block;
  margin: 0;
  padding: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* 表单组样式 */
.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

/* 输入框带按钮样式 */
.input-with-button {
  display: flex;
  gap: 10px;
}

.input-with-button .form-control {
  flex: 1;
  width: auto;
}

.select-dir-btn {
  padding: 10px 16px;
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
}

.select-dir-btn:hover {
  background: var(--color-bg-tertiary);
}

/* Toggle 开关样式 */
.toggle-wrapper {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: var(--color-bg-secondary);
  backdrop-filter: blur(40px) saturate(150%);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  border: 1px solid var(--color-border);
  outline: 1px solid var(--color-border);
  outline-offset: -1px;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-wrapper:hover {
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
  border-color: var(--color-accent);
  outline-color: var(--color-accent);
}

.toggle-wrapper:active {
  transform: scale(0.98);
}

.toggle-switch {
  position: relative;
  display: block;
  width: 52px;
  height: 30px;
  flex-shrink: 0;
  cursor: pointer;
  margin: 0;
  padding: 0;
  line-height: 0;
}

.toggle-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--color-bg-secondary);
  backdrop-filter: blur(40px) saturate(150%);
  -webkit-backdrop-filter: blur(40px) saturate(150%);
  border: 1px solid var(--color-border);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  border-radius: 15px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  outline: 1px solid var(--color-border);
  outline-offset: -1px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 24px;
  width: 24px;
  left: 3px;
  bottom: 3px;
  background-color: var(--color-text-primary);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 50%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  border: 1px solid var(--color-border);
}

.toggle-input:checked + .toggle-slider {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-dark) 100%);
  border-color: var(--color-accent);
  box-shadow: 0 4px 16px var(--color-accent-subtle), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  outline-color: var(--color-accent);
}

.toggle-input:checked + .toggle-slider:before {
  transform: translateX(22px);
  background-color: var(--color-text-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  border-color: var(--color-accent);
}

.toggle-switch:hover .toggle-slider {
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
}

.toggle-switch:hover .toggle-slider:before {
  background-color: var(--color-text-primary);
}

.toggle-switch:active .toggle-slider {
  transform: scale(0.95);
}

.toggle-switch:active .toggle-slider:before {
  transform: translateX(22px) scale(0.95);
}

.toggle-input:disabled + .toggle-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-info {
  flex: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  gap: 4px;
}

.toggle-label-text {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: -0.01em;
  line-height: 1.4;
  margin: 0;
  padding: 0;
}
</style>