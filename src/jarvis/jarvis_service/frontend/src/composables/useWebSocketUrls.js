/**
 * WebSocket URL构建工具函数
 * 负责WebSocket URL的解析和构建
 */

// 获取当前页面的WebSocket协议（ws://或wss://）
export function getWebSocketProtocol() {
  return window.location.protocol === 'https:' ? 'wss' : 'ws'
}

// 解析网关地址，支持完整URL格式（如ws://example.com:8080/ws或example.com:8080）
export function parseGatewayAddress(address) {
  // 移除首尾空格
  address = address.trim()

  // 如果是完整URL（包含协议）
  if (address.includes('://')) {
    try {
      const url = new URL(address)
      return {
        protocol: url.protocol.replace(':', ''),  // 'ws', 'wss', 'http', 'https'
        host: url.hostname,
        port: url.port || (url.protocol === 'https:' || url.protocol === 'wss:' ? '443' : '80'),
        path: url.pathname
      }
    } catch (e) {
      console.error('[URL] Failed to parse address:', address, e)
      return null
    }
  }

  // 如果是host:port格式
  if (address.includes(':')) {
    const parts = address.split(':')
    if (parts.length === 2) {
      return {
        protocol: null,  // 使用默认协议
        host: parts[0],
        port: parts[1],
        path: ''
      }
    }
  }

  // 如果只有主机名（使用默认端口）
  return {
    protocol: null,
    host: address,
    port: '8000',
    path: ''
  }
}

// 构建节点WebSocket基础路径
export function buildNodeWebSocketUrl(host, port, nodeId = 'master', path = '', protocol = null) {
  const wsProtocol = protocol || getWebSocketProtocol()
  const normalizedNodeId = String(nodeId || 'master').trim() || 'master'
  const normalizedPath = `/${String(path || '').replace(/^/+/g, '')}`
  return `${wsProtocol}://${host}:${port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`
}

// 构建WebSocket URL（用于网关连接）
export function buildWebSocketUrl(host, port, protocol = null) {
  return buildNodeWebSocketUrl(host, port, 'master', 'ws', protocol)
}

// 构建Agent WebSocket URL（通过统一节点代理）
export function buildAgentWebSocketUrl(host, agentId, protocol = null, port = null, nodeId = '') {
  const normalizedNodeId = String(nodeId || 'master').trim() || 'master'
  return buildNodeWebSocketUrl(host, port, normalizedNodeId, `agent/${agentId}/ws`, protocol)
}

// 构建WebSocket协议头
export function buildWebSocketProtocols(authToken) {
  const token = String(authToken || '').trim()
  if (!token) {
    return ['jarvis-ws']
  }
  return ['jarvis-ws', `jarvis-token.${encodeURIComponent(token)}`]
}

// 获取网关地址（host和port）
export function getGatewayAddress(gatewayUrl) {
  const parsed = parseGatewayAddress(gatewayUrl)
  if (!parsed) {
    return { host: '127.0.0.1', port: '8000' }
  }
  return {
    host: parsed.host || window.location.hostname || '127.0.0.1',
    port: parsed.port || '8000'
  }
}