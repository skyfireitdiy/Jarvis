/**
 * LSP 语言服务器清单注册表。
 *
 * 数据全部来自后端 `GET /api/lsp/servers`，前端不做任何语言硬编码：
 * 新增语言只需在后端 `lsp_servers/` 丢一个清单 JSON，本文件无需改动。
 *
 * 清单字段（后端返回）：
 *   id            语言服务器唯一标识，如 "python"
 *   monacoLanguage 对应的 Monaco 语言 id，如 "python"
 *   extensions    文件扩展名列表，如 [".py", ".pyi"]
 *   installHint   服务器未安装时的提示文案
 *   source        来源，"builtin" | "user"
 */

/** @type {Map<string, object>} monacoLanguage -> serverSpec */
let serverByLanguage = new Map();

/** @type {Map<string, object>} extension(小写,含点) -> serverSpec */
let serverByExtension = new Map();

let loaded = false;
let loadPromise = null;

/**
 * 拉取清单并建立索引。失败时静默降级为空映射（不抛异常）。
 *
 * @param {object} deps
 * @param {(path: string, options?: object) => Promise<Response>} deps.fetchWithAuth
 * @param {() => {host: string, port: string}} deps.getGatewayAddress
 * @param {() => string} deps.getHttpProtocol
 * @param {boolean} [force] 强制重新拉取（忽略缓存）
 * @returns {Promise<Map<string, object>>} monacoLanguage -> serverSpec
 */
export async function loadLspServers(
  { fetchWithAuth, getGatewayAddress, getHttpProtocol },
  force = false,
) {
  if (loaded && !force) return serverByLanguage;
  if (loadPromise && !force) return loadPromise;

  loadPromise = (async () => {
    try {
      const { host, port } = getGatewayAddress();
      const protocol = getHttpProtocol();
      const url = `${protocol}://${host}:${port}/api/lsp/servers`;
      const response = await fetchWithAuth(url, { method: "GET" });
      if (!response.ok) {
        console.warn(`[lsp] 拉取语言服务器清单失败: HTTP ${response.status}`);
        return serverByLanguage;
      }
      const result = await response.json();
      const servers = Array.isArray(result?.servers) ? result.servers : [];

      const byLang = new Map();
      const byExt = new Map();
      for (const spec of servers) {
        if (!spec || !spec.id || !spec.monacoLanguage) continue;
        // 同一语言出现多个服务器时，user 来源优先（与后端覆盖语义一致）
        const existing = byLang.get(spec.monacoLanguage);
        if (
          !existing ||
          (spec.source === "user" && existing.source !== "user")
        ) {
          byLang.set(spec.monacoLanguage, spec);
        }
        for (const ext of spec.extensions || []) {
          byExt.set(String(ext).toLowerCase(), spec);
        }
      }
      serverByLanguage = byLang;
      serverByExtension = byExt;
      loaded = true;
    } catch (error) {
      console.warn(
        "[lsp] 拉取语言服务器清单异常，已降级为无 LSP:",
        error?.message || error,
      );
    }
    return serverByLanguage;
  })();

  return loadPromise;
}

/**
 * 按 Monaco 语言 id 查服务器清单。
 * @param {string} monacoLanguage
 * @returns {object|null}
 */
export function getServerByLanguage(monacoLanguage) {
  if (!monacoLanguage) return null;
  return serverByLanguage.get(String(monacoLanguage)) || null;
}

/**
 * 按文件扩展名查服务器清单（备用路径，语言 id 不可靠时使用）。
 * @param {string} path
 * @returns {object|null}
 */
export function getServerByPath(path) {
  if (!path) return null;
  const match = String(path).match(/(\.[^./\\]+)$/);
  if (!match) return null;
  return serverByExtension.get(match[1].toLowerCase()) || null;
}

/** 清单是否已成功加载过。 */
export function isLspRegistryLoaded() {
  return loaded;
}
