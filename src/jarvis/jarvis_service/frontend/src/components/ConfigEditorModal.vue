<template>
  <Teleport to="body">
    <div class="modal-overlay" v-if="visible" @click.self="close">
      <div class="modal config-editor-modal">
        <div class="modal-header">
          <h2>配置文件</h2>
          <button class="close-btn" @click="close">×</button>
        </div>

      <!-- 加载中 -->
      <div v-if="loading" class="config-editor-loading">加载配置中...</div>

      <!-- 加载失败 -->
      <div v-else-if="loadError" class="config-editor-error">
        <div>{{ loadError }}</div>
        <button class="ghost-btn" @click="loadAll">重试</button>
      </div>

      <template v-else>
        <!-- 工具栏：视图切换 + 操作 -->
        <div class="config-editor-toolbar">
          <div class="config-editor-tabs">
            <button
              class="config-editor-tab"
              :class="{ active: viewMode === 'form' }"
              @click="switchView('form')"
            >表单</button>
            <button
              class="config-editor-tab"
              :class="{ active: viewMode === 'text' }"
              @click="switchView('text')"
            >纯文本</button>
          </div>
          <div class="config-editor-actions">
            <button class="ghost-btn" @click="loadAll" :disabled="saving">重新加载</button>
            <button class="primary-btn" @click="save" :disabled="saving">
              {{ saving ? '保存中…' : '保存配置' }}
            </button>
          </div>
        </div>

        <div v-if="saveError" class="config-editor-error">{{ saveError }}</div>

        <!-- 表单视图：Schema 动态生成 -->
        <div v-if="viewMode === 'form'" class="config-editor-form">
          <div v-if="schemaDescription" class="config-editor-desc">{{ schemaDescription }}</div>
          <div v-for="propName in schemaPropertyNames" :key="propName" class="config-editor-section">
            <SchemaField
              :schema="schemaProperties[propName]"
              :name="propName"
              :required="schemaRequired.includes(propName)"
              :value="formData[propName]"
              :path="propName"
              @update="(v) => setField(propName, v)"
            />
          </div>
        </div>

        <!-- 纯文本视图 -->
        <div v-else class="config-editor-text">
          <div class="config-editor-text-help">
            以纯文本方式编辑配置（YAML 格式）。修改后点击「保存配置」会先解析校验，失败时不会写入。
          </div>
          <textarea
            ref="textAreaRef"
            class="config-editor-textarea"
            v-model="textContent"
            spellcheck="false"
          ></textarea>
        </div>
      </template>

      <div class="modal-actions">
        <button class="ghost-btn" @click="close">关闭</button>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import SchemaField from './SchemaField.vue'
import { toYaml, parseYaml, cloneValue } from '../utils/configYaml.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  fetchWithAuth: { type: Function, default: null },
  gatewayUrl: { type: String, default: '127.0.0.1:8000' },
  getHttpProtocol: { type: Function, default: () => 'http' },
  showToast: { type: Function, default: () => {} },
  nodeId: { type: String, default: 'master' },
})

const emit = defineEmits(['update:visible'])

// ===== 状态 =====
const loading = ref(false)
const loadError = ref('')
const saveError = ref('')
const saving = ref(false)
const viewMode = ref('form') // 'form' | 'text'
const schema = ref(null)
const config = ref({})
const formData = ref({})
const textContent = ref('')
const textAreaRef = ref(null)

// ===== 计算属性 =====
const schemaProperties = computed(() => (schema.value && schema.value.properties) || {})
const schemaPropertyNames = computed(() => Object.keys(schemaProperties.value))
const schemaRequired = computed(() => (schema.value && schema.value.required) || [])
const schemaDescription = computed(() => (schema.value && schema.value.description) || '')

// ===== 辅助函数 =====
function getGatewayAddress() {
  const raw = (props.gatewayUrl || '127.0.0.1:8000').trim()
  if (raw.includes('://')) {
    try {
      const url = new URL(raw)
      const isTls = url.protocol === 'https:' || url.protocol === 'wss:'
      return { host: url.hostname || '127.0.0.1', port: url.port || (isTls ? '443' : '80') }
    } catch (e) {
      return { host: '127.0.0.1', port: '8000' }
    }
  }
  const parts = raw.split(':')
  return { host: parts[0] || '127.0.0.1', port: parts[1] || '8000' }
}

function buildApiUrl(path) {
  const { host, port } = getGatewayAddress()
  const proto = props.getHttpProtocol ? props.getHttpProtocol() : 'http'
  return `${proto}://${host}:${port}${path}`
}

async function apiGet(path) {
  if (!props.fetchWithAuth) throw new Error('fetchWithAuth 未提供')
  const rawResp = await props.fetchWithAuth(buildApiUrl(path), { method: 'GET' })
  // fetchWithAuth 返回的是原生 Response，需先解析 JSON
  let resp = rawResp
  if (rawResp && typeof rawResp.json === 'function') {
    try {
      resp = await rawResp.json()
    } catch (e) {
      throw new Error('响应解析失败')
    }
  }
  if (!resp || resp.success === false) {
    const msg = resp && resp.error && resp.error.message ? resp.error.message : '请求失败'
    throw new Error(msg)
  }
  return resp
}

async function apiPost(path, body) {
  if (!props.fetchWithAuth) throw new Error('fetchWithAuth 未提供')
  const rawResp = await props.fetchWithAuth(buildApiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  // fetchWithAuth 返回的是原生 Response，需先解析 JSON
  let resp = rawResp
  if (rawResp && typeof rawResp.json === 'function') {
    try {
      resp = await rawResp.json()
    } catch (e) {
      throw new Error('响应解析失败')
    }
  }
  if (!resp || resp.success === false) {
    const msg = resp && resp.error && resp.error.message ? resp.error.message : '请求失败'
    throw new Error(msg)
  }
  return resp
}

// ===== 数据加载 =====
async function loadAll() {
  loading.value = true
  loadError.value = ''
  saveError.value = ''
  try {
    const schemaResp = await apiGet('/api/config/schema')
    schema.value = schemaResp.data || {}

    const configResp = await apiGet(`/api/nodes/${props.nodeId}/config`)
    config.value = (configResp.data && configResp.data.config) || {}
    initForm()
  } catch (e) {
    loadError.value = (e && e.message) ? e.message : '加载配置失败'
  } finally {
    loading.value = false
  }
}

function initForm() {
  const data = {}
  for (const name of schemaPropertyNames.value) {
    data[name] = cloneValue(
      config.value[name] !== undefined ? config.value[name] : schemaProperties.value[name].default
    )
  }
  formData.value = data
  textContent.value = toYaml(data)
}

// ===== 字段更新 =====
function setField(path, value) {
  formData.value[path] = value
}

// ===== 视图切换 =====
function switchView(mode) {
  if (mode === viewMode.value) return
  if (mode === 'text') {
    // 进入纯文本视图：把当前表单状态序列化为 YAML
    textContent.value = toYaml(formData.value)
  }
  viewMode.value = mode
  if (mode === 'text') {
    nextTick(() => {
      if (textAreaRef.value) textAreaRef.value.focus()
    })
  }
}

// ===== 保存 =====
async function save() {
  saveError.value = ''
  let data
  if (viewMode.value === 'text') {
    // 纯文本视图：解析 YAML
    try {
      data = parseYaml(textContent.value)
    } catch (e) {
      saveError.value = `纯文本解析失败：${e.message}`
      return
    }
  } else {
    data = cloneValue(formData.value)
  }

  saving.value = true
  try {
    // 保留 Schema 未覆盖的顶层键（避免丢失额外配置）
    const merged = { ...cloneValue(config.value), ...data }
    const sections = Object.keys(merged)
    await apiPost(`/api/nodes/${props.nodeId}/config`, {
      config_sections: sections,
      config_data: merged,
    })
    config.value = merged
    props.showToast('配置已保存', 'success')
  } catch (e) {
    saveError.value = (e && e.message) ? e.message : '保存失败'
  } finally {
    saving.value = false
  }
}

// ===== 关闭 =====
function close() {
  emit('update:visible', false)
}

watch(() => props.visible, (v) => {
  if (v) loadAll()
})
</script>

<style scoped>
/* 模态框遮罩与卡片基础样式（本组件独立定义，避免依赖其他组件 scoped 样式导致全透明/重叠） */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-overlay, rgba(4, 8, 15, 0.72));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3100;
  padding: 20px;
}

.modal-overlay .modal {
  background: var(--color-bg-modal, rgba(9, 16, 28, 0.94));
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.1));
  border-radius: 14px;
  padding: 28px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  color: var(--text, #e6edf3);
}

.config-editor-modal {
  width: 720px;
  max-width: 92vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}

.config-editor-loading,
.config-editor-error {
  padding: 24px 16px;
  text-align: center;
  color: var(--text-secondary, #8ba3b8);
}

.config-editor-error {
  color: var(--error, #e5484d);
}

.config-editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  margin-bottom: 12px;
}

.config-editor-tabs {
  display: flex;
  gap: 4px;
}

.config-editor-tab {
  padding: 6px 14px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary, #8ba3b8);
  cursor: pointer;
  font-size: 13px;
}

.config-editor-tab.active {
  background: var(--accent, #4f8cff);
  color: #fff;
  border-color: var(--accent, #4f8cff);
}

.config-editor-actions {
  display: flex;
  gap: 8px;
}

.config-editor-desc {
  color: var(--text-secondary, #8ba3b8);
  font-size: 13px;
  margin-bottom: 12px;
}

.config-editor-form {
  overflow-y: auto;
  flex: 1;
  padding-right: 4px;
}

.config-editor-section {
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: var(--bg, rgba(255, 255, 255, 0.02));
}

.config-editor-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.config-editor-text-help {
  color: var(--text-secondary, #8ba3b8);
  font-size: 12px;
  margin-bottom: 8px;
}

.config-editor-textarea {
  flex: 1;
  width: 100%;
  min-height: 320px;
  font-family: 'SF Mono', 'Consolas', 'Menlo', monospace;
  font-size: 12px;
  line-height: 1.5;
  padding: 10px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
  background: var(--bg, rgba(0, 0, 0, 0.2));
  color: var(--text, #e6edf3);
  resize: vertical;
}

/* ===== 移动端适配 ===== */
@media (max-width: 640px) {
  .modal-overlay {
    padding: 8px;
    align-items: flex-end;
  }
  .modal-overlay .modal {
    padding: 16px;
    border-radius: 12px;
  }
  .config-editor-modal {
    width: 100%;
    max-width: 100vw;
    max-height: 92vh;
  }
  .config-editor-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .config-editor-tabs {
    justify-content: center;
  }
  .config-editor-actions {
    justify-content: flex-end;
  }
  .config-editor-actions .ghost-btn,
  .config-editor-actions .primary-btn {
    padding: 8px 12px;
    font-size: 13px;
    flex: 1;
  }
  .config-editor-section {
    padding: 10px;
  }
  .config-editor-textarea {
    min-height: 240px;
  }
}
</style>
