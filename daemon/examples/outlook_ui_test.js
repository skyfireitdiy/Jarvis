// outlook_ui_test.js — 验证 UI 模式链路（截图 + OCR 读新式 Outlook 邮件列表）
// 用法: jarvis-daemon run-script outlook_ui_test.js

// 1. 找到 Outlook 窗口（olk.exe 的新式 Outlook）
function findOutlookWindow() {
  const res = jarvis.cap("windows.window.list", {});
  if (!res.success) throw new Error("window.list 失败: " + res.error);
  print(
    "window.list res.data 类型:",
    typeof res.data,
    JSON.stringify(res.data).slice(0, 300),
  );
  // 兼容两种结构：res.data 直接是数组，或 res.data.windows 是数组
  let wins = [];
  if (Array.isArray(res.data)) wins = res.data;
  else if (res.data && Array.isArray(res.data.windows)) wins = res.data.windows;
  else if (res.data && Array.isArray(res.data.result)) wins = res.data.result;
  for (const w of wins) {
    const title = w.title || w.Title || w.name || "";
    if (title.indexOf("Outlook") >= 0 && title.indexOf("收件箱") >= 0) {
      // 统一返回小写字段
      return {
        window_id: w.window_id || w.WindowID,
        title: title,
        pid: w.pid || w.PID,
      };
    }
  }
  return null;
}

// 2. 最小化可能遮挡的窗口，聚焦 Outlook
function ensureOutlookVisible(win) {
  // 用 PowerShell 把 Outlook 窗口置顶 + 最小化其它可见窗口
  const ps = `
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class UIV{ [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int c); [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);}'
$h = [IntPtr]0x${win.window_id.replace("0x", "")}
[UIV]::ShowWindow($h, 9) | Out-Null   # SW_RESTORE
[UIV]::BringWindowToTop($h) | Out-Null
[UIV]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
Write-Output 'OK'
`;
  const res = jarvis.cap("windows.script.exec", {
    script: ps,
    interpreter: "powershell",
    timeout_ms: 15000,
  });
  if (!res.success) throw new Error("聚焦 Outlook 失败: " + res.error);
  return true;
}

// 3. 截取 Outlook 窗口区域
function captureOutlookRegion(win) {
  const ps = `
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class UIV2{ [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r); public struct RECT{public int Left,Top,Right,Bottom;} }'
$r = New-Object UIV2+RECT
[UIV2]::GetWindowRect([IntPtr]0x${win.window_id.replace("0x", "")}, [ref]$r) | Out-Null
$x = $r.Left; $y = $r.Top; $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
$bmp.Save('C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output ('OK ' + $x + ' ' + $y + ' ' + $w + ' ' + $h)
`;
  const res = jarvis.cap("windows.script.exec", {
    script: ps,
    interpreter: "powershell",
    timeout_ms: 20000,
  });
  if (!res.success) throw new Error("截图失败: " + res.error);
  return "C:\\Users\\skyfire\\.jarvis\\scripts\\olk_cap.png";
}

// 4. OCR 识别
function ocrImage(path) {
  const res = jarvis.cap("ocr.recognize", {
    image: path,
    lang: "chi_sim+eng",
    gateway: "https://jvs-ai.cn:4443",
  });
  if (!res.success) throw new Error("OCR 失败: " + res.error);
  return res.data && res.data.text ? res.data.text : "";
}

// 主流程
let result;
const win = findOutlookWindow();
if (!win) {
  throw new Error("未找到 Outlook 收件箱窗口");
}
print("找到 Outlook 窗口:", win.window_id, win.title);
ensureOutlookVisible(win);
jarvis.sleep(1000);
const shot = captureOutlookRegion(win);
print("已截图:", shot);
const text = ocrImage(shot);
print("===== OCR 识别结果 =====");
print(text);
print("===== 结束 =====");
result = { ok: true, window: win.window_id, ocrText: text };
result;
