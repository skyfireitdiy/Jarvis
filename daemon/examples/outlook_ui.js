// outlook_ui.js — 通过 UI 操作（截图 + OCR）读取新式 Outlook 邮件（后台服务脚本）
//
// 适用：SF-PC 等使用「新式 Outlook（olk.exe）」的机器，经典 MAPI COM 读不到邮件，
//       只能用 UI 方式（截图 + OCR）获取内容。
//
// 用法（在 Windows 上，daemon 需支持 run-script）：
//   jarvis-daemon run-script examples/outlook_ui.js --arg action=list
//   jarvis-daemon run-script examples/outlook_ui.js --arg action=read --arg subject=Anna
//   jarvis-daemon run-script examples/outlook_ui.js --arg action=read --arg index=0
//
// 说明：
//   - 通过 jarvis.cap("windows.script.exec", ...) 截图 Outlook 窗口区域，
//     再 jarvis.cap("ocr.recognize", ...) 识别文字。
//   - 动作：list 读收件箱邮件列表；read 点击指定邮件读正文（按 subject 子串或列表 index）。
//   - 依赖网关 OCR（ocr.recognize）。run-script 独立进程需设置环境变量
//     JARVIS_GATEWAY + JARVIS_AUTH_TOKEN 注入凭据；否则 OCR 会返回明确错误。
//   - 不硬编码任何凭据。
//
// 注意：脚本以 daemon 权限运行，等同 shell 权限。仅做读取，不含写操作。

// ---------------------------------------------------------------------------
// 工具：截图窗口区域（用 Add-Type 定义完整 C# 类，避免 struct New-Object 问题）
// ---------------------------------------------------------------------------
function captureWindowRegion(windowId, outPath) {
  const hex = String(windowId).replace("0x", "");
  const ps = `
Add-Type -AssemblyName System.Drawing
$src = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public class CapShot {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  public static string Shot(IntPtr h, string path) {
    RECT r; GetWindowRect(h, out r);
    int w = r.Right - r.Left, ht = r.Bottom - r.Top;
    using (Bitmap bmp = new Bitmap(w, ht)) {
      using (Graphics g = Graphics.FromImage(bmp)) { g.CopyFromScreen(r.Left, r.Top, 0, 0, bmp.Size); }
      bmp.Save(path, ImageFormat.Png);
    }
    return r.Left + "," + r.Top + "," + w + "," + ht;
  }
}
'@
Add-Type -TypeDefinition $src -ReferencedAssemblies System.Drawing
[CapShot]::Shot([IntPtr]0x${hex}, '${outPath}')
`;
  const res = jarvis.cap("windows.script.exec", {
    script: ps,
    interpreter: "powershell",
    timeout_ms: 20000,
  });
  if (!res.success) throw new Error("截图失败: " + res.error);
  return res.data && res.data.stdout ? res.data.stdout.trim() : "";
}

// ---------------------------------------------------------------------------
// 工具：OCR 识别（返回 { text, lines }）
// ---------------------------------------------------------------------------
function ocrImage(path, withDetail) {
  const params = {
    image: path,
    lang: "chi_sim+eng",
    gateway: "https://jvs-ai.cn:4443",
  };
  if (withDetail) params.detail = true;
  const res = jarvis.cap("ocr.recognize", params);
  if (!res.success) throw new Error("OCR 失败: " + res.error);
  const d = res.data || {};
  return { text: d.text || "", lines: d.lines || [] };
}

// ---------------------------------------------------------------------------
// 动作一：list —— 读收件箱邮件列表（OCR 文本）
// ---------------------------------------------------------------------------
function listMails(win) {
  captureWindowRegion(
    win.window_id,
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
  );
  jarvis.sleep(600);
  const { text } = ocrImage(
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
    false,
  );
  return text;
}

// ---------------------------------------------------------------------------
// 动作二：read —— 点击指定邮件读正文
//   subject: 按主题子串匹配邮件行；index: 按列表行序号（0 起）匹配
// ---------------------------------------------------------------------------
function readMail(win, subject, index) {
  // 截图 + OCR detail 拿邮件行坐标
  captureWindowRegion(
    win.window_id,
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
  );
  jarvis.sleep(600);
  const { text, lines } = ocrImage(
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
    true,
  );

  // 窗口原点（截图返回 "left,top,w,h"）
  const rectStr = captureWindowRegion(
    win.window_id,
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
  );
  const parts = rectStr.split(",");
  const ox = parseInt(parts[0], 10);
  const oy = parseInt(parts[1], 10);

  // 邮件列表在窗口左侧（x 约 98~340 区域）。筛选左侧区域的 OCR 行作为候选邮件行。
  // 用 OCR detail 的行坐标，取每行的中心点；匹配 subject 或按 index 选行。
  const leftLines = lines.filter(
    (l) => l.bbox && l.bbox.x < 360 && l.bbox.y > 60,
  );
  // 按 y 分组，相近 y 视为同一行
  leftLines.sort((a, b) => a.bbox.y - b.bbox.y);
  const rows = [];
  for (const l of leftLines) {
    const cy = l.bbox.y + l.bbox.height / 2;
    if (rows.length === 0 || Math.abs(rows[rows.length - 1].y - cy) > 18) {
      rows.push({ y: cy, x: l.bbox.x + l.bbox.width / 2, text: l.text });
    } else {
      rows[rows.length - 1].text += " " + l.text;
    }
  }

  // 选目标行
  let target = null;
  if (subject) {
    for (const r of rows) {
      if (r.text.indexOf(subject) >= 0) {
        target = r;
        break;
      }
    }
    if (!target) throw new Error("未找到主题含 '" + subject + "' 的邮件行");
  } else {
    const idx = index !== undefined ? index : 0;
    if (idx < 0 || idx >= rows.length)
      throw new Error("index 越界: " + idx + "（共 " + rows.length + " 行）");
    target = rows[idx];
  }

  // 点击该行（屏幕坐标 = 窗口坐标 + 窗口原点）
  const sx = Math.round(ox + target.x);
  const sy = Math.round(oy + target.y);
  const clickRes = jarvis.cap("windows.input.click", { x: sx, y: sy });
  if (!clickRes.success) throw new Error("点击失败: " + clickRes.error);

  // 等待正文加载后截图 + OCR
  jarvis.sleep(1500);
  captureWindowRegion(
    win.window_id,
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
  );
  jarvis.sleep(600);
  const body = ocrImage(
    "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png",
    false,
  );
  return { clicked: target.text, body: body.text };
}

// ---------------------------------------------------------------------------
// 工具：定位 Outlook 收件箱窗口
// ---------------------------------------------------------------------------
function findOutlookWindow() {
  const res = jarvis.cap("windows.window.list", {});
  if (!res.success) throw new Error("window.list 失败: " + res.error);
  let wins = [];
  if (Array.isArray(res.data)) wins = res.data;
  else if (res.data && Array.isArray(res.data.windows)) wins = res.data.windows;
  else if (res.data && Array.isArray(res.data.result)) wins = res.data.result;
  for (const w of wins) {
    const title = w.title || w.Title || w.name || "";
    if (title.indexOf("Outlook") >= 0 && title.indexOf("收件箱") >= 0) {
      return {
        window_id: w.window_id || w.WindowID,
        title: title,
        pid: w.pid || w.PID,
      };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
const action = jarvis.args.action || "list";
let result;

const win = findOutlookWindow();
if (!win) {
  throw new Error("未找到 Outlook 收件箱窗口（请先打开新式 Outlook）");
}
print("找到 Outlook 窗口:", win.window_id, win.title);

if (action === "list") {
  const text = listMails(win);
  print("===== 收件箱邮件列表（OCR） =====");
  print(text);
  print("===== 结束 =====");
  result = { action: "list", window: win.window_id, ocrText: text };
} else if (action === "read") {
  const subject = jarvis.args.subject || "";
  const indexRaw = jarvis.args.index;
  const index = indexRaw !== undefined ? parseInt(indexRaw, 10) : undefined;
  if (!subject && (index === undefined || isNaN(index))) {
    throw new Error("read 需要 --arg subject=<主题子串> 或 --arg index=<行号>");
  }
  const out = readMail(win, subject, index);
  print("===== 已点击邮件 =====");
  print(out.clicked);
  print("===== 正文（OCR） =====");
  print(out.body);
  print("===== 结束 =====");
  result = {
    action: "read",
    window: win.window_id,
    clicked: out.clicked,
    body: out.body,
  };
} else {
  throw new Error("未知 action: " + action + "（支持 list/read）");
}

result;
