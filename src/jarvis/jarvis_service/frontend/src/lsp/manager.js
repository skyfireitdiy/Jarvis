/**
 * 轻量 LSP 客户端管理器。
 *
 * 职责：
 *  - 按 (serverId, workspaceRoot) 复用 WebSocket 连接
 *  - 自建 JSON-RPC 通道（id 自增 + Promise map），不依赖 monaco.lsp 的全量同步器
 *  - 文档同步（didOpen / didChange / didClose）只针对目标语言的 model
 *  - 注册 hover / completion / diagnostics 三个语言特性 provider，按语言隔离
 *  - 失败静默降级：连接失败或服务器未安装时仅 console.warn，不影响编辑器
 *
 * ## 为什么自建（重要）
 *
 * `monaco.lsp` 的 `MonacoLspClient` 内置 `TextDocumentSynchronizer`，在 initialize
 * 完成后会**全量接管** `monaco.editor.getModels()` 里的所有 model，且无法按语言过滤。
 * 若直接使用，Python server 会收到 Go 文件的 didOpen，且无法多语言多 server 共存。
 * 早期实现用"dispose 非目标语言 model"规避，会破坏多标签（切标签丢 undo 栈）。
 *
 * 因此这里自建轻量客户端：只复用原生 WebSocket，自己管理 JSON-RPC 与文档同步，
 * provider 用 `monaco.languages.registerXxxProvider(语言, ...)` 天然按语言隔离，
 * **绝不 dispose 任何 model**。
 */

import * as monaco from "monaco-editor/esm/vs/editor/editor.main.js";

/** @type {Map<string, {client: LspClient, socket: WebSocket, spec: object, root: string, models: Set<object>, subs: Map<object, {changeSub: object, disposeSub: object}>}>} */
const sessions = new Map();

/** 已注册 provider 的语言集合，避免重复注册。 */
const registeredProviders = new Set();

function sessionKey(serverId, root) {
  return `${serverId}::${root || ""}`;
}

/**
 * 轻量 JSON-RPC over WebSocket 客户端。
 * 请求用自增 id 匹配响应；通知单向发送；服务端主动消息（如 publishDiagnostics）走回调。
 */
class LspClient {
  /**
   * @param {WebSocket} socket
   * @param {object} opts
   * @param {(msg: object) => void} [opts.onNotification] 处理服务端主动通知
   */
  constructor(socket, opts = {}) {
    this.socket = socket;
    this.onNotification = opts.onNotification || (() => {});
    this._seq = 0;
    this._pending = new Map(); // id -> {resolve, reject}
    this._ready = new Promise((resolve, reject) => {
      this._readyResolve = resolve;
      this._readyReject = reject;
    });
    this._initialize();
  }

  _initialize() {
    this.socket.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!msg || typeof msg !== "object") return;
      if (typeof msg.id === "number" || typeof msg.id === "string") {
        // 请求的响应
        const pending = this._pending.get(msg.id);
        if (pending) {
          this._pending.delete(msg.id);
          if (msg.error)
            pending.reject(new Error(msg.error.message || "LSP error"));
          else pending.resolve(msg.result);
        }
      } else if (msg.method) {
        // 服务端主动通知（如 publishDiagnostics）
        this.onNotification(msg);
      }
    };
    this.socket.onerror = () => {
      this._failAll(new Error("LSP WebSocket error"));
    };
    this.socket.onclose = () => {
      this._failAll(new Error("LSP WebSocket closed"));
    };
    // 标记 ready（socket 已 open 由调用方保证）
    this._readyResolve();
  }

  _failAll(err) {
    for (const [, pending] of this._pending) pending.reject(err);
    this._pending.clear();
  }

  /** 等待初始化握手完成（可选，连接建立后即可用）。 */
  ready() {
    return this._ready;
  }

  /**
   * 发送 JSON-RPC 请求，返回 Promise<result>。
   * @param {string} method
   * @param {object} params
   */
  request(method, params) {
    const id = ++this._seq;
    return new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      try {
        this.socket.send(
          JSON.stringify({ jsonrpc: "2.0", id, method, params: params || {} }),
        );
      } catch (err) {
        this._pending.delete(id);
        reject(err);
      }
    });
  }

  /** 发送 JSON-RPC 通知（无响应）。 */
  notify(method, params) {
    try {
      this.socket.send(
        JSON.stringify({ jsonrpc: "2.0", method, params: params || {} }),
      );
    } catch {
      /* 忽略发送失败 */
    }
  }

  close() {
    try {
      this.socket.close();
    } catch {
      /* ignore */
    }
    this._failAll(new Error("LSP client closed"));
  }
}

/**
 * 建立到语言服务器的 WebSocket，并完成 LSP initialize 握手。
 *
 * @param {object} params
 * @param {object} params.spec 语言服务器清单
 * @param {string} params.workspaceRoot workspace 根目录
 * @param {object} params.deps
 * @returns {Promise<LspClient>}
 */
async function connectLspClient({ spec, workspaceRoot, deps }) {
  const { host, port } = deps.getGatewayAddress();
  const wsProtocol = deps.getWebSocketProtocol();
  const rootParam = workspaceRoot
    ? `?root=${encodeURIComponent(workspaceRoot)}`
    : "";
  const url = `${wsProtocol}://${host}:${port}/api/lsp/${encodeURIComponent(spec.id)}${rootParam}`;

  const socket = await openLspSocket({
    url,
    protocols: deps.buildWebSocketProtocols(),
  });

  const client = new LspClient(socket, {
    onNotification: (msg) => handleServerNotification(spec, msg),
  });

  // LSP initialize 握手
  const capabilities = await client.request("initialize", {
    processId: null,
    rootUri: workspaceRoot ? `file://${workspaceRoot}` : null,
    capabilities: {
      textDocument: {
        hover: { contentFormat: ["markdown", "plaintext"] },
        completion: { completionItem: { snippetSupport: true } },
        publishDiagnostics: {},
      },
    },
  });
  client.notify("initialized", {});

  // 按服务器能力注册语言特性 provider
  registerLanguageFeatures(spec, capabilities || {});
  return client;
}

/** 打开 WebSocket 并等待握手（带超时）。 */
function openLspSocket({ url, protocols, timeoutMs = 8000 }) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let socket;
    try {
      socket = new WebSocket(url, protocols);
    } catch (error) {
      reject(error);
      return;
    }
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        socket.close();
      } catch {
        /* ignore */
      }
      reject(new Error("LSP WebSocket 连接超时"));
    }, timeoutMs);
    socket.onopen = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(socket);
    };
    socket.onerror = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(new Error("LSP WebSocket 连接失败"));
    };
    socket.onclose = (event) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(
        new Error(
          `LSP WebSocket 被关闭: code=${event?.code} reason=${event?.reason || ""}`,
        ),
      );
    };
  });
}

/**
 * 处理服务端主动通知（目前只有 publishDiagnostics）。
 * 按通知里的 uri 找到对应 Monaco model，写入诊断标记。
 */
function handleServerNotification(spec, msg) {
  if (msg.method === "textDocument/publishDiagnostics") {
    const params = msg.params || {};
    const uri = String(params.uri || "").toLowerCase();
    // 遍历所有 session 找匹配 model
    for (const entry of sessions.values()) {
      for (const model of entry.models) {
        if (String(model.uri.toString(true)).toLowerCase() === uri) {
          const markers = (params.diagnostics || []).map((d) => ({
            severity: toMonacoSeverity(d.severity),
            message: d.message || "",
            startLineNumber: (d.range?.start?.line ?? 0) + 1,
            startColumn: (d.range?.start?.character ?? 0) + 1,
            endLineNumber: (d.range?.end?.line ?? 0) + 1,
            endColumn: (d.range?.end?.character ?? 0) + 1,
            source: d.source || spec.id,
          }));
          monaco.editor.setModelMarkers(model, `lsp:${spec.id}`, markers);
          return;
        }
      }
    }
  }
}

function toMonacoSeverity(severity) {
  // LSP: 1=Error 2=Warning 3=Information 4=Hint
  switch (severity) {
    case 1:
      return monaco.MarkerSeverity.Error;
    case 2:
      return monaco.MarkerSeverity.Warning;
    case 3:
      return monaco.MarkerSeverity.Info;
    case 4:
      return monaco.MarkerSeverity.Hint;
    default:
      return monaco.MarkerSeverity.Error;
  }
}

/**
 * 按服务器能力注册 hover / completion provider（每个语言只注册一次）。
 * provider 通过 `monaco.languages.registerXxxProvider(语言, ...)` 天然按语言隔离。
 */
function registerLanguageFeatures(spec, capabilities) {
  const language = spec.monacoLanguage;
  if (!language || registeredProviders.has(language)) return;

  const serverCaps = capabilities?.capabilities || {};

  if (serverCaps.hoverProvider) {
    monaco.languages.registerHoverProvider(language, {
      provideHover: async (model, position) => {
        const client = getClientForModel(model, spec);
        if (!client) return null;
        try {
          const result = await client.request("textDocument/hover", {
            textDocument: { uri: model.uri.toString(true) },
            position: {
              line: position.lineNumber - 1,
              character: position.column - 1,
            },
          });
          if (!result) return null;
          const contents = Array.isArray(result.contents)
            ? result.contents
            : [result.contents];
          const value = contents
            .map((c) => (typeof c === "string" ? c : c?.value || ""))
            .join("\n\n");
          if (!value) return null;
          return { contents: [{ value, isTrusted: true }] };
        } catch {
          return null;
        }
      },
    });
  }

  if (serverCaps.completionProvider) {
    monaco.languages.registerCompletionItemProvider(language, {
      triggerCharacters: serverCaps.completionProvider.triggerCharacters || [],
      provideCompletionItems: async (model, position) => {
        const client = getClientForModel(model, spec);
        if (!client) return { suggestions: [] };
        try {
          const result = await client.request("textDocument/completion", {
            textDocument: { uri: model.uri.toString(true) },
            position: {
              line: position.lineNumber - 1,
              character: position.column - 1,
            },
            context: { triggerKind: 1 },
          });
          const items = Array.isArray(result) ? result : result?.items || [];
          return {
            suggestions: items.map((item) => ({
              label: item.label,
              kind: toMonacoCompletionKind(item.kind),
              insertText: item.insertText ?? item.label,
              detail: item.detail || "",
              documentation:
                item.documentation && typeof item.documentation === "object"
                  ? item.documentation.value
                  : item.documentation,
              sortText: item.sortText,
              filterText: item.filterText,
            })),
          };
        } catch {
          return { suggestions: [] };
        }
      },
    });
  }

  registeredProviders.add(language);
}

function getClientForModel(model, spec) {
  const uri = String(model.uri.toString(true)).toLowerCase();
  for (const entry of sessions.values()) {
    if (entry.spec.id !== spec.id) continue;
    for (const m of entry.models) {
      if (String(m.uri.toString(true)).toLowerCase() === uri)
        return entry.client;
    }
  }
  return null;
}

function toMonacoCompletionKind(kind) {
  // LSP CompletionItemKind: 1=Text ... 25=TypeParameter
  const map = {
    1: monaco.languages.CompletionItemKind.Text,
    2: monaco.languages.CompletionItemKind.Method,
    3: monaco.languages.CompletionItemKind.Function,
    4: monaco.languages.CompletionItemKind.Constructor,
    5: monaco.languages.CompletionItemKind.Field,
    6: monaco.languages.CompletionItemKind.Variable,
    7: monaco.languages.CompletionItemKind.Class,
    8: monaco.languages.CompletionItemKind.Interface,
    9: monaco.languages.CompletionItemKind.Module,
    10: monaco.languages.CompletionItemKind.Property,
    11: monaco.languages.CompletionItemKind.Unit,
    12: monaco.languages.CompletionItemKind.Value,
    13: monaco.languages.CompletionItemKind.Enum,
    14: monaco.languages.CompletionItemKind.Keyword,
    15: monaco.languages.CompletionItemKind.Snippet,
    16: monaco.languages.CompletionItemKind.Color,
    17: monaco.languages.CompletionItemKind.File,
    18: monaco.languages.CompletionItemKind.Reference,
    19: monaco.languages.CompletionItemKind.Folder,
    20: monaco.languages.CompletionItemKind.EnumMember,
    21: monaco.languages.CompletionItemKind.Constant,
    22: monaco.languages.CompletionItemKind.Struct,
    23: monaco.languages.CompletionItemKind.Event,
    24: monaco.languages.CompletionItemKind.Operator,
    25: monaco.languages.CompletionItemKind.TypeParameter,
  };
  return map[kind] ?? monaco.languages.CompletionItemKind.Text;
}

/**
 * 确保存在可用的 LSP session，并把指定 model 接入同步。
 *
 * @param {object} params
 * @param {object} params.spec 语言服务器清单
 * @param {string} params.workspaceRoot workspace 根目录
 * @param {object} params.model Monaco ITextModel
 * @param {object} params.deps 依赖注入（getGatewayAddress/getWebSocketProtocol/buildWebSocketProtocols）
 * @returns {Promise<boolean>} 是否成功接入
 */
export async function ensureClient({ spec, workspaceRoot, model, deps }) {
  if (!spec || !spec.id || !model) return false;

  const key = sessionKey(spec.id, workspaceRoot);
  let entry = sessions.get(key);

  if (!entry || entry.socket.readyState !== WebSocket.OPEN) {
    try {
      const client = await connectLspClient({ spec, workspaceRoot, deps });
      entry = {
        client,
        socket: client.socket,
        spec,
        root: workspaceRoot,
        models: new Set(),
        subs: new Map(),
      };
      sessions.set(key, entry);
      client.socket.addEventListener("close", () => {
        if (sessions.get(key) === entry) sessions.delete(key);
        // socket 意外关闭：解除该 session 全部 model 绑定，避免订阅与定时器泄漏
        releaseEntry(entry);
      });
    } catch (error) {
      console.warn(
        `[lsp] 语言服务器 "${spec.id}" 不可用，已降级为仅语法高亮。` +
          (spec.installHint ? ` 安装提示: ${spec.installHint}` : ""),
        error?.message || error,
      );
      return false;
    }
  }

  // 已接入则跳过
  if (entry.models.has(model)) return true;

  // didOpen
  entry.client.notify("textDocument/didOpen", {
    textDocument: {
      uri: model.uri.toString(true),
      languageId: model.getLanguageId(),
      version: model.getVersionId(),
      text: model.getValue(),
    },
  });
  entry.models.add(model);

  // 内容变更 → didChange（防抖）
  const changeSub = model.onDidChangeContent(() => {
    scheduleDidChange(entry.client, model);
  });
  // model 销毁 → didClose 并解除绑定
  const disposeSub = model.onWillDispose(() => {
    entry.client.notify("textDocument/didClose", {
      textDocument: { uri: model.uri.toString(true) },
    });
    unbindModel(entry, model);
  });
  entry.subs.set(model, { changeSub, disposeSub });

  return true;
}

/**
 * 解除单个 model 与 session 的绑定：取消 pending 定时器、释放订阅句柄。
 * 不发送 didClose（由调用方决定是否需要）。
 */
function unbindModel(entry, model) {
  const pending = changeTimers.get(model);
  if (pending) {
    clearTimeout(pending);
    changeTimers.delete(model);
  }
  const handles = entry.subs.get(model);
  if (handles) {
    entry.subs.delete(model);
    try {
      handles.changeSub.dispose();
    } catch {
      /* ignore */
    }
    try {
      handles.disposeSub.dispose();
    } catch {
      /* ignore */
    }
  }
  entry.models.delete(model);
}

/**
 * 释放一个 session entry 的全部资源：取消该 session 所有 model 的订阅与定时器。
 * 幂等，可重复调用。
 */
function releaseEntry(entry) {
  if (!entry) return;
  for (const model of Array.from(entry.models)) {
    unbindModel(entry, model);
  }
  entry.models.clear();
  entry.subs.clear();
}

/** 防抖表：model -> timer */
const changeTimers = new Map();

function scheduleDidChange(client, model) {
  const existing = changeTimers.get(model);
  if (existing) clearTimeout(existing);
  const timer = setTimeout(() => {
    changeTimers.delete(model);
    client.notify("textDocument/didChange", {
      textDocument: {
        uri: model.uri.toString(true),
        version: model.getVersionId(),
      },
      contentChanges: [{ text: model.getValue() }],
    });
  }, 300);
  changeTimers.set(model, timer);
}

/**
 * 释放指定 server 的连接。
 * @param {string} serverId
 * @param {string} root
 */
export function disposeClient(serverId, root) {
  const key = sessionKey(serverId, root);
  const entry = sessions.get(key);
  if (!entry) return;
  sessions.delete(key);
  releaseEntry(entry);
  try {
    entry.client.close();
  } catch {
    /* ignore */
  }
}

/** 释放全部连接（组件卸载时调用）。 */
export function disposeAll() {
  for (const [key, entry] of sessions.entries()) {
    releaseEntry(entry);
    try {
      entry.client.close();
    } catch {
      /* ignore */
    }
    sessions.delete(key);
  }
  registeredProviders.clear();
  for (const timer of changeTimers.values()) clearTimeout(timer);
  changeTimers.clear();
}

/** 当前活跃的连接数，供调试。 */
export function getActiveClientCount() {
  return sessions.size;
}
