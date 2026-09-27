package webui

// indexHTML 是内嵌的登录页。
//
// 刻意内联为字符串而非外部文件：守护进程是单文件分发的二进制，若依赖外部
// 资源文件，部署时容易缺失。页面为纯 HTML/CSS/JS，无任何外部依赖。
//
// 交互：表单提交 → fetch POST /api/login → 成功显示提示并禁用表单（用户可
// 直接关闭页面）；失败在页面内显示错误信息。
//
// 网关地址会存入浏览器 localStorage（key: jarvis_gateway），下次打开自动回填，
// 免去重复输入。**只存网关地址，绝不存储用户名与密码**。
const indexHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jarvis 守护进程登录</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    background: #f5f6f8; color: #1f2329; padding: 16px;
  }
  .card {
    width: 100%; max-width: 380px; background: #fff; border-radius: 12px;
    box-shadow: 0 8px 30px rgba(0,0,0,.08); padding: 28px 24px;
  }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { font-size: 13px; color: #6b7280; margin: 0 0 20px; }
  label { display: block; font-size: 13px; margin: 12px 0 6px; color: #374151; }
  input {
    width: 100%; padding: 10px 12px; font-size: 14px;
    border: 1px solid #d1d5db; border-radius: 8px; outline: none;
  }
  input:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,.15); }
  button {
    width: 100%; margin-top: 20px; padding: 11px; font-size: 15px;
    color: #fff; background: #2563eb; border: 0; border-radius: 8px;
    cursor: pointer;
  }
  button:hover { background: #1d4ed8; }
  button:disabled { background: #9ca3af; cursor: not-allowed; }
  .msg { margin-top: 16px; font-size: 14px; display: none; padding: 10px 12px; border-radius: 8px; }
  .msg.err { display: block; background: #fef2f2; color: #b91c1c; }
  .msg.ok  { display: block; background: #ecfdf5; color: #047857; }
  .hint { margin-top: 18px; font-size: 12px; color: #9ca3af; line-height: 1.6; }
</style>
</head>
<body>
  <div class="card">
    <h1>Jarvis 守护进程登录</h1>
    <p class="sub">登录后本机将连接到网关</p>
    <form id="f" autocomplete="off">
      <label for="gateway">网关地址</label>
      <input id="gateway" name="gateway" placeholder="http://example.com:8000" required>

      <label for="username">用户名</label>
      <input id="username" name="username" required>

      <label for="password">密码</label>
      <input id="password" name="password" type="password" required>

      <button id="submit" type="submit">登录</button>
    </form>
    <div id="msg" class="msg"></div>
    <p class="hint">凭据仅用于连接网关，不落盘保存。</p>
  </div>

<script>
(function () {
  var form = document.getElementById('f');
  var msg = document.getElementById('msg');
  var btn = document.getElementById('submit');
  var gatewayEl = document.getElementById('gateway');
  var STORAGE_KEY = 'jarvis_gateway';

  // 回填上次使用的网关地址（只存地址，不存用户名/密码）。
  try {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved) { gatewayEl.value = saved; }
  } catch (e) { /* 隐私模式等场景下 localStorage 不可用，忽略 */ }

  function show(text, ok) {
    msg.textContent = text;
    msg.className = 'msg ' + (ok ? 'ok' : 'err');
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    btn.disabled = true;
    msg.className = 'msg';
    msg.textContent = '';

    var payload = {
      gateway: gatewayEl.value.trim(),
      username: document.getElementById('username').value.trim(),
      password: document.getElementById('password').value
    };

    // 记住网关地址，方便下次登录。
    try { localStorage.setItem(STORAGE_KEY, payload.gateway); } catch (e) { /* 忽略 */ }

    fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (data) {
        return { ok: resp.ok, data: data };
      });
    }).then(function (r) {
      if (r.ok && r.data && r.data.success) {
        show(r.data.message || '登录成功，本页面可以关闭了', true);
        // 成功后禁用表单，避免重复提交；用户可直接关闭页面。
        form.querySelectorAll('input,button').forEach(function (el) { el.disabled = true; });
      } else {
        show((r.data && r.data.error) || '登录失败，请重试', false);
        btn.disabled = false;
      }
    }).catch(function (err) {
      show('请求失败：' + err, false);
      btn.disabled = false;
    });
  });
})();
</script>
</body>
</html>
`
