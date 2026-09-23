<template>
  <div class="schema-field">
    <div class="config-field-label">
      <span class="config-field-name">{{ name }}<span v-if="required" class="config-field-required"> *</span></span>
      <span v-if="schema.description" class="config-field-desc">{{ schema.description }}</span>
    </div>

    <!-- 枚举：下拉选择 -->
    <select
      v-if="isEnum"
      class="config-field-select"
      :value="value"
      @change="update($event.target.value)"
    >
      <option v-for="opt in schema.enum" :key="String(opt)" :value="String(opt)">{{ opt }}</option>
    </select>

    <!-- 布尔：开关 -->
    <label v-else-if="type === 'boolean'" class="config-field-switch">
      <input type="checkbox" :checked="!!value" @change="update($event.target.checked)" />
      <span class="config-switch-slider"></span>
    </label>

    <!-- 数字 -->
    <input
      v-else-if="type === 'number' || type === 'integer'"
      type="number"
      class="config-field-input"
      :value="value === undefined || value === null ? '' : value"
      :min="schema.minimum"
      :max="schema.maximum"
      @input="onNumberInput"
    />

    <!-- 文本域 -->
    <textarea
      v-else-if="isTextarea"
      class="config-field-textarea"
      :value="value === undefined || value === null ? '' : value"
      @input="update($event.target.value)"
    ></textarea>

    <!-- 字典：additionalProperties 且无 properties -->
    <div v-else-if="isDict" class="config-field-dict">
      <div v-for="(dictValue, dictKey) in value" :key="dictKey" class="config-dict-item">
        <div class="config-dict-item-header">
          <span class="config-dict-key">{{ dictKey }}</span>
          <button type="button" class="config-field-remove" @click="removeDictKey(dictKey)">×</button>
        </div>
        <SchemaField
          :schema="schema.additionalProperties"
          :name="dictKey"
          :value="dictValue"
          :path="path + '.' + dictKey"
          @update="(v) => setDictValue(dictKey, v)"
        />
      </div>
      <div class="config-dict-add">
        <input
          ref="dictKeyInput"
          class="config-dict-new-key"
          placeholder="新键名"
          v-model="newDictKey"
          @keydown.enter="addDictKey"
        />
        <button type="button" class="config-field-add" @click="addDictKey">+ 添加</button>
      </div>
    </div>

    <!-- 对象：固定属性 -->
    <div v-else-if="isObject" class="config-field-object">
      <div
        v-for="subName in objectPropertyNames"
        :key="subName"
        class="config-field-nested"
      >
        <SchemaField
          :schema="objectProperties[subName]"
          :name="subName"
          :required="objectRequired.includes(subName)"
          :value="value[subName]"
          :path="path + '.' + subName"
          @update="(v) => setObjectValue(subName, v)"
        />
      </div>
    </div>

    <!-- 数组 -->
    <div v-else-if="isArray" class="config-field-array">
      <div v-for="(item, idx) in value" :key="idx" class="config-array-item">
        <div class="config-array-item-header">
          <span class="config-array-index">#{{ idx }}</span>
          <button type="button" class="config-field-remove" @click="removeArrayItem(idx)">×</button>
        </div>
        <SchemaField
          :schema="arrayItemSchema"
          :name="'item'"
          :value="item"
          :path="path + '[' + idx + ']'"
          @update="(v) => setArrayItem(idx, v)"
        />
      </div>
      <button type="button" class="config-field-add" @click="addArrayItem">+ 添加项</button>
    </div>

    <!-- 默认：文本输入 -->
    <input
      v-else
      type="text"
      class="config-field-input"
      :value="value === undefined || value === null ? '' : value"
      @input="update($event.target.value)"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  name: { type: String, default: '' },
  required: { type: Boolean, default: false },
  value: { type: null, default: undefined },
  path: { type: String, default: '' },
})

const emit = defineEmits(['update'])

const type = computed(() => props.schema.type || 'string')
const isEnum = computed(() => Array.isArray(props.schema.enum) && props.schema.enum.length > 0)
const isDict = computed(() => type.value === 'object' && props.schema.additionalProperties && !props.schema.properties)
const isObject = computed(() => type.value === 'object' && props.schema.properties)
const isArray = computed(() => type.value === 'array')
const isTextarea = computed(() => type.value === 'string' && props.schema.format === 'textarea')

const objectProperties = computed(() => props.schema.properties || {})
const objectPropertyNames = computed(() => Object.keys(objectProperties.value))
const objectRequired = computed(() => props.schema.required || [])
const arrayItemSchema = computed(() => props.schema.items || {})

const newDictKey = ref('')
const dictKeyInput = ref(null)

function update(v) {
  emit('update', v)
}

function onNumberInput(e) {
  const v = e.target.value
  if (v === '') { update(undefined); return }
  update(type.value === 'integer' ? parseInt(v, 10) : parseFloat(v))
}

// 对象子字段更新：保证 value 是对象
function setObjectValue(subName, v) {
  const next = { ...(props.value || {}) }
  next[subName] = v
  update(next)
}

// 字典操作
function setDictValue(dictKey, v) {
  const next = { ...(props.value || {}) }
  next[dictKey] = v
  update(next)
}

function removeDictKey(dictKey) {
  const next = { ...(props.value || {}) }
  delete next[dictKey]
  update(next)
}

function addDictKey() {
  const key = newDictKey.value.trim()
  if (!key) return
  const next = { ...(props.value || {}) }
  if (next[key] === undefined) next[key] = defaultForSchema(props.schema.additionalProperties)
  update(next)
  newDictKey.value = ''
  if (dictKeyInput.value) dictKeyInput.value.focus()
}

// 数组操作
function addArrayItem() {
  update([...(props.value || []), defaultForSchema(arrayItemSchema.value)])
}

function setArrayItem(idx, v) {
  const next = [...(props.value || [])]
  next[idx] = v
  update(next)
}

function removeArrayItem(idx) {
  const next = [...(props.value || [])]
  next.splice(idx, 1)
  update(next)
}

// 根据 Schema 生成默认值
function defaultForSchema(schema) {
  if (!schema) return ''
  if (schema.default !== undefined) return schema.default
  const t = schema.type || 'string'
  if (t === 'boolean') return false
  if (t === 'number' || t === 'integer') return 0
  if (t === 'array') return []
  if (t === 'object') return {}
  return ''
}
</script>

<style scoped>
.schema-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-field-label {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}

.config-field-name {
  font-weight: 600;
  color: var(--text, #e6edf3);
}

.config-field-required {
  color: var(--error, #e5484d);
}

.config-field-desc {
  color: var(--text-secondary, #8ba3b8);
  font-size: 12px;
}

.config-field-input,
.config-field-select,
.config-field-textarea {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  border-radius: 6px;
  background: var(--bg, rgba(0, 0, 0, 0.2));
  color: var(--text, #e6edf3);
  font-size: 13px;
}

.config-field-textarea {
  min-height: 60px;
  resize: vertical;
}

.config-field-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 40px;
  height: 22px;
  cursor: pointer;
}

.config-field-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.config-switch-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--border, rgba(255, 255, 255, 0.15));
  border-radius: 11px;
  transition: background 0.2s;
}

.config-switch-slider::before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 2px;
  bottom: 2px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}

.config-field-switch input:checked + .config-switch-slider {
  background: var(--accent, #4f8cff);
}

.config-field-switch input:checked + .config-switch-slider::before {
  transform: translateX(18px);
}

.config-field-object,
.config-field-dict {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 6px;
  background: var(--bg, rgba(255, 255, 255, 0.02));
}

.config-field-nested {
  padding: 6px 0;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.05));
}

.config-field-nested:last-child {
  border-bottom: none;
}

.config-dict-item,
.config-array-item {
  padding: 8px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: 6px;
  background: var(--bg, rgba(255, 255, 255, 0.02));
}

.config-dict-item-header,
.config-array-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.config-dict-key,
.config-array-index {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #8ba3b8);
}

.config-field-remove {
  border: none;
  background: transparent;
  color: var(--error, #e5484d);
  font-size: 16px;
  cursor: pointer;
  line-height: 1;
  padding: 0 4px;
}

.config-field-add {
  align-self: flex-start;
  padding: 4px 12px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  border-radius: 6px;
  background: transparent;
  color: var(--accent, #4f8cff);
  cursor: pointer;
  font-size: 12px;
}

.config-dict-add {
  display: flex;
  gap: 6px;
}

.config-dict-new-key {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
  border-radius: 6px;
  background: var(--bg, rgba(0, 0, 0, 0.2));
  color: var(--text, #e6edf3);
  font-size: 12px;
}

/* ===== 移动端适配 ===== */
@media (max-width: 640px) {
  .config-field-label {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
  .config-field-input,
  .config-field-select,
  .config-field-textarea {
    padding: 8px 10px;
    font-size: 15px;
  }
  .config-field-textarea {
    min-height: 80px;
  }
  .config-dict-add {
    flex-wrap: wrap;
  }
  .config-dict-new-key {
    flex: 1 1 100%;
  }
  .config-field-add {
    flex: 1;
    text-align: center;
    padding: 8px 12px;
  }
  .config-field-remove {
    font-size: 20px;
    padding: 0 8px;
  }
  .config-field-object,
  .config-field-dict {
    padding: 6px;
  }
}
</style>
