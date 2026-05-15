/**
 * URL构建工具 Composable
 * 提供URL构建、协议处理等功能
 */

import { ref } from "vue";

export function useUrlBuilder() {
  /**
   * 获取当前页面的HTTP协议（http:// 或 https://）
   * @returns {string} 'http' 或 'https'
   */
  function getHttpProtocol() {
    return window.location.protocol === "https:" ? "https" : "http";
  }

  /**
   * 获取当前页面的WebSocket协议（ws:// 或 wss://）
   * @returns {string} 'ws' 或 'wss'
   */
  function getWebSocketProtocol() {
    return window.location.protocol === "https:" ? "wss" : "ws";
  }

  /**
   * 解析网关地址，支持完整URL格式
   * @param {string} address - 网关地址
   * @returns {object|null} 解析结果对象或null
   */
  function parseGatewayAddress(address) {
    // 移除首尾空格
    address = address.trim();

    // 如果是完整URL（包含协议）
    if (address.includes("://")) {
      try {
        const url = new URL(address);
        return {
          protocol: url.protocol.replace(":", ""), // 'ws', 'wss', 'http', 'https'
          host: url.hostname,
          port:
            url.port ||
            (url.protocol === "https:" || url.protocol === "wss:"
              ? "443"
              : "80"),
          path: url.pathname,
        };
      } catch (e) {
        console.error("[URL] Failed to parse address:", address, e);
        return null;
      }
    }

    // 如果是 host:port 格式
    if (address.includes(":")) {
      const parts = address.split(":");
      if (parts.length === 2) {
        return {
          protocol: null, // 使用默认协议
          host: parts[0],
          port: parts[1],
          path: "",
        };
      }
    }

    // 如果只有主机名（使用默认端口）
    return {
      protocol: null,
      host: address,
      port: "8000",
      path: "",
    };
  }

  /**
   * 获取网关地址（host和port）
   * @param {string} gatewayUrl - 网关URL
   * @returns {object} 包含host和port的对象
   */
  function getGatewayAddress(gatewayUrl) {
    const parsed = parseGatewayAddress(gatewayUrl);
    if (!parsed) {
      return {
        host: "127.0.0.1",
        port: "8000",
      };
    }
    return {
      host: parsed.host || "127.0.0.1",
      port: parsed.port || "8000",
    };
  }

  /**
   * 构建节点HTTP基础路径
   * @param {string} host - 主机名
   * @param {string} port - 端口号
   * @param {string} nodeId - 节点ID，默认为'master'
   * @param {string} path - 路径
   * @param {string} protocol - 协议，可选
   * @returns {string} 完整的HTTP URL
   */
  function buildNodeHttpUrl(
    host,
    port,
    nodeId = "master",
    path = "",
    protocol = null,
  ) {
    const httpProtocol = protocol || getHttpProtocol();
    const normalizedNodeId = String(nodeId || "master").trim() || "master";
    const normalizedPath = `/${String(path || "").replace(/^\/+/, "")}`;
    return `${httpProtocol}://${host}:${port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`;
  }

  /**
   * 构建节点WebSocket基础路径
   * @param {string} host - 主机名
   * @param {string} port - 端口号
   * @param {string} nodeId - 节点ID，默认为'master'
   * @param {string} path - 路径
   * @param {string} protocol - 协议，可选
   * @returns {string} 完整的WebSocket URL
   */
  function buildNodeWebSocketUrl(
    host,
    port,
    nodeId = "master",
    path = "",
    protocol = null,
  ) {
    const wsProtocol = protocol || getWebSocketProtocol();
    const normalizedNodeId = String(nodeId || "master").trim() || "master";
    const normalizedPath = `/${String(path || "").replace(/^\/+/, "")}`;
    return `${wsProtocol}://${host}:${port}/api/node/${encodeURIComponent(normalizedNodeId)}${normalizedPath}`;
  }

  /**
   * 构建WebSocket URL（用于网关连接）
   * @param {string} host - 主机名
   * @param {string} port - 端口号
   * @param {string} protocol - 协议，可选
   * @returns {string} WebSocket URL
   */
  function buildWebSocketUrl(host, port, protocol = null) {
    return buildNodeWebSocketUrl(host, port, "master", "ws", protocol);
  }

  /**
   * 构建Agent WebSocket URL（通过统一节点代理）
   * @param {string} host - 主机名
   * @param {string} agentId - Agent ID
   * @param {string} protocol - 协议，可选
   * @param {string} port - 端口号，可选
   * @param {string} nodeId - 节点ID，默认为空
   * @returns {string} Agent WebSocket URL
   */
  function buildAgentWebSocketUrl(
    host,
    agentId,
    protocol = null,
    port = null,
    nodeId = "",
  ) {
    const normalizedNodeId = String(nodeId || "master").trim() || "master";
    return buildNodeWebSocketUrl(
      host,
      port,
      normalizedNodeId,
      `agent/${agentId}/ws`,
      protocol,
    );
  }

  /**
   * 构建HTTP URL
   * @param {string} host - 主机名
   * @param {string} port - 端口号
   * @param {string} path - 路径
   * @param {string} protocol - 协议，可选
   * @returns {string} HTTP URL
   */
  function buildHttpUrl(host, port, path, protocol = null) {
    const normalizedPath = String(path || "").replace(/^\/+/, "");
    return buildNodeHttpUrl(host, port, "master", normalizedPath, protocol);
  }

  /**
   * 构建WebSocket协议列表
   * @param {string} token - 认证令牌
   * @returns {array} 协议列表
   */
  function buildWebSocketProtocols(token) {
    const tokenStr = String(token || "").trim();
    if (!tokenStr) {
      return ["jarvis-ws"];
    }
    return ["jarvis-ws", `jarvis-token.${encodeURIComponent(tokenStr)}`];
  }

  return {
    getHttpProtocol,
    getWebSocketProtocol,
    parseGatewayAddress,
    getGatewayAddress,
    buildNodeHttpUrl,
    buildNodeWebSocketUrl,
    buildWebSocketUrl,
    buildAgentWebSocketUrl,
    buildHttpUrl,
    buildWebSocketProtocols,
  };
}
