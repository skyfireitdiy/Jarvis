// LSP 语言服务器注册表（src/lsp/registry.js）的单元测试（node:test + node:assert/strict）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/lsp/registry.test.mjs
//
// 说明：registry.js 有模块级可变状态（serverByLanguage/serverByExtension/loaded/
// loadPromise），且 loadLspServers 有缓存。node:test 每个文件独立进程，但同一模块
// 实例的状态会跨用例保留。为获得干净状态，这里用「动态 import + URL 查询串」让
// Node 把 `registry.js?case=N` 视为不同模块实例（ESM 支持查询串区分模块），
// 每个用例拿到独立实例，互不污染。fetchWithAuth 等依赖通过参数注入 mock。
import { test } from "node:test";
import assert from "node:assert/strict";

// 动态 import 一个独立模块实例（用 case 查询串区分）
async function loadRegistry(caseNo) {
  return await import(`./registry.js?case=${caseNo}`);
}

// 构造默认 deps：fetchWithAuth 返回 ok + 空 servers
function makeDeps(overrides = {}) {
  const fetchWithAuth =
    overrides.fetchWithAuth ||
    (async () => ({
      ok: true,
      status: 200,
      json: async () => ({ servers: [] }),
    }));
  return {
    fetchWithAuth,
    getGatewayAddress:
      overrides.getGatewayAddress ||
      (() => ({ host: "localhost", port: "8080" })),
    getHttpProtocol: overrides.getHttpProtocol || (() => "http"),
  };
}

test("初始状态：未加载，查询返回 null", async () => {
  const reg = await loadRegistry(1);
  assert.equal(reg.isLspRegistryLoaded(), false);
  assert.equal(reg.getServerByLanguage("python"), null);
  assert.equal(reg.getServerByPath("a.py"), null);
});

test("loadLspServers 成功：按 monacoLanguage 与 extensions 建立索引", async () => {
  const reg = await loadRegistry(2);
  const servers = [
    { id: "python", monacoLanguage: "python", extensions: [".py", ".PYI"] },
    { id: "js", monacoLanguage: "javascript", extensions: [".js"] },
  ];
  const deps = makeDeps({
    fetchWithAuth: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ servers }),
    }),
  });
  const result = await reg.loadLspServers(deps);
  assert.ok(result instanceof Map);
  // 按语言索引
  assert.equal(reg.getServerByLanguage("python").id, "python");
  assert.equal(reg.getServerByLanguage("javascript").id, "js");
  // 按扩展名索引（含点、小写归一）
  assert.equal(reg.getServerByPath("main.PY").id, "python");
  assert.equal(reg.getServerByPath("app.js").id, "js");
  assert.equal(reg.isLspRegistryLoaded(), true);
});

test("同 monacoLanguage 只保留首个", async () => {
  const reg = await loadRegistry(3);
  const servers = [
    { id: "py1", monacoLanguage: "python", extensions: [".py"] },
    { id: "py2", monacoLanguage: "python", extensions: [".py"] },
  ];
  const deps = makeDeps({
    fetchWithAuth: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ servers }),
    }),
  });
  await reg.loadLspServers(deps);
  assert.equal(reg.getServerByLanguage("python").id, "py1");
});

test("缓存：第二次调用（force=false）不重复 fetch", async () => {
  const reg = await loadRegistry(4);
  let callCount = 0;
  const deps = makeDeps({
    fetchWithAuth: async () => {
      callCount++;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          servers: [
            { id: "py", monacoLanguage: "python", extensions: [".py"] },
          ],
        }),
      };
    },
  });
  await reg.loadLspServers(deps);
  await reg.loadLspServers(deps);
  assert.equal(callCount, 1);
});

test("force=true 时重新拉取", async () => {
  const reg = await loadRegistry(5);
  let callCount = 0;
  const deps = makeDeps({
    fetchWithAuth: async () => {
      callCount++;
      return { ok: true, status: 200, json: async () => ({ servers: [] }) };
    },
  });
  await reg.loadLspServers(deps);
  await reg.loadLspServers(deps, true);
  assert.equal(callCount, 2);
});

test("response.ok=false 时返回空 Map 且不抛", async () => {
  const reg = await loadRegistry(6);
  const deps = makeDeps({
    fetchWithAuth: async () => ({ ok: false, status: 500 }),
  });
  const result = await reg.loadLspServers(deps);
  assert.ok(result instanceof Map);
  assert.equal(result.size, 0);
  assert.equal(reg.isLspRegistryLoaded(), false);
});

test("fetchWithAuth 抛错时被捕获、不抛、返回 Map", async () => {
  const reg = await loadRegistry(7);
  const deps = makeDeps({
    fetchWithAuth: async () => {
      throw new Error("network down");
    },
  });
  const result = await reg.loadLspServers(deps);
  assert.ok(result instanceof Map);
  assert.equal(reg.isLspRegistryLoaded(), false);
});

test("servers 非数组时视为空，不抛错", async () => {
  const reg = await loadRegistry(8);
  const deps = makeDeps({
    fetchWithAuth: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ servers: "oops" }),
    }),
  });
  const result = await reg.loadLspServers(deps);
  assert.ok(result instanceof Map);
  assert.equal(result.size, 0);
});

test("缺 id 或缺 monacoLanguage 的条目被跳过；extensions 缺失不报错", async () => {
  const reg = await loadRegistry(9);
  const servers = [
    { id: "ok", monacoLanguage: "python", extensions: [".py"] },
    { id: "no-lang", extensions: [".x"] }, // 缺 monacoLanguage → 跳过
    { monacoLanguage: "no-id", extensions: [".y"] }, // 缺 id → 跳过
    { id: "no-ext", monacoLanguage: "plaintext" }, // 缺 extensions → 不报错
  ];
  const deps = makeDeps({
    fetchWithAuth: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ servers }),
    }),
  });
  await reg.loadLspServers(deps);
  assert.equal(reg.getServerByLanguage("python").id, "ok");
  assert.equal(reg.getServerByLanguage("no-lang"), null);
  assert.equal(reg.getServerByLanguage("no-id"), null);
  // 无 extensions 的语言可被语言 id 查到
  assert.equal(reg.getServerByLanguage("plaintext").id, "no-ext");
});

test("getServerByLanguage：空/未命中返回 null，命中返回 spec", async () => {
  const reg = await loadRegistry(10);
  const deps = makeDeps({
    fetchWithAuth: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        servers: [{ id: "py", monacoLanguage: "python", extensions: [".py"] }],
      }),
    }),
  });
  await reg.loadLspServers(deps);
  assert.equal(reg.getServerByLanguage(""), null);
  assert.equal(reg.getServerByLanguage(undefined), null);
  assert.equal(reg.getServerByLanguage("golang"), null);
  assert.equal(reg.getServerByLanguage("python").id, "py");
});

test("getServerByPath：空/无扩展名/未注册返回 null，大小写不敏感命中", async () => {
  const reg = await loadRegistry(11);
  const deps = makeDeps({
    fetchWithAuth: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        servers: [{ id: "py", monacoLanguage: "python", extensions: [".py"] }],
      }),
    }),
  });
  await reg.loadLspServers(deps);
  assert.equal(reg.getServerByPath(""), null);
  assert.equal(reg.getServerByPath(undefined), null);
  assert.equal(reg.getServerByPath("noext"), null); // 无扩展名
  assert.equal(reg.getServerByPath("a.PY").id, "py"); // 大小写不敏感命中
  assert.equal(reg.getServerByPath("/deep/dir/main.py").id, "py"); // 多级目录取最后扩展名
  assert.equal(reg.getServerByPath("main.go"), null); // 未注册扩展名
});
