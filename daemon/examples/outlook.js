// outlook.js — 通过 Outlook COM 操作桌面版 Outlook（后台服务脚本）
//
// 用法（在 Windows 上，daemon 需支持 run-script）：
//   jarvis-daemon run-script examples/outlook.js --arg action=list
//   jarvis-daemon run-script examples/outlook.js --arg action=list --arg filter=王
//   jarvis-daemon run-script examples/outlook.js --arg action=read --arg id=<entryid>
//   jarvis-daemon run-script examples/outlook.js --arg action=search --arg query=发票
//   jarvis-daemon run-script examples/outlook.js --arg action=send \
//       --arg to=a@b.com --arg subject=标题 --arg body=正文
//
// 说明：
//   - 通过 jarvis.cap("windows.script.exec", ...) 执行 PowerShell COM 操作 Outlook。
//   - 动作：list 列收件箱邮件（可按 filter 过滤发件人/主题）；read 读指定邮件正文；
//     search 搜索邮件；send 发送邮件。
//   - 不硬编码任何凭据；发送邮件依赖 Outlook 已配置的账户。
//
// 注意：脚本以 daemon 权限运行，等同 shell 权限。send 为写操作，请确认意图后再用。

// ---------------------------------------------------------------------------
// PowerShell 公共片段：启动 Outlook COM，返回 Mail 对象
// ---------------------------------------------------------------------------
// 用 PowerShell 单行方式调用，避免转义地狱：把 PowerShell 代码作为脚本体传入
// windows.script.exec，由 daemon 侧执行 powershell -Command。

function psExec(powershellCode) {
  const res = jarvis.cap("windows.script.exec", {
    script: powershellCode,
    interpreter: "powershell",
    timeout_ms: 60000,
  });
  if (!res.success) {
    console.error("执行 PowerShell 失败:", res.error);
    throw new Error("PowerShell 执行失败: " + res.error);
  }
  return res.data;
}

// 从 PowerShell 输出中提取 JSON（脚本末尾用 ConvertTo-Json -Compress 输出）
function extractJson(raw) {
  if (!raw || !raw.stdout) return null;
  const s = raw.stdout.trim();
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start < 0 || end < 0 || end <= start) return null;
  const json = s.slice(start, end + 1);
  try {
    return JSON.parse(json);
  } catch (e) {
    console.error("解析 JSON 失败:", e.message);
    return null;
  }
}

// ---------------------------------------------------------------------------
// 动作一：list —— 列收件箱邮件（支持 filter 过滤发件人/主题）
// ---------------------------------------------------------------------------
function listMails(filter) {
  const ps = `
$ErrorActionPreference = 'Stop'
try {
  $ol = New-Object -ComObject Outlook.Application
  $ns = $ol.GetNamespace('MAPI')
  $inbox = $ns.GetDefaultFolder(6)  # 6 = olFolderInbox
  $items = $inbox.Items
  $result = @()
  foreach ($m in $items) {
    if ($m.Class -ne 43) { continue }  # 43 = olMail
    $sender = ''
    try { $sender = $m.SenderName } catch {}
    $subject = ''
    try { $subject = $m.Subject } catch {}
    $filter = '${filter}'
    if ($filter -ne '' -and $subject -notlike "*$filter*" -and $sender -notlike "*$filter*") { continue }
    $result += [PSCustomObject]@{
      id      = $m.EntryID
      sender  = $sender
      subject = $subject
      time    = $m.ReceivedTime.ToString('yyyy-MM-dd HH:mm')
      unread  = $m.UnRead
    }
  }
  $result | ConvertTo-Json -Compress -Depth 3
} catch {
  Write-Output ('ERROR: ' + $_.Exception.Message)
  exit 1
}
`;
  const data = psExec(ps);
  const json = extractJson(data);
  if (!json) {
    // 可能输出 ERROR 或空
    const raw = data && data.stdout ? data.stdout.trim() : "";
    if (raw.indexOf("ERROR:") === 0) {
      throw new Error("Outlook 列表失败: " + raw);
    }
    return [];
  }
  // ConvertTo-Json 单条时是对象，多条时是数组
  return Array.isArray(json) ? json : [json];
}

// ---------------------------------------------------------------------------
// 动作二：read —— 读指定邮件正文
// ---------------------------------------------------------------------------
function readMail(entryId) {
  const ps = `
$ErrorActionPreference = 'Stop'
try {
  $ol = New-Object -ComObject Outlook.Application
  $ns = $ol.GetNamespace('MAPI')
  $mail = $ns.GetItemFromID('${entryId}')
  $body = ''
  try { $body = $mail.Body } catch {}
  [PSCustomObject]@{
    id      = $mail.EntryID
    sender  = $mail.SenderName
    subject = $mail.Subject
    time    = $mail.ReceivedTime.ToString('yyyy-MM-dd HH:mm')
    body    = $body
  } | ConvertTo-Json -Compress -Depth 3
} catch {
  Write-Output ('ERROR: ' + $_.Exception.Message)
  exit 1
}
`;
  const data = psExec(ps);
  const json = extractJson(data);
  if (!json) {
    const raw = data && data.stdout ? data.stdout.trim() : "";
    if (raw.indexOf("ERROR:") === 0)
      throw new Error("Outlook 读取失败: " + raw);
    throw new Error("Outlook 读取失败: 无法解析结果");
  }
  return json;
}

// ---------------------------------------------------------------------------
// 动作三：search —— 搜索邮件（按主题/正文关键词）
// ---------------------------------------------------------------------------
function searchMails(query) {
  const ps = `
$ErrorActionPreference = 'Stop'
try {
  $ol = New-Object -ComObject Outlook.Application
  $ns = $ol.GetNamespace('MAPI')
  $inbox = $ns.GetDefaultFolder(6)
  $items = $inbox.Items
  $result = @()
  $q = '${query}'
  foreach ($m in $items) {
    if ($m.Class -ne 43) { continue }
    $subject = ''
    $body = ''
    try { $subject = $m.Subject } catch {}
    try { $body = $m.Body } catch {}
    if ($subject -like "*$q*" -or $body -like "*$q*") {
      $result += [PSCustomObject]@{
        id      = $m.EntryID
        sender  = $m.SenderName
        subject = $subject
        time    = $m.ReceivedTime.ToString('yyyy-MM-dd HH:mm')
      }
    }
  }
  $result | ConvertTo-Json -Compress -Depth 3
} catch {
  Write-Output ('ERROR: ' + $_.Exception.Message)
  exit 1
}
`;
  const data = psExec(ps);
  const json = extractJson(data);
  if (!json) {
    const raw = data && data.stdout ? data.stdout.trim() : "";
    if (raw.indexOf("ERROR:") === 0)
      throw new Error("Outlook 搜索失败: " + raw);
    return [];
  }
  return Array.isArray(json) ? json : [json];
}

// ---------------------------------------------------------------------------
// 动作四：send —— 发送邮件
// ---------------------------------------------------------------------------
function sendMail(to, cc, subject, body) {
  const ps = `
$ErrorActionPreference = 'Stop'
try {
  $ol = New-Object -ComObject Outlook.Application
  $mail = $ol.CreateItem(0)  # 0 = olMailItem
  $mail.To = '${to}'
  if ('${cc}' -ne '') { $mail.CC = '${cc}' }
  $mail.Subject = '${subject}'
  $mail.Body = '${body}'
  $mail.Send()
  Write-Output ('SENT: ' + $mail.Subject)
} catch {
  Write-Output ('ERROR: ' + $_.Exception.Message)
  exit 1
}
`;
  const data = psExec(ps);
  const raw = data && data.stdout ? data.stdout.trim() : "";
  if (raw.indexOf("SENT:") === 0) {
    return { ok: true, subject: raw.slice(6) };
  }
  if (raw.indexOf("ERROR:") === 0) {
    throw new Error("Outlook 发送失败: " + raw);
  }
  throw new Error("Outlook 发送失败: 未知结果");
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
const action = jarvis.args.action || "list";
let result;

if (action === "list") {
  const filter = jarvis.args.filter || "";
  const mails = listMails(filter);
  print("收件箱邮件数:", mails.length);
  for (const m of mails) {
    print(
      (m.unread ? "[未读] " : "      ") +
        m.time +
        "  " +
        m.sender +
        "  " +
        m.subject,
    );
  }
  result = { action: "list", count: mails.length, mails: mails };
} else if (action === "read") {
  const id = jarvis.args.id;
  if (!id) throw new Error("read 需要 --arg id=<entryid>");
  const mail = readMail(id);
  print("发件人:", mail.sender);
  print("主题:", mail.subject);
  print("时间:", mail.time);
  print("----------------------------------------");
  print(mail.body);
  result = { action: "read", mail: mail };
} else if (action === "search") {
  const query = jarvis.args.query || "";
  if (!query) throw new Error("search 需要 --arg query=<关键词>");
  const mails = searchMails(query);
  print("搜索到邮件数:", mails.length);
  for (const m of mails) {
    print(m.time + "  " + m.sender + "  " + m.subject);
  }
  result = {
    action: "search",
    query: query,
    count: mails.length,
    mails: mails,
  };
} else if (action === "send") {
  const to = jarvis.args.to;
  if (!to) throw new Error("send 需要 --arg to=<收件人>");
  const subject = jarvis.args.subject || "";
  const body = jarvis.args.body || "";
  const cc = jarvis.args.cc || "";
  result = sendMail(to, cc, subject, body);
  print("已发送:", result.subject);
} else {
  throw new Error("未知 action: " + action + "（支持 list/read/search/send）");
}

result;
