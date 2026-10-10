import { ref } from 'vue'

// 本机 daemon 登录态同步 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出，保持行为完全一致：
// - 前端 token 变化时，自动把「远程网关地址 + token」推送给本机 jarvis-daemon，
//   让 daemon 无需用户手动配置即可感知登录态（daemon 侧多网关并存，互不顶掉）。
// - daemon 在线探测：探测本机回环 /api/status，用于隐藏大厅的「安装本地后台服务」引导入口。
// - daemon 端口设置：写 localStorage 后立即用新地址重新推送一次登录态。
//
// 依赖注入：
// - auth：ref({ password, token, userInfo })
// - terminalName：ref(string)（终端名称，随 /api/auth 推送）
// - autoInstallBrowserExt：ref(boolean)（自动安装/更新浏览器扩展开关，随登录态推送）
// - getGateway：函数（返回当前网关的 HTTP 基地址，由调用方注入；
//   实际来自 window.__jarvisAuthBridge.getGateway()，此处注入以避免循环依赖）
export function useDaemonSync({ auth, terminalName, autoInstallBrowserExt, getGateway }) {
  // 注意：gateway 是远程网关地址，daemon 地址是本机回环，两者必须分开。
  const DAEMON_DEFAULT_URL = 'http://127.0.0.1:17800'
  const DAEMON_URL_STORAGE_KEY = 'jarvis_daemon_url'
  const DAEMON_DEFAULT_PORT = '17800'

  // 规范化 daemon 地址：去空白、补 http:// 前缀、去尾部斜杠。
  // 空串返回空串（调用方决定是否回退默认值），便于设置页区分「未配置」。
  function normalizeDaemonUrl(value) {
    let url = String(value || '').trim()
    if (!url) return ''
    if (!/^https?:\/\//i.test(url)) url = 'http://' + url
    return url.replace(/\/+$/, '')
  }

  // 从已保存的 daemon 地址中提取端口号（设置页只暴露端口，IP 恒为回环 127.0.0.1）。
  function extractDaemonPort(url) {
    const normalized = normalizeDaemonUrl(url)
    if (!normalized) return ''
    try {
      return new URL(normalized).port || ''
    } catch {
      return ''
    }
  }

  // 解析本机 daemon 地址：默认回环 17800，允许 localStorage 覆盖（设置页可改端口，便于端口被占用时自定义）
  function getDaemonUrl() {
    let url
    try {
      url = localStorage.getItem(DAEMON_URL_STORAGE_KEY) || ''
    } catch {
      url = ''
    }
    return normalizeDaemonUrl(url) || DAEMON_DEFAULT_URL
  }

  // 设置页展示用的端口（未配置时展示默认端口，便于用户在此基础上改）
  function loadDaemonPort() {
    let url
    try {
      url = localStorage.getItem(DAEMON_URL_STORAGE_KEY) || ''
    } catch {
      url = ''
    }
    return extractDaemonPort(url) || DAEMON_DEFAULT_PORT
  }

  const daemonPort = ref(loadDaemonPort())
  // 保存 daemon 端口：只接受端口号（IP 恒为本机回环 127.0.0.1）。
  // 写 localStorage 后立即用新地址重新推送一次登录态，使用户改完端口无需刷新页面即可让后续请求走新端口。
  function saveDaemonPortSetting(nextValue = daemonPort.value) {
    const port = String(nextValue || '').trim()
    // 留空或等于默认端口则清除覆盖项，回到默认地址
    if (!port || port === DAEMON_DEFAULT_PORT) {
      daemonPort.value = DAEMON_DEFAULT_PORT
      try {
        localStorage.removeItem(DAEMON_URL_STORAGE_KEY)
      } catch (error) {
        console.warn('[DAEMON] Failed to clear daemon port:', error)
      }
    } else {
      daemonPort.value = port
      try {
        localStorage.setItem(DAEMON_URL_STORAGE_KEY, `http://127.0.0.1:${port}`)
      } catch (error) {
        console.warn('[DAEMON] Failed to save daemon port:', error)
      }
    }
    // 端口变化后立即重新推送一次给本机 daemon（与终端名称/扩展开关一致的做法）
    syncTokenToDaemon(auth.value.token, getGateway())
  }

  // 本机是否已安装并运行 daemon：探测本机回环 /api/status（daemon 监听 127.0.0.1，CORS 全开、无需鉴权）。
  // 用本机探测而非网关 /api/daemon/sessions：后者是全局会话，多机在线时会串到别人的设备。
  // 探测成功即认为「本机已装 daemon」，前端据此隐藏大厅的安装引导入口（与浏览器扩展的隐藏逻辑一致）。
  const localDaemonOnline = ref(false)
  let localDaemonProbeTimer = null
  async function probeLocalDaemon() {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 1500)
    try {
      const resp = await fetch(`${getDaemonUrl()}/api/status`, {
        signal: controller.signal,
        credentials: 'omit',
      })
      if (!resp.ok) {
        localDaemonOnline.value = false
        return
      }
      const data = await resp.json()
      localDaemonOnline.value = !!data?.success
    } catch {
      // daemon 未安装/未启动属预期情况，静默视为离线
      localDaemonOnline.value = false
    } finally {
      clearTimeout(timer)
    }
  }
  function startLocalDaemonProbe() {
    if (localDaemonProbeTimer) return
    probeLocalDaemon()
    localDaemonProbeTimer = setInterval(probeLocalDaemon, 10000)
  }
  function stopLocalDaemonProbe() {
    if (localDaemonProbeTimer) {
      clearInterval(localDaemonProbeTimer)
      localDaemonProbeTimer = null
    }
  }

  // 把当前登录态同步到本机 daemon。
  // token 非空 → POST /api/auth {gateway, token, name}；token 为空 → POST /api/logout {gateway}。
  // name 即「终端名称」，daemon 会在向网关登录（hello 帧）时带上，供网关区分终端。
  // 完全 fire-and-forget：不 await、不抛错、不弹 toast、不阻塞主流程；daemon 不存在时静默。
  function syncTokenToDaemon(token, gateway) {
    try {
      if (!gateway) return
      const daemonUrl = getDaemonUrl()
      const isLogout = !token
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 1500)
      fetch(`${daemonUrl}${isLogout ? '/api/logout' : '/api/auth'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          isLogout
            ? { gateway }
            : {
                gateway,
                token,
                name: terminalName.value || '',
                // 随登录态一并推送「自动安装/更新浏览器扩展」开关，daemon 据此决定
                // 是否在网关扩展版本变化时自动同步（daemon 只存内存态，不落盘）。
                auto_install_browser_ext: autoInstallBrowserExt.value,
              },
        ),
        signal: controller.signal,
        credentials: 'omit',
      })
        .then(() => {})
        .catch((e) => {
          // daemon 不存在（连接被拒）或超时属预期情况，只留 debug 级日志，不产生噪音
          console.debug('[AUTH] sync token to daemon skipped:', e?.message || e)
        })
        .finally(() => clearTimeout(timer))
    } catch (e) {
      console.debug('[AUTH] sync token to daemon failed:', e?.message || e)
    }
  }

  return {
    daemonPort,
    localDaemonOnline,
    normalizeDaemonUrl,
    extractDaemonPort,
    getDaemonUrl,
    loadDaemonPort,
    saveDaemonPortSetting,
    probeLocalDaemon,
    startLocalDaemonProbe,
    stopLocalDaemonProbe,
    syncTokenToDaemon,
  }
}
