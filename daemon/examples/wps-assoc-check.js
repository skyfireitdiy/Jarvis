// wps-assoc-check.js — WPS 文件关联巡检脚本
//
// 用法：
//   jarvis-daemon run-script wps-assoc-check.js
//   jarvis-daemon run-script wps-assoc-check.js --arg wps_root="D:\\WPS Office"
//   jarvis-daemon run-script wps-assoc-check.js --arg fix=1
//
// 背景：
//   WPS 升级后会保留旧版本目录名，但注册表里的 ProgID open 命令与
//   App Paths 可能仍指向已被删除的旧版本目录，导致双击 .xls/.docx 等
//   文件时弹「打开方式」或直接打不开。
//
// 本脚本检查三处关键注册表位置是否指向「真实存在的」可执行文件：
//   1. HKCR\<ProgID>\shell\open\command   （文件类型打开命令）
//   2. HKCU/HKLM\...\App Paths\*.exe      （应用路径登记）
//   3. HKCR\.<ext> 的默认 ProgID           （扩展名 → ProgID 映射）
//   4. HKCU\...\FileExts\.<ext>\UserChoice（用户选择，优先级最高）
//
// 默认只检查并报告，不修改任何东西。
// 传 --arg fix=1 时，会把失效路径自动修正为当前实际存在的版本目录。
//
// 实现说明：
//   注册表读取统一走 PowerShell 的 Registry API（而非 reg.exe），
//   因为 reg.exe 输出为系统 ANSI 代码页（中文系统为 GBK），
//   经 daemon 按 UTF-8 返回会乱码，且「(默认)」值名被本地化。

const wpsRoot = jarvis.args.wps_root || "D:\\WPS Office";
const doFix = String(jarvis.args.fix || "") === "1";

// 需要巡检的扩展名 → 期望的 ProgID 前缀（可多个候选，任一匹配即算 OK）
// 说明：WPS 不同版本/安装方式会注册不同的 ProgID 命名体系，
//   新版为 ET.* / WPS.* / WPP.*，旧版为 KWPS.* / KWPP.*，两者都要认。
const EXTENSIONS = {
  ".xls": ["ET.Xls"],
  ".xlsx": ["ET.Xlsx"],
  ".doc": ["WPS.Doc", "KWPS.Document"],
  ".docx": ["WPS.Docx", "KWPS.Document"],
  ".ppt": ["WPP.PPT", "KWPP.Presentation"],
  ".pptx": ["WPP.PPTX", "KWPP.Presentation"],
};

// 需要巡检的 ProgID（open 命令里应指向真实存在的 exe）
const PROGIDS = [
  "ET.Xls.6",
  "ET.Xlsx.6",
  "WPS.Doc.6",
  "WPS.Docx.6",
  "WPP.PPT.6",
  "WPP.PPTX.6",
  "KWPS.Document.12",
  "KWPS.Document.9",
  "KWPP.Presentation.12",
  "KWPP.Presentation.9",
];

const issues = [];
const notes = [];

function log(msg) {
  print(msg);
}

function warn(msg) {
  issues.push(msg);
  print("[问题] " + msg);
}

// ---------- 1. 探测本机实际存在的 WPS 版本目录与可执行文件 ----------

function probeWpsInstall() {
  const res = jarvis.cap("windows.fs.list", { path: wpsRoot, max_depth: 1 });
  if (!res.success) {
    warn("无法列出 WPS 安装根目录 " + wpsRoot + "：" + res.error);
    return { versions: [], exes: { et: [], wps: [], wpp: [] } };
  }

  const versions = [];
  for (const entry of res.data.entries) {
    if (entry.is_dir) versions.push(entry.name);
  }
  log("发现 WPS 版本目录 " + versions.length + " 个：" + versions.join(", "));

  // 在每个版本目录下探测 office6\et.exe / wps.exe / wpp.exe
  const exes = { et: [], wps: [], wpp: [] };
  for (const v of versions) {
    for (const name of ["et", "wps", "wpp"]) {
      const p = wpsRoot + "\\" + v + "\\office6\\" + name + ".exe";
      const chk = jarvis.cap("windows.fs.read", { path: p, limit: 1 });
      if (chk.success) exes[name].push(p);
    }
  }

  for (const name of ["et", "wps", "wpp"]) {
    if (exes[name].length === 0) {
      warn("未找到任何 " + name + ".exe（在 " + wpsRoot + " 各版本 office6 下）");
    } else {
      log("  " + name + ".exe 可用路径：" + exes[name].join(" | "));
    }
  }

  return { versions: versions, exes: exes };
}

// ---------- 2. 注册表读取（PowerShell Registry API，避免编码/本地化问题） ----------

// 批量读取多个注册表值，返回 { key: value|null }
// spec: [{ id, hive, path, name }]，name 为空表示默认值
function regReadBatch(spec) {
  const json = JSON.stringify(spec);
  // 通过 stdin 传 JSON，避免引号转义地狱
  const ps = [
    "$ErrorActionPreference='SilentlyContinue'",
    "$raw = [Console]::In.ReadToEnd()",
    "$spec = $raw | ConvertFrom-Json",
    "$out = @{}",
    "foreach ($s in $spec) {",
    "  $hive = switch ($s.hive) {",
    "    'HKCU' { 'HKEY_CURRENT_USER' }",
    "    'HKLM' { 'HKEY_LOCAL_MACHINE' }",
    "    'HKCR' { 'HKEY_CLASSES_ROOT' }",
    "    default { $s.hive }",
    "  }",
    "  $full = $hive + '\\' + $s.path",
    "  $v = $null",
    "  try {",
    "    if ($s.name) {",
    "      $v = (Get-ItemProperty -Path ('Registry::' + $full) -Name $s.name -ErrorAction Stop).($s.name)",
    "    } else {",
    "      $v = (Get-ItemProperty -Path ('Registry::' + $full) -ErrorAction Stop).'(default)'",
    "    }",
    "  } catch { $v = $null }",
    "  $out[$s.id] = $v",
    "}",
    "$out | ConvertTo-Json -Compress",
  ].join("\n");

  const res = jarvis.cap("windows.script.exec", {
    interpreter: "powershell",
    script: ps,
    stdin: json,
    timeout_ms: 60000,
  });
  if (!res.success) {
    warn("注册表批量读取失败：" + res.error);
    return {};
  }
  const text = (res.data.stdout || "").trim();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (e) {
    warn("注册表读取结果解析失败：" + e.message + " 原文：" + text);
    return {};
  }
}

// 判断路径是否真实存在
function fileExists(p) {
  if (!p) return false;
  const res = jarvis.cap("windows.fs.read", { path: p, limit: 1 });
  return res.success;
}

// 从 open 命令里抽出 exe 路径（形如 "C:\a b\x.exe" "%1"）
function extractExe(command) {
  if (!command) return null;
  const m = command.match(/^\s*"([^"]+\.exe)"/i) || command.match(/^\s*([^\s]+\.exe)/i);
  return m ? m[1] : null;
}

// 根据 ProgID 推断应使用的 exe 名
// 新版命名：ET.*(表格) / WPS.*(文字) / WPP.*(演示)
// 旧版命名：KWPS.*(文字) / KWPP.*(演示)
function wantExeFor(progId) {
  const base = progId.split(".")[0].toLowerCase();
  if (base === "et") return "et";
  if (base === "wps" || base === "kwps") return "wps";
  if (base === "wpp" || base === "kwpp") return "wpp";
  return null;
}

// 判断 progId 是否以任一候选前缀开头
function matchAnyPrefix(progId, prefixes) {
  const s = String(progId || "");
  for (let i = 0; i < prefixes.length; i++) {
    if (s.indexOf(prefixes[i]) === 0) return true;
  }
  return false;
}

// 把原 open 命令里的 exe 路径替换为新路径，保留其余参数
// 例："D:\WPS Office\12.1.0.29690\office6\wps.exe" /prometheus /wps "%1"
//   → "D:\WPS Office\12.1.0.20784\office6\wps.exe" /prometheus /wps "%1"
function rebuildCommand(origCmd, newExe) {
  const m = origCmd.match(/^\s*("[^"]+\.exe"|[^\s]+\.exe)/i);
  if (!m) return '"' + newExe + '" "%1"';
  return '"' + newExe + '"' + origCmd.slice(m[0].length);
}

// 取最新（最靠后）的可用 exe 作为修正目标
function pickExe(probe, want) {
  const list = probe.exes[want];
  if (!list || list.length === 0) return null;
  return list[list.length - 1];
}

// 用 PowerShell 写注册表默认值
function regWriteDefault(hive, path, value) {
  const hiveMap = {
    HKCU: "HKEY_CURRENT_USER",
    HKLM: "HKEY_LOCAL_MACHINE",
    HKCR: "HKEY_CLASSES_ROOT",
  };
  const full = (hiveMap[hive] || hive) + "\\" + path;
  const ps = [
    "$ErrorActionPreference='Stop'",
    "$full = $env:JARVIS_REG_FULL",
    "$val = $env:JARVIS_REG_VAL",
    "if (-not (Test-Path ('Registry::' + $full))) { New-Item -Path ('Registry::' + $full) -Force | Out-Null }",
    "Set-ItemProperty -Path ('Registry::' + $full) -Name '(default)' -Value $val",
    "Write-Output 'fixed'",
  ].join("\n");
  const res = jarvis.cap("windows.script.exec", {
    interpreter: "powershell",
    script: ps,
    env: { JARVIS_REG_FULL: full, JARVIS_REG_VAL: value },
    timeout_ms: 30000,
  });
  return res.success && (res.data.stdout || "").indexOf("fixed") >= 0;
}

// ---------- 3. 巡检 ProgID 的 open 命令 ----------

function checkProgIds(probe) {
  log("");
  log("=== 巡检 ProgID open 命令 ===");

  const spec = PROGIDS.map((p) => ({
    id: p,
    hive: "HKCR",
    path: p + "\\shell\\open\\command",
    name: "",
  }));
  const vals = regReadBatch(spec);

  for (const progId of PROGIDS) {
    const cmd = vals[progId];
    if (cmd === null || cmd === undefined || cmd === "") {
      notes.push("ProgID " + progId + " 未注册（跳过）");
      continue;
    }
    const exe = extractExe(cmd);
    if (!exe) {
      warn(progId + " 的 open 命令无法解析出 exe：" + cmd);
      continue;
    }
    if (fileExists(exe)) {
      log("  [OK]   " + progId + " -> " + exe);
      continue;
    }

    warn(progId + " 的 open 命令指向不存在的文件：" + exe + "（命令原文：" + cmd + "）");
    const want = wantExeFor(progId);
    const suggestion = want ? pickExe(probe, want) : null;
    if (!suggestion) continue;

    notes.push("  → " + progId + " 建议修正为：" + suggestion);
    if (doFix) {
      const newCmd = rebuildCommand(cmd, suggestion);
      if (regWriteDefault("HKCR", progId + "\\shell\\open\\command", newCmd)) {
        log("  [已修复] " + progId + " -> " + newCmd);
      } else {
        warn("  修复 " + progId + " 失败（可能需管理员权限）");
      }
    }
  }
}

// ---------- 4. 巡检 App Paths ----------

function checkAppPaths(probe) {
  log("");
  log("=== 巡检 App Paths ===");

  const targets = [
    { name: "et.exe", want: "et" },
    { name: "wps.exe", want: "wps" },
    { name: "wpp.exe", want: "wpp" },
  ];
  const roots = ["HKCU", "HKLM"];

  const spec = [];
  for (const root of roots) {
    for (const t of targets) {
      spec.push({
        id: root + "|" + t.name,
        hive: root,
        path: "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + t.name,
        name: "",
      });
    }
  }
  const vals = regReadBatch(spec);

  for (const root of roots) {
    for (const t of targets) {
      const id = root + "|" + t.name;
      const val = vals[id];
      if (val === null || val === undefined || val === "") continue;

      if (fileExists(val)) {
        log("  [OK]   " + root + " App Paths\\" + t.name + " -> " + val);
        continue;
      }

      warn(root + " App Paths\\" + t.name + " 指向不存在的文件：" + val);
      const suggestion = pickExe(probe, t.want);
      if (!suggestion) continue;

      notes.push("  → " + root + " App Paths\\" + t.name + " 建议修正为：" + suggestion);
      if (doFix) {
        const ok = regWriteDefault(
          root,
          "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + t.name,
          suggestion,
        );
        if (ok) {
          log("  [已修复] " + root + " App Paths\\" + t.name + " -> " + suggestion);
        } else {
          warn("  修复 " + root + " App Paths\\" + t.name + " 失败（可能需管理员权限）");
        }
      }
    }
  }
}

// ---------- 5. 巡检扩展名 → ProgID 映射 ----------

function checkExtensions() {
  log("");
  log("=== 巡检扩展名关联 ===");

  const spec = [];
  for (const ext in EXTENSIONS) {
    spec.push({ id: "hkcr|" + ext, hive: "HKCR", path: ext, name: "" });
    spec.push({
      id: "uc|" + ext,
      hive: "HKCU",
      path:
        "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\" + ext + "\\UserChoice",
      name: "ProgId",
    });
  }
  const vals = regReadBatch(spec);

  for (const ext in EXTENSIONS) {
    const expectedPrefixes = EXTENSIONS[ext];
    const hkcrProgId = vals["hkcr|" + ext];
    const ucProgId = vals["uc|" + ext];

    // HKCR 默认 ProgID
    if (hkcrProgId === null || hkcrProgId === undefined || hkcrProgId === "") {
      warn(ext + " 在 HKCR 下没有默认 ProgID");
    } else if (!matchAnyPrefix(hkcrProgId, expectedPrefixes)) {
      warn(
        ext + " 的 HKCR 默认 ProgID 为 " + hkcrProgId +
        "，期望以 " + expectedPrefixes.join(" 或 ") + " 开头"
      );
    } else {
      log("  [OK]   " + ext + " -> " + hkcrProgId + " (HKCR)");
    }

    // HKCU UserChoice（存在则优先级最高）
    if (ucProgId !== null && ucProgId !== undefined && ucProgId !== "") {
      if (!matchAnyPrefix(ucProgId, expectedPrefixes)) {
        warn(
          ext + " 的 UserChoice ProgId 为 " + ucProgId +
          "，期望以 " + expectedPrefixes.join(" 或 ") + " 开头"
        );
      } else {
        log("  [OK]   " + ext + " -> " + ucProgId + " (UserChoice)");
      }
    } else {
      notes.push(ext + " 无 UserChoice，将回落到 HKCR 默认 ProgID");
    }
  }
}

// ---------- 主流程 ----------

log("WPS 文件关联巡检");
log("WPS 安装根目录：" + wpsRoot);
log("模式：" + (doFix ? "检查并自动修复" : "仅检查（加 --arg fix=1 可自动修复）"));
log("----------------------------------------");

const probe = probeWpsInstall();
checkProgIds(probe);
checkAppPaths(probe);
checkExtensions();

log("");
log("----------------------------------------");
log("巡检完成：发现 " + issues.length + " 个问题");

if (notes.length > 0) {
  log("");
  log("补充说明：");
  for (const n of notes) log(n);
}

if (issues.length > 0) {
  log("");
  log("问题清单：");
  for (let i = 0; i < issues.length; i++) {
    log("  " + (i + 1) + ". " + issues[i]);
  }
  if (!doFix) {
    log("");
    log("提示：加 --arg fix=1 可自动把失效路径修正为当前实际存在的版本。");
  }
}

// 顶层返回值
({
  ok: issues.length === 0,
  issue_count: issues.length,
  issues: issues,
  fixed: doFix,
});
