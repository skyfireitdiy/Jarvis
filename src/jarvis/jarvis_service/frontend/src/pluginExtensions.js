// 插件前端扩展加载器（方案2：运行时动态加载）。
//
// 前端是 vite 构建的静态产物，插件无法参与构建。插件 config.yaml 声明
// `frontend` 扩展点（admin_tabs / sidebar_views / tool_panels），后端按节点
// serve 插件前端资源（GET /api/plugins/{node_id}/{name}/frontend/{path}，
// 返回 JSON 包裹的 content）。本模块负责：
//   - 拉取扩展清单（fetchPluginExtensions）
//   - 动态加载插件 JS 为 Vue 组件（loadExtensionComponent）
//
// 插件 JS 是纯浏览器 ES module，通过全局 window.Vue（main.js 暴露）使用 Vue，
// 不 import 'vue'，导出 Vue 组件定义（渲染函数或 options 对象均可）。

// 已加载组件缓存：`${nodeId}/${pluginName}/${extType}/${extId}` -> Promise<Component|null>
const componentCache = new Map();

/**
 * 从后端拉取指定节点的插件扩展清单。
 *
 * @param {object} opts
 * @param {Function} opts.fetchWithAuth 带认证的 fetch（App.vue 注入）
 * @param {string} [opts.nodeId='master'] 目标节点
 * @param {string} opts.baseUrl 网关地址（如 http://host:port）
 * @param {Function} [opts.getHttpProtocol] 协议函数（http/https）
 * @returns {Promise<Array>} 扩展清单数组，每项形如：
 *   { nodeId, plugin, extType, id, title, entry, url }
 *   失败时返回空数组（不影响主界面）。
 */
export async function fetchPluginExtensions({
  fetchWithAuth,
  nodeId = "master",
  baseUrl,
  getHttpProtocol,
}) {
  const extensions = [];
  try {
    const protocol =
      typeof getHttpProtocol === "function" ? getHttpProtocol() : "http";
    const url = `${protocol}://${baseUrl}/api/plugins?node_id=${encodeURIComponent(nodeId)}`;
    const resp = await fetchWithAuth(url);
    if (!resp || !resp.ok) return extensions;
    const result = await resp.json();
    if (!result || !result.success) return extensions;
    const plugins = (result.data && result.data.plugins) || [];
    for (const plugin of plugins) {
      const frontend = plugin && plugin.frontend;
      if (!frontend || typeof frontend !== "object") continue;
      for (const extType of ["admin_tabs", "sidebar_views", "tool_panels"]) {
        const list = frontend[extType];
        if (!Array.isArray(list)) continue;
        for (const ext of list) {
          if (!ext || !ext.id || !ext.entry) continue;
          extensions.push({
            nodeId,
            plugin: plugin.name,
            pluginVersion: plugin.version,
            extType,
            id: ext.id,
            title: ext.title || ext.id,
            entry: ext.entry,
            icon: ext.icon || null,
            iconSvg: null,
            url: buildExtensionUrl({
              nodeId,
              plugin: plugin.name,
              entry: ext.entry,
              baseUrl,
              getHttpProtocol,
            }),
          });
        }
      }
    }
    // 为配置了图标文件路径的扩展加载 SVG 内容（内联 SVG 直接使用）
    await Promise.all(
      extensions.map(async (ext) => {
        if (!ext.icon) return;
        if (
          typeof ext.icon === "string" &&
          ext.icon.trim().startsWith("<svg")
        ) {
          ext.iconSvg = ext.icon;
          return;
        }
        try {
          const iconUrl = buildExtensionUrl({
            nodeId,
            plugin: ext.plugin,
            entry: ext.icon,
            baseUrl,
            getHttpProtocol,
          });
          const resp = await fetchWithAuth(iconUrl);
          if (!resp || !resp.ok) return;
          const result = await resp.json();
          if (!result || !result.success) return;
          const svg = result.data && result.data.content;
          if (typeof svg === "string" && svg.trim()) ext.iconSvg = svg;
        } catch (e) {
          console.warn(
            `[PluginExtensions] Failed to load icon for ${ext.plugin}/${ext.id}:`,
            e,
          );
        }
      }),
    );
  } catch (e) {
    console.warn("[PluginExtensions] Failed to fetch plugin extensions:", e);
  }
  return extensions;
}

/**
 * 构造插件前端资源的 serve 端点 URL。
 * GET /api/plugins/{node_id}/{name}/frontend/{path}
 */
export function buildExtensionUrl({
  nodeId,
  plugin,
  entry,
  baseUrl,
  getHttpProtocol,
}) {
  const protocol =
    typeof getHttpProtocol === "function" ? getHttpProtocol() : "http";
  const path = String(entry || "").replace(/^\/+/, "");
  return `${protocol}://${baseUrl}/api/plugins/${encodeURIComponent(nodeId)}/${encodeURIComponent(plugin)}/frontend/${path}`;
}

/**
 * 动态加载插件前端 JS 为 Vue 组件。
 *
 * 后端 serve_frontend 返回 JSON 包裹的 content（JS 源码字符串），无法直接
 * import(url)。这里先 fetch 拿到源码，用 Blob URL 创建 module 再 import()。
 * 插件 JS 应为单文件自包含（不引用相对路径资源），否则 Blob module 无法解析。
 *
 * @param {object} ext 扩展清单项（fetchPluginExtensions 返回的元素）
 * @param {object} opts { fetchWithAuth, getHttpProtocol }
 * @returns {Promise<Component|null>} Vue 组件（default export），失败返回 null
 */
export async function loadExtensionComponent(
  ext,
  { fetchWithAuth, getHttpProtocol } = {},
) {
  if (!ext) return null;
  const cacheKey = `${ext.nodeId}/${ext.plugin}/${ext.extType}/${ext.id}`;
  if (componentCache.has(cacheKey)) return componentCache.get(cacheKey);

  const promise = (async () => {
    try {
      const protocol =
        typeof getHttpProtocol === "function" ? getHttpProtocol() : "http";
      const url = buildExtensionUrl({
        nodeId: ext.nodeId,
        plugin: ext.plugin,
        entry: ext.entry,
        baseUrl: urlHost(ext.url),
        getHttpProtocol: () => protocol,
      });
      const resp = await fetchWithAuth(url);
      if (!resp || !resp.ok) return null;
      const result = await resp.json();
      if (!result || !result.success) return null;
      const source = result.data && result.data.content;
      if (typeof source !== "string" || !source.trim()) return null;

      const blob = new Blob([source], { type: "application/javascript" });
      const blobUrl = URL.createObjectURL(blob);
      try {
        const mod = await import(/* @vite-ignore */ blobUrl);
        return mod && mod.default ? mod.default : null;
      } finally {
        URL.revokeObjectURL(blobUrl);
      }
    } catch (err) {
      console.warn(
        `[PluginExtensions] Failed to load extension ${ext.plugin}/${ext.id}:`,
        err,
      );
      return null;
    }
  })();

  componentCache.set(cacheKey, promise);
  return promise;
}

// 从完整 URL 中提取 host:port（用于构造 serve 端点）
function urlHost(url) {
  try {
    const parsed = new URL(url);
    return parsed.host;
  } catch {
    return "";
  }
}

/** 清空组件缓存（卸载/升级插件后可调用） */
export function clearExtensionCache() {
  componentCache.clear();
}
