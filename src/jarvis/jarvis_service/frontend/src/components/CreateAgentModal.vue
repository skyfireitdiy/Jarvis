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
.modal-overlay .modal.create-agent-modal {
  max-width: min(50vw, 960px) !important;
  width: min(50vw, 960px);
  max-height: calc(var(--app-height, 100vh) - 40px);
  overflow-y: auto;
}

.create-agent-modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: #e6edf3;
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
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: #e6edf3;
  font-size: 14px;
}

.create-agent-modal .form-control:focus {
  outline: none;
  border-color: rgba(63, 185, 80, 0.6);
  background: rgba(255, 255, 255, 0.08);
}

.create-agent-modal select.form-control option {
  background: #1a1f2e;
  color: #e6edf3;
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
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
}

.create-agent-modal .btn.secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

.create-agent-modal .btn.primary {
  background: #3fb950;
  color: white;
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
  background: rgba(13, 17, 23, 0.6);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  cursor: pointer;
}

.create-agent-modal .radio-label:hover {
  background: rgba(13, 17, 23, 0.8);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.create-agent-modal .radio-label:has(input:checked) {
  background: rgba(56, 139, 253, 0.12);
  border-color: rgba(56, 139, 253, 0.4);
}

.create-agent-modal .radio-label input[type="radio"] {
  appearance: none;
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  background: rgba(13, 17, 23, 0.8);
  cursor: pointer;
  position: relative;
}

.create-agent-modal .radio-label input[type="radio"]:hover {
  border-color: rgba(255, 255, 255, 0.5);
}

.create-agent-modal .radio-label input[type="radio"]:checked {
  border-color: #58a6ff;
  background: rgba(56, 139, 253, 0.1);
}

.create-agent-modal .radio-label input[type="radio"]:checked::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  background: #58a6ff;
  border-radius: 50%;
}

.create-agent-modal .radio-text {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.create-agent-modal .radio-desc {
  font-size: 12px;
  color: #8b949e;
  line-height: 1.4;
}
</style>