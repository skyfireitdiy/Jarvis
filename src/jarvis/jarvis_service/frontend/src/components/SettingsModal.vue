<template>
  <!-- 设置弹窗 -->
  <div class="modal-overlay" v-if="visible">
    <div class="modal settings-modal">
      <div class="modal-header">
        <h2>设置</h2>
        <button class="close-btn" @click="close">×</button>
      </div>
      <div class="form-group">
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input type="checkbox" v-model="localAutoLoginEnabled" @change="handleAutoLoginChange" class="toggle-input" />
            <span class="toggle-slider"></span>
          </label>
          <div class="toggle-info">
            <span class="toggle-label-text">免登录（记住Token）</span>
            <span class="form-help">启用后，登录成功时将Token保存在浏览器本地，下次打开时自动尝试连接。</span>
          </div>
        </div>
      </div>

      <div class="form-group">
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input type="checkbox" v-model="localNotifyOnExit" @change="handleNotifyOnExitChange" class="toggle-input" />
            <span class="toggle-slider"></span>
          </label>
          <div class="toggle-info">
            <span class="toggle-label-text">Agent 退出时弹出通知</span>
            <span class="form-help">启用后，Agent 结束运行时弹出系统通知提醒（不影响提示音）。</span>
          </div>
        </div>
      </div>

      <div class="form-group">
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input type="checkbox" v-model="localNotifyOnInput" @change="handleNotifyOnInputChange" class="toggle-input" />
            <span class="toggle-slider"></span>
          </label>
          <div class="toggle-info">
            <span class="toggle-label-text">需要输入时弹出通知</span>
            <span class="form-help">启用后，Agent 等待输入时弹出系统通知提醒（不影响提示音）。</span>
          </div>
        </div>
      </div>

      <!-- 我的账户 -->
      <div class="form-group">
        <label>当前用户</label>
        <div style="font-size:14px">{{ currentUserInfo?.username || '-' }}<span v-if="currentUserInfo?.display_name" style="color:var(--text-secondary,#8ba3b8);margin-left:8px">({{ currentUserInfo.display_name }})</span></div>
      </div>
      <div class="form-group">
        <label>修改密码</label>
        <div class="form-row"><label>旧密码</label><input v-model="changePasswordForm.old_password" type="password" placeholder="输入旧密码" /></div>
        <div class="form-row"><label>新密码</label><input v-model="changePasswordForm.new_password" type="password" placeholder="输入新密码" /></div>
        <div class="form-row"><label>确认密码</label><input v-model="changePasswordForm.confirm_password" type="password" placeholder="再次输入新密码" /></div>
        <button class="ghost-btn" @click="changePassword" :disabled="loading">修改密码</button>
      </div>

      <!-- 历史消息管理 -->
      <div class="form-group">
        <div class="history-info">
          <div class="history-stat">
            <span class="history-stat-label">历史消息数量:</span>
            <span class="history-stat-value">{{ historyStorage.getTotalCount() }}</span>
          </div>
          <div class="history-stat">
            <span class="history-stat-label">存储空间:</span>
            <span class="history-stat-value">{{ historyStorage.getStorageInfo().totalSizeFormatted }}</span>
          </div>
        </div>
      </div>
      <div class="form-group">
        <button class="danger-btn" @click="confirmClearHistory" :disabled="historyStorage.getTotalCount() === 0">
          清除历史记录
        </button>
      </div>


      <!-- 隐藏工作目录 -->
      <div class="form-group">
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input type="checkbox" v-model="localHideWorkingDir" @change="handleHideWorkingDirChange" class="toggle-input" />
            <span class="toggle-slider"></span>
          </label>
          <div class="toggle-info">
            <span class="toggle-label-text">隐藏工作目录</span>
            <span class="form-help">启用后，界面上的 Agent 工作目录将显示为占位符，适合录屏或截图时使用（仅本机浏览器生效）。</span>
          </div>
        </div>
      </div>

      <!-- 自动安装/更新浏览器扩展 -->
      <div class="form-group">
        <div class="toggle-wrapper">
          <label class="toggle-switch">
            <input type="checkbox" v-model="localAutoInstallBrowserExt" @change="handleAutoInstallBrowserExtChange" class="toggle-input" />
            <span class="toggle-slider"></span>
          </label>
          <div class="toggle-info">
            <span class="toggle-label-text">自动安装/更新浏览器扩展</span>
            <span class="form-help">默认关闭。开启后，本机 daemon 会在网关上的扩展版本变化时自动下载并覆盖本地扩展目录；不会重启浏览器，需在 chrome://extensions 点击「刷新」使新版本生效。</span>
          </div>
        </div>
      </div>
      <!-- 终端名称 -->
      <div class="form-group">
        <label>终端名称</label>
        <div class="form-help" style="margin-bottom:10px">用于在网关侧区分不同终端（如「家里的台式机」「办公笔记本」）。留空则使用默认名称；修改后会自动同步给浏览器扩展与本机 daemon，Agent 即可按名称定位到这台机器。</div>
        <input
          class="node-name-input"
          :value="localTerminalName"
          placeholder="例如：办公笔记本"
          @input="onTerminalNameInput($event.target.value)"
          @keydown.enter="$event.target.blur()"
        />
      </div>

      <!-- 本机后台服务端口 -->
      <div class="form-group">
        <label>本机后台服务端口</label>
        <div class="form-help" style="margin-bottom:10px">本机 jarvis-daemon 的监听端口（默认 17800）。若默认端口被占用、daemon 改用了其它端口，请在此填写新端口号，浏览器将据此连接本机后台服务（地址恒为本机 127.0.0.1）。留空或填默认端口即恢复默认。</div>
        <input
          class="node-name-input"
          :value="localDaemonPort"
          placeholder="17800"
          inputmode="numeric"
          @input="onDaemonPortInput($event.target.value)"
          @change="onDaemonPortCommit"
          @keydown.enter="$event.target.blur()"
          @blur="onDaemonPortCommit"
        />
      </div>

      <!-- 节点显示名映射 -->
      <div class="form-group">
        <label>节点显示名</label>
        <div class="form-help" style="margin-bottom:10px">为节点自定义显示名称（仅本机浏览器生效，留空则显示原始节点 ID）。</div>
        <div v-if="nodeList.length === 0" class="form-help">暂无可用节点。</div>
        <div v-for="node in nodeList" :key="node.value" class="node-name-row">
          <span class="node-name-origin" :title="node.value">{{ node.value }}</span>
          <input
            class="node-name-input"
            :value="localNodeDisplayNames[node.value] || ''"
            :placeholder="'自定义显示名'"
            @input="onNodeNameInput(node.value, $event.target.value)"
            @keydown.enter="$event.target.blur()"
          />
        </div>
      </div>

      <!-- 连接管理 -->
      <div class="form-group">
        <label>连接管理</label>
        <div class="connection-management-section">
          <button class="danger-btn" @click="disconnectAll" :disabled="!socket">
            断开连接
          </button>
          <span class="form-help">断开所有 WebSocket 连接并刷新页面</span>
        </div>
      </div>

      <!-- 外观：壁纸与界面透明度 -->
      <div class="form-group">
        <label>工作区壁纸</label>
        <div class="form-help" style="margin-bottom:10px">上传图片作为工作区背景（支持 png / jpeg / webp / gif，单张不超过 8MB，最多 {{ WALLPAPER_MAX_COUNT }} 张）。壁纸保存在网关，所有终端共享同一套。</div>
        <div class="wallpaper-row">
          <div class="wallpaper-preview" :class="{ empty: !wallpaperPreviewUrl }">
            <img v-if="wallpaperPreviewUrl" :src="wallpaperPreviewUrl" alt="壁纸预览" />
            <span v-else>未设置壁纸</span>
          </div>
          <div class="wallpaper-actions">
            <button class="ghost-btn" @click="triggerWallpaperPick" :disabled="wallpaperUploading || !canUploadMore">
              {{ wallpaperUploading ? '上传中…' : '添加图片' }}
            </button>
            <button class="ghost-btn" @click="fetchGatewayWallpaper" :disabled="wallpaperUploading || wallpaperLoading">
              {{ wallpaperLoading ? '读取中…' : '使用网关壁纸' }}
            </button>
            <button class="danger-btn" @click="removeWallpaper" :disabled="wallpaperUploading || !wallpaperUrl">
              移除壁纸
            </button>
            <input
              ref="wallpaperInputRef"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              class="wallpaper-file-input"
              @change="handleWallpaperFileChange"
            />
          </div>
        </div>
        <!-- 网关壁纸库：所有终端共享，点击缩略图切换当前壁纸 -->
        <div v-if="gatewayWallpapers.length" class="wallpaper-gallery">
          <div
            v-for="item in gatewayWallpapers"
            :key="item.url"
            class="wallpaper-thumb"
            :class="{ active: item.url === wallpaperUrl }"
            :title="item.url === wallpaperUrl ? '当前壁纸' : '点击使用这张壁纸'"
            @click="useGatewayWallpaper(item.url)"
          >
            <img :src="buildWallpaperAbsoluteUrl(item.url)" :alt="item.name || '壁纸'" />
            <button
              class="wallpaper-thumb-remove"
              title="从网关删除这张壁纸"
              :disabled="wallpaperUploading"
              @click.stop="deleteGatewayWallpaper(item.url)"
            >×</button>
          </div>
        </div>
        <!-- 网关壁纸状态：本机未启用但网关已有壁纸时，提示可一键启用 -->
        <div v-if="gatewayWallpapers.length && !wallpaperUrl" class="wallpaper-hint">
          网关已保存 {{ gatewayWallpapers.length }} 张壁纸，本机尚未启用。点击缩略图或「使用网关壁纸」即可启用。
        </div>
        <div v-else-if="wallpaperUrl && gatewayWallpapers.length && !gatewayWallpapers.some((item) => item.url === wallpaperUrl)" class="wallpaper-hint">
          本机壁纸与网关当前壁纸不一致（网关壁纸可能已被其他终端更新）。
        </div>
        <div v-else-if="wallpaperChecked && !gatewayWallpapers.length" class="wallpaper-hint">
          网关尚未保存任何壁纸。
        </div>
      </div>

      <div class="form-group">
        <label>界面透明度</label>
        <div class="form-help" style="margin-bottom:10px">调整工作区各面板与控件的背景透明度，数值越低越透明（壁纸透出越明显），100 为完全不透明。</div>
        <div class="opacity-row">
          <input
            type="range"
            min="20"
            max="100"
            step="1"
            class="opacity-slider"
            :value="localUiOpacity"
            @input="onUiOpacityInput($event.target.value)"
            @change="onUiOpacityCommit"
          />
          <span class="opacity-value">{{ localUiOpacity }}%</span>
        </div>
      </div>

      <div class="modal-actions">
        <button class="ghost-btn" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  historyStorage: {
    type: Object,
    required: true
  },
  socket: {
    type: Object,
    default: null
  },
  autoLoginEnabled: {
    type: Boolean,
    default: false
  },
  notifyOnExit: {
    type: Boolean,
    default: false
  },
  notifyOnInput: {
    type: Boolean,
    default: false
  },
  auth: { type: Object, default: () => ({}) },
  fetchWithAuth: { type: Function, default: null },
  // 取当前有效 token（会从 localStorage 回填到内存），用于跨终端发现网关壁纸
  getToken: { type: Function, default: null },
  gatewayUrl: { type: String, default: '127.0.0.1:8000' },
  getHttpProtocol: { type: Function, default: () => 'http' },
  showToast: { type: Function, default: () => {} },
  nodeOptions: { type: Array, default: () => [] },
  nodeDisplayNames: { type: Object, default: () => ({}) },
  hideWorkingDir: { type: Boolean, default: false },
  autoInstallBrowserExt: { type: Boolean, default: false },
  terminalName: { type: String, default: '' },
  daemonPort: { type: String, default: '' },
  // 工作区壁纸 URL（网关 /uploads/wallpaper/... 相对路径，空串表示未设置）
  wallpaperUrl: { type: String, default: '' },
  // 界面透明度（20~100，100 表示完全不透明）
  uiOpacity: { type: Number, default: 100 }
})

const emit = defineEmits([
  'update:visible',
  'confirmClearHistory',
  'disconnectAll',
  'update:autoLoginEnabled',
  'saveAutoLoginSetting',
  'update:notifyOnExit',
  'update:notifyOnInput',
  'saveNotifySettings',
  'saveNodeDisplayNames',
  'update:hideWorkingDir',
  'saveHideWorkingDirSetting',
  'update:autoInstallBrowserExt',
  'saveAutoInstallBrowserExtSetting',
  'update:terminalName',
  'saveTerminalNameSetting',
  'update:daemonPort',
  'saveDaemonPortSetting',
  'saveWallpaperSetting',
  'update:uiOpacity',
  'saveUiOpacitySetting'
])

// 本地状态
const localAutoLoginEnabled = ref(props.autoLoginEnabled)
const localNotifyOnExit = ref(props.notifyOnExit)
const localNotifyOnInput = ref(props.notifyOnInput)
const localHideWorkingDir = ref(props.hideWorkingDir)
const localAutoInstallBrowserExt = ref(props.autoInstallBrowserExt)
const localTerminalName = ref(props.terminalName)
const localDaemonPort = ref(props.daemonPort)
// 壁纸：预览用绝对 URL（相对路径需拼网关地址），上传中标记
const wallpaperInputRef = ref(null)
const wallpaperUploading = ref(false)
const wallpaperPreviewUrl = ref(buildWallpaperAbsoluteUrl(props.wallpaperUrl))
// 网关侧壁纸库（与「本机是否启用」无关）：用于跨终端发现已上传的壁纸
const gatewayWallpapers = ref([])
// 网关当前生效壁纸 URL（列表第一张 / 最近上传的那张）
const gatewayWallpaperUrl = computed(() => gatewayWallpapers.value[0]?.url || '')
const wallpaperLoading = ref(false)
const wallpaperChecked = ref(false)
// 壁纸库上限，与网关 /api/wallpaper/upload 保持一致
const WALLPAPER_MAX_COUNT = 20
const canUploadMore = computed(() => gatewayWallpapers.value.length < WALLPAPER_MAX_COUNT)
// 界面透明度（20~100）
const localUiOpacity = ref(normalizeOpacity(props.uiOpacity))
const changePasswordForm = ref({ old_password: '', new_password: '', confirm_password: '' })
const loading = ref(false)
// 节点显示名本地副本（编辑中，input 时即时更新并向上同步）
const localNodeDisplayNames = ref({ ...(props.nodeDisplayNames || {}) })

// 节点列表（去重，value 为原始 node_id）
const nodeList = computed(() => {
  const seen = new Set()
  const list = []
  for (const opt of props.nodeOptions || []) {
    const value = String(opt?.node_id || opt?.value || '').trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    list.push({ value })
  }
  return list
})

// 计算属性
const currentUserInfo = computed(() => props.auth?.userInfo || null)
const currentUserId = computed(() => props.auth?.userInfo?.user_id || '')

// 辅助函数
function getGatewayAddress() {
  const raw = (props.gatewayUrl || '127.0.0.1:8000').trim()
  // 完整 URL（如 wss://jvs-ai.cn）需用 URL 解析，避免 split(':') 误判
  if (raw.includes('://')) {
    try {
      const url = new URL(raw)
      const isTls = url.protocol === 'https:' || url.protocol === 'wss:'
      return {
        host: url.hostname || '127.0.0.1',
        port: url.port || (isTls ? '443' : '80'),
      }
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

// 壁纸 URL 归一化：后端返回 /uploads/wallpaper/xxx 相对路径，需拼网关地址才能作为 img src
function buildWallpaperAbsoluteUrl(url) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  if (/^(https?:|data:|blob:)/i.test(raw)) return raw
  return buildApiUrl(raw.startsWith('/') ? raw : `/${raw}`)
}

// 透明度归一化到 20~100 的整数
function normalizeOpacity(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return 100
  return Math.min(100, Math.max(20, Math.round(num)))
}

// 壁纸单文件上限，与网关 /api/wallpaper/upload 保持一致
const WALLPAPER_MAX_BYTES = 8 * 1024 * 1024

// 把网关返回的壁纸列表归一化为 [{url, name}]，过滤掉非法项
function normalizeWallpaperList(list) {
  if (!Array.isArray(list)) return []
  const seen = new Set()
  const result = []
  for (const item of list) {
    const url = String((typeof item === 'string' ? item : item?.url) || '').trim()
    if (!url || seen.has(url)) continue
    seen.add(url)
    result.push({ url, name: String(item?.name || '') })
  }
  return result
}

function triggerWallpaperPick() {
  wallpaperInputRef.value?.click()
}

// 查询网关当前保存的壁纸（跨终端共享）：新电脑/新浏览器打开设置时，
// 即使本机 localStorage 里没有壁纸记录，也能看到网关已有壁纸并一键启用。
async function fetchGatewayWallpaper() {
  if (wallpaperLoading.value) return
  wallpaperLoading.value = true
  try {
    // fetchWithAuth 在内存 token 为空时直接返回模拟 401（不会真发请求）。
    // 新电脑/新浏览器刚打开页面时 token 可能只在 localStorage 里，这里先回填。
    try {
      if (typeof props.getToken === 'function') props.getToken()
    } catch (e) {
      // 忽略：token 回填失败时按未登录处理
    }
    const response = await props.fetchWithAuth(buildApiUrl('/api/wallpaper'))
    const result = await response.json()
    if (!response.ok || !result?.success) {
      // 未登录（401）或权限不足时不打扰用户，静默忽略
      return
    }
    // 兼容两种返回：{wallpapers:[...]}（壁纸库）与 {url}（旧版单张）
    gatewayWallpapers.value = normalizeWallpaperList(
      Array.isArray(result.wallpapers) ? result.wallpapers : result.url ? [result.url] : []
    )
    wallpaperChecked.value = true
    // 本机尚未启用壁纸但网关已有：直接启用，让用户「打开设置就看到壁纸」
    if (gatewayWallpaperUrl.value && !props.wallpaperUrl) {
      wallpaperPreviewUrl.value = buildWallpaperAbsoluteUrl(gatewayWallpaperUrl.value)
      emit('saveWallpaperSetting', gatewayWallpaperUrl.value)
    }
  } catch (error) {
    console.warn('[WALLPAPER] Failed to fetch gateway wallpaper:', error)
  } finally {
    wallpaperLoading.value = false
  }
}

// 读取文件为 base64（去掉 dataURL 前缀，网关兼容两种格式但这里保持精简）
function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const commaIndex = result.indexOf(',')
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result)
    }
    reader.onerror = () => reject(reader.error || new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })
}

// 选择图片后上传到网关（支持一次多选），最后一张上传成功的壁纸自动启用
async function handleWallpaperFileChange(event) {
  const input = event.target
  const files = Array.from(input?.files || [])
  // 允许重复选择同一文件（否则 change 不再触发）
  if (input) input.value = ''
  if (!files.length) return
  const validFiles = []
  for (const file of files) {
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
      props.showToast(`「${file.name}」不是支持的图片格式（png / jpeg / webp / gif）`, 'error')
      continue
    }
    if (file.size > WALLPAPER_MAX_BYTES) {
      props.showToast(`「${file.name}」超过 8MB`, 'error')
      continue
    }
    validFiles.push(file)
  }
  if (!validFiles.length) return
  const remaining = WALLPAPER_MAX_COUNT - gatewayWallpapers.value.length
  if (remaining <= 0) {
    props.showToast(`壁纸库最多 ${WALLPAPER_MAX_COUNT} 张，请先删除部分壁纸`, 'error')
    return
  }
  if (validFiles.length > remaining) {
    props.showToast(`壁纸库最多 ${WALLPAPER_MAX_COUNT} 张，本次只上传前 ${remaining} 张`, 'error')
    validFiles.length = remaining
  }
  wallpaperUploading.value = true
  let lastUrl = ''
  let uploaded = 0
  try {
    for (const file of validFiles) {
      const data = await readFileAsBase64(file)
      const response = await props.fetchWithAuth(buildApiUrl('/api/wallpaper/upload'), {
        method: 'POST',
        body: JSON.stringify({ data, filename: file.name })
      })
      const result = await response.json()
      if (!response.ok || !result?.success) {
        const message = result?.error?.message || `上传失败（HTTP ${response.status}）`
        props.showToast(`「${file.name}」${message}`, 'error')
        continue
      }
      uploaded += 1
      lastUrl = String(result.url || '')
    }
    if (uploaded > 0) {
      // 上传后刷新壁纸库列表（网关按最近上传排序）
      await fetchGatewayWallpaper()
      if (lastUrl) {
        wallpaperPreviewUrl.value = buildWallpaperAbsoluteUrl(lastUrl)
        emit('saveWallpaperSetting', lastUrl)
      }
      props.showToast(uploaded > 1 ? `已上传 ${uploaded} 张壁纸` : '壁纸已更新', 'success')
    }
  } catch (error) {
    console.warn('[WALLPAPER] Upload failed:', error)
    props.showToast('壁纸上传失败，请检查网络或权限', 'error')
  } finally {
    wallpaperUploading.value = false
  }
}

// 点击缩略图：把该壁纸设为当前壁纸（只改本机 localStorage，不动网关）
function useGatewayWallpaper(url) {
  const target = String(url || '').trim()
  if (!target) return
  wallpaperPreviewUrl.value = buildWallpaperAbsoluteUrl(target)
  emit('saveWallpaperSetting', target)
}

// 从网关删除指定壁纸；若删的是当前壁纸，自动切到剩余第一张（无剩余则清空）
async function deleteGatewayWallpaper(url) {
  const target = String(url || '').trim()
  if (!target || wallpaperUploading.value) return
  wallpaperUploading.value = true
  try {
    const response = await props.fetchWithAuth(
      buildApiUrl(`/api/wallpaper?url=${encodeURIComponent(target)}`),
      { method: 'DELETE' }
    )
    const result = await response.json()
    if (!response.ok || !result?.success) {
      const message = result?.error?.message || `删除失败（HTTP ${response.status}）`
      props.showToast(message, 'error')
      return
    }
    const wasActive = target === props.wallpaperUrl
    await fetchGatewayWallpaper()
    if (wasActive) {
      const nextUrl = gatewayWallpaperUrl.value || ''
      wallpaperPreviewUrl.value = buildWallpaperAbsoluteUrl(nextUrl)
      emit('saveWallpaperSetting', nextUrl)
    }
    props.showToast('壁纸已删除', 'success')
  } catch (error) {
    console.warn('[WALLPAPER] Delete one failed:', error)
    props.showToast('删除壁纸失败，请检查网络或权限', 'error')
  } finally {
    wallpaperUploading.value = false
  }
}

// 移除壁纸：删除网关文件并清空本地设置
async function removeWallpaper() {
  wallpaperUploading.value = true
  try {
    const response = await props.fetchWithAuth(buildApiUrl('/api/wallpaper'), { method: 'DELETE' })
    const result = await response.json()
    if (!response.ok || !result?.success) {
      const message = result?.error?.message || `删除失败（HTTP ${response.status}）`
      props.showToast(message, 'error')
      return
    }
    wallpaperPreviewUrl.value = ''
    gatewayWallpapers.value = []
    wallpaperChecked.value = true
    emit('saveWallpaperSetting', '')
    props.showToast('壁纸已移除', 'success')
  } catch (error) {
    console.warn('[WALLPAPER] Remove failed:', error)
    props.showToast('移除壁纸失败，请检查网络或权限', 'error')
  } finally {
    wallpaperUploading.value = false
  }
}

// 透明度滑块：拖动时实时预览（不落盘），松手后持久化
function onUiOpacityInput(value) {
  localUiOpacity.value = normalizeOpacity(value)
  emit('update:uiOpacity', localUiOpacity.value)
}

function onUiOpacityCommit() {
  emit('saveUiOpacitySetting', localUiOpacity.value)
}

// 监听props变化
watch(() => props.autoLoginEnabled, (newVal) => {
  localAutoLoginEnabled.value = newVal
})

watch(() => props.notifyOnExit, (newVal) => {
  localNotifyOnExit.value = newVal
})

watch(() => props.notifyOnInput, (newVal) => {
  localNotifyOnInput.value = newVal
})

watch(() => props.nodeDisplayNames, (newVal) => {
  localNodeDisplayNames.value = { ...(newVal || {}) }
}, { deep: true })

watch(() => props.hideWorkingDir, (newVal) => {
  localHideWorkingDir.value = newVal
})
watch(() => props.autoInstallBrowserExt, (newVal) => {
  localAutoInstallBrowserExt.value = newVal
})

watch(() => props.terminalName, (newVal) => {
  localTerminalName.value = newVal
})

watch(() => props.daemonPort, (newVal) => {
  localDaemonPort.value = newVal
})
watch(() => props.wallpaperUrl, (newVal) => {
  // 外部（其他终端）更新壁纸时同步预览
  if (wallpaperUploading.value) return
  wallpaperPreviewUrl.value = buildWallpaperAbsoluteUrl(newVal)
})
watch(() => props.uiOpacity, (newVal) => {
  // 上传/拖动过程中避免被父组件回写覆盖
  if (wallpaperUploading.value) return
  localUiOpacity.value = normalizeOpacity(newVal)
})
// 设置弹窗打开时查询网关壁纸：换电脑/换浏览器后本机 localStorage 没有记录，
// 但网关已保存壁纸，需要让用户看到并启用（否则会以为壁纸丢了）。
watch(() => props.visible, (visible) => {
  if (visible) fetchGatewayWallpaper()
}, { immediate: true })

// 本机后台服务端口输入：更新本地副本并向上同步（父组件负责持久化到 localStorage）。
// 输入过程中不即时持久化，避免用户逐字符输入时反复写入半成品端口；失焦/回车时提交。
function onDaemonPortInput(value) {
  localDaemonPort.value = String(value || '').trim()
  emit('update:daemonPort', localDaemonPort.value)
}
function onDaemonPortCommit() {
  emit('saveDaemonPortSetting', localDaemonPort.value)
}

// 终端名称输入：更新本地副本并向上同步（父组件负责持久化与同步到扩展/daemon）
function onTerminalNameInput(value) {
  const trimmed = String(value || '').trim()
  localTerminalName.value = trimmed
  emit('update:terminalName', trimmed)
  emit('saveTerminalNameSetting', trimmed)
}

// 隐藏工作目录开关变更
function handleHideWorkingDirChange() {
  emit('update:hideWorkingDir', localHideWorkingDir.value)
  emit('saveHideWorkingDirSetting', localHideWorkingDir.value)
}
// 自动安装/更新浏览器扩展开关变更（父组件负责持久化到 localStorage 并推送给本机 daemon）
function handleAutoInstallBrowserExtChange() {
  emit('update:autoInstallBrowserExt', localAutoInstallBrowserExt.value)
  emit('saveAutoInstallBrowserExtSetting', localAutoInstallBrowserExt.value)
}

// 节点显示名输入：更新本地副本并向上同步（父组件负责持久化）
function onNodeNameInput(nodeId, value) {
  const next = { ...localNodeDisplayNames.value }
  const trimmed = String(value || '').trim()
  if (trimmed) next[nodeId] = trimmed
  else delete next[nodeId]
  localNodeDisplayNames.value = next
  emit('saveNodeDisplayNames', next)
}

// 关闭弹窗
function close() {
  emit('update:visible', false)
}

// 处理免登录设置变更
function handleAutoLoginChange() {
  emit('update:autoLoginEnabled', localAutoLoginEnabled.value)
  emit('saveAutoLoginSetting')
}

// 处理 Agent 退出通知开关变更
function handleNotifyOnExitChange() {
  emit('update:notifyOnExit', localNotifyOnExit.value)
  emit('saveNotifySettings')
}

// 处理需要输入通知开关变更
function handleNotifyOnInputChange() {
  emit('update:notifyOnInput', localNotifyOnInput.value)
  emit('saveNotifySettings')
}



// 确认清除历史
function confirmClearHistory() {
  emit('confirmClearHistory')
}



// 断开所有连接
function disconnectAll() {
  emit('disconnectAll')
}



// 修改密码
async function changePassword() {
  const form = changePasswordForm.value
  if (!form.old_password || !form.new_password) { props.showToast('旧密码和新密码不能为空', 'error'); return }
  if (form.new_password !== form.confirm_password) { props.showToast('两次输入的新密码不一致', 'error'); return }
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/users/${currentUserId.value}/change-password`), {
      method: 'POST', body: JSON.stringify({ old_password: form.old_password, new_password: form.new_password })
    })
    const result = await resp.json()
    if (result.success) { props.showToast('密码修改成功', 'success'); changePasswordForm.value = { old_password: '', new_password: '', confirm_password: '' } }
    else props.showToast(result.error?.message || '修改失败', 'error')
  } catch (e) { props.showToast('修改失败: ' + e.message, 'error') }
  finally { loading.value = false }
}




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
  z-index: 3000;
  padding: 20px;
}

/* 模态框基础样式 */
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

/* ========== Form Group 样式（从 App.vue 全局样式迁移） ========== */
.form-group {
  margin-bottom: 16px;
  padding: 16px;
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius-sm);
  box-shadow: 0 2px 8px var(--color-shadow);
}

.form-group.inline {
  display: flex;
  gap: 12px;
}

.form-group.inline .form-item {
  flex: 1;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

.form-group input {
  width: 100%;
  padding: 11px 14px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-primary);
}

.form-group select {
  width: 100%;
  padding: 11px 14px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%239ca3af' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 36px;
}

.form-group select:focus {
  outline: none;
  border-color: var(--color-accent);
  background-color: var(--color-bg-primary);
}

.form-group select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  padding: 8px;
}

/* ========== Toggle Switch 样式（从 App.vue 全局样式迁移） ========== */
.toggle-wrapper {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  border: none;
  outline: none;
  border-radius: 0;
  box-shadow: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-wrapper:hover {

  border-color: var(--color-accent);
  outline-color: var(--color-accent-subtle);
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

  border: none;
  box-shadow: var(--tile-shadow);
  border-radius: var(--tile-radius-sm);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  /* 外描边效果 */
  outline: none;
  outline-offset: -1px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 24px;
  width: 24px;
  left: 3px;
  bottom: 3px;
  background-color: var(--color-text-secondary);

  border-radius: 50%;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px var(--color-shadow);
  border: none;
}

.toggle-input:checked + .toggle-slider {
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-secondary) 100%);
  border-color: var(--color-accent);
  box-shadow: var(--tile-shadow);
  outline-color: var(--color-accent-subtle);
}

.toggle-input:checked + .toggle-slider:before {
  transform: translateX(22px);
  background-color: var(--color-text-primary);
  box-shadow: 0 2px 8px var(--color-shadow);
  border-color: var(--color-accent-subtle);
}

/* Hover 状态 */
.toggle-switch:hover .toggle-slider {

}

.toggle-switch:hover .toggle-slider:before {
  background-color: var(--color-text-primary);
}

/* Active 状态 - 物理回弹反馈 */
.toggle-switch:active .toggle-slider {
  transform: scale(0.95);
}

.toggle-switch:active .toggle-slider:before {
  transform: translateX(22px) scale(0.95);
}

/* 禁用状态 */
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

.form-help {
  display: block;
  margin: 0;
  padding: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

/* ========== SettingsModal 特有样式 ========== */
.settings-modal {
  max-width: 640px;
  max-height: 80vh;
  overflow-y: auto;
}

.settings-modal h2 {
  margin: 0 0 24px 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.03em;
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

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}

.danger-btn {
  padding: 10px 20px;
  background: var(--color-error);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.danger-btn:hover:not(:disabled) {
  background: var(--color-error);
  transform: translateY(-1px);
}

.danger-btn:active:not(:disabled) {
  transform: translateY(0);
}

.danger-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.history-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--color-bg-primary);
  border: none;
  border-radius: var(--tile-radius);
}

.history-stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.history-stat-value {
  font-size: 14px;
  color: var(--color-text-primary);
  font-weight: 600;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
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

.config-sync-section {
  margin-top: 16px;
  padding: 16px;
  background: transparent;
  border-radius: var(--tile-radius);
  border: none;
}

.config-sync-row {
  margin-bottom: 16px;
}

.config-sync-row:last-child {
  margin-bottom: 0;
}

.config-sync-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.config-sync-section .node-select {
  width: 100%;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  border: none;
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.config-sync-section .node-select:hover {
  border-color: var(--color-border-subtle);
}

.config-sync-section .node-select:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: var(--tile-shadow);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  border-radius: var(--tile-radius);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  color: var(--color-text-primary);
}

.checkbox-label:hover {
  background: var(--color-bg-secondary);
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-accent);
}

/* ========== 节点显示名映射样式 ========== */
.node-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.node-name-row:last-child {
  margin-bottom: 0;
}

.node-name-origin {
  flex: 0 0 40%;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-name-input {
  flex: 1;
  min-width: 0;
}

/* ========== 外观设置：壁纸与透明度 ========== */
.wallpaper-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.wallpaper-preview {
  flex: 0 0 168px;
  width: 168px;
  height: 96px;
  border-radius: var(--tile-radius-xs, 8px);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary, rgba(18, 30, 50, 0.65));
  border: 1px solid var(--color-border, rgba(32, 200, 255, 0.18));
  color: var(--text-secondary, #8ba3b8);
  font-size: 12px;
}

.wallpaper-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.wallpaper-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.wallpaper-actions .ghost-btn,
.wallpaper-actions .danger-btn {
  width: auto;
  margin: 0;
}

/* 原生 file input 隐藏，由「选择图片」按钮触发 */
.wallpaper-file-input {
  display: none;
}

/* 网关壁纸库缩略图 */
.wallpaper-gallery {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.wallpaper-thumb {
  position: relative;
  width: 88px;
  height: 52px;
  border-radius: var(--tile-radius-xs, 8px);
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  background: var(--color-bg-tertiary, rgba(18, 30, 50, 0.65));
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.wallpaper-thumb:hover {
  transform: translateY(-1px);
  border-color: var(--color-border-subtle, rgba(32, 200, 255, 0.35));
}

.wallpaper-thumb.active {
  border-color: var(--color-accent, #20c8ff);
  box-shadow: 0 0 0 1px var(--color-accent, #20c8ff);
}

.wallpaper-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.wallpaper-thumb-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  padding: 0;
  line-height: 16px;
  font-size: 14px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.wallpaper-thumb:hover .wallpaper-thumb-remove {
  opacity: 1;
}

.wallpaper-thumb-remove:hover {
  background: var(--color-error, #e5484d);
}

/* 网关壁纸状态提示 */
.wallpaper-hint {
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: var(--tile-radius-xs, 8px);
  background: rgba(32, 200, 255, 0.08);
  border-left: 2px solid var(--color-accent, #20c8ff);
  color: var(--text-secondary, #8ba3b8);
  font-size: 12px;
  line-height: 1.5;
}

.opacity-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.opacity-slider {
  flex: 1;
  min-width: 0;
  accent-color: var(--color-accent, #20c8ff);
  cursor: pointer;
}

.opacity-value {
  flex: 0 0 48px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary, #8ba3b8);
  font-size: 13px;
}

/* ========== 私钥显示区域样式 ========== */
.node-secret-section {
  margin-top: 12px;
  padding: 16px;
  background: transparent;
  border-radius: var(--tile-radius);
  border: none;
}

.secret-display {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--color-bg-primary);
  border-radius: var(--tile-radius);
  border: none;
}

.secret-code {
  flex: 1;
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 13px;
  color: var(--color-text-primary);
  word-break: break-all;
  min-width: 0;
}

.secret-placeholder {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-secondary);
  font-style: italic;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.copy-btn:hover:not(:disabled) {
  background: var(--color-bg-secondary);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.copy-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.secret-actions {
  display: flex;
  gap: 8px;
}

.secret-actions .ghost-btn {
  flex: 1;
  padding: 8px 16px;
  font-size: 13px;
}

/* ========== 重启节点服务区域样式 ========== */
.restart-service-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.restart-service-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ========== 配置同步按钮样式 ========== */
.config-sync-button {
  margin-top: 16px;
}


</style>
