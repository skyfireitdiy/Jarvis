// 浏览器扩展登录态桥接 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出，保持行为完全一致：
// 供 Jarvis 浏览器扩展读取当前登录态，避免用户重复登录或手填 Token。
// 扩展通过主世界脚本调用 window.__jarvisAuthBridge.getToken() 获取 Token，
// 并通过 getGateway() 获取当前配置的网关地址（网关与前端可能不同域名），
// 以便扩展把 Token 关联到正确的网关。
//
// 依赖注入：
// - auth：ref({ password, token, userInfo })
// - terminalName：ref(string)（终端名称，供扩展随 hello 上报给网关）
// - gatewayUrl：ref(string)（当前配置的网关地址，ws(s)://host:port）
// - parseGatewayAddress：函数（解析网关地址为 { protocol, host, port }）
// - syncTokenToDaemon：函数（token, gateway）→ 手动触发一次 daemon 同步
export function useAuthBridge({ auth, terminalName, gatewayUrl, parseGatewayAddress, syncTokenToDaemon }) {
  function installAuthBridge() {
    window.__jarvisAuthBridge = {
      // 优先返回内存中的 Token；内存为空时回退 localStorage（免登录场景下
      // jarvis_auth_token 已持久化），让浏览器扩展在持久化 Token 失效时能靠页面兜底恢复。
      // 注意：本页面只服务当前配置的单个网关（见 getGateway），localStorage 中的
      // Token 即属于该网关，扩展会按 getGateway() 声明的网关做匹配，天然支持多网关。
      getToken: () => auth.value.token || localStorage.getItem('jarvis_auth_token') || null,
      // 终端名称：供扩展随 hello 上报给网关，使网关能区分不同终端。
      getName: () => terminalName.value || null,
      getGateway: () => {
        const parsed = parseGatewayAddress(gatewayUrl.value)
        if (!parsed) return null
        // 网关地址可能以 ws(s):// 配置（前端连 WebSocket 用），但这里要交给
        // daemon 作为「HTTP 基地址」使用，必须保留传输安全性：
        // wss→https、ws→http。若一律降级成 http，daemon 会以明文 ws 去连
        // HTTPS 端口，被 nginx 以 400 拒绝，表现为 websocket: bad handshake。
        const schemeMap = { ws: 'http', wss: 'https', http: 'http', https: 'https' }
        const scheme = schemeMap[parsed.protocol] || parsed.protocol || 'http'
        const host = parsed.host || window.location.hostname || '127.0.0.1'
        const port = parsed.port || '8000'
        return `${scheme}://${host}:${port}`
      },
      // 供真实浏览器验证/排查时手动触发一次 daemon 同步
      syncToDaemon: () => syncTokenToDaemon(auth.value.token, window.__jarvisAuthBridge.getGateway()),
    }
  }

  return {
    installAuthBridge,
  }
}
