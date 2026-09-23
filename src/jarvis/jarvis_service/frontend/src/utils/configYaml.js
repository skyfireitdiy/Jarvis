// 轻量 YAML 序列化 / 解析工具
// 覆盖配置 Schema 常见数据类型（标量、嵌套对象、数组），用于纯文本预览与编辑。
// 不引入第三方依赖，保持前端改动最小。

export function cloneValue(v) {
  if (v === null || typeof v !== "object") return v;
  return JSON.parse(JSON.stringify(v));
}

// ===== 序列化 =====
export function toYaml(value) {
  return yamlDump(value, 0);
}

function yamlDump(value, indent) {
  const pad = "  ".repeat(indent);
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return yamlQuote(value);
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    return value
      .map((item) => {
        if (item !== null && typeof item === "object") {
          return `${pad}- ${yamlDumpInline(item)}`;
        }
        return `${pad}- ${yamlDump(item, 0)}`;
      })
      .join("\n");
  }
  if (typeof value === "object") {
    const keys = Object.keys(value);
    if (keys.length === 0) return "{}";
    return keys
      .map((k) => {
        const v = value[k];
        if (v !== null && typeof v === "object") {
          return `${pad}${yamlKey(k)}:\n${yamlDump(v, indent + 1)}`;
        }
        return `${pad}${yamlKey(k)}: ${yamlDump(v, 0)}`;
      })
      .join("\n");
  }
  return String(value);
}

function yamlDumpInline(value) {
  // 数组项中的对象：首行键对齐到「- 」之后
  if (value === null || typeof value !== "object") return yamlDump(value, 0);
  if (Array.isArray(value)) return JSON.stringify(value);
  const keys = Object.keys(value);
  if (keys.length === 0) return "{}";
  return keys
    .map((k, i) => {
      const v = value[k];
      const prefix = i === 0 ? "" : "  ";
      if (v !== null && typeof v === "object") {
        return `${prefix}${yamlKey(k)}:\n${yamlDump(v, 2)}`;
      }
      return `${prefix}${yamlKey(k)}: ${yamlDump(v, 0)}`;
    })
    .join("\n");
}

function yamlKey(k) {
  return /^[A-Za-z0-9_\-./]+$/.test(k) ? k : yamlQuote(k);
}

function yamlQuote(s) {
  if (s === "") return "''";
  // 纯文本/常见字符无需引号；排除会被误解析为布尔/空值的词
  if (
    /^[A-Za-z0-9_\-. /\u4e00-\u9fa5]+$/.test(s) &&
    !/^(true|false|null|yes|no|on|off|~)$/i.test(s)
  ) {
    return s;
  }
  return JSON.stringify(s);
}

// ===== 解析 =====
export function parseYaml(text) {
  const lines = String(text).split("\n");
  const result = {};
  const stack = []; // { indent, obj }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === "" || trimmed.startsWith("#")) continue;
    const indent = line.length - line.replace(/^ +/, "").length;
    while (stack.length > 0 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }
    const parent = stack.length > 0 ? stack[stack.length - 1].obj : result;
    const parsed = parseYamlLine(trimmed);
    if (!parsed) continue;
    const { key, value, isContainer } = parsed;
    if (isContainer) {
      const child = {};
      parent[key] = child;
      stack.push({ indent, obj: child });
    } else {
      parent[key] = value;
    }
  }
  return result;
}

function parseYamlLine(line) {
  const m = line.match(/^([^:]+):(?:\s+(.*))?$/);
  if (!m) return null;
  const key = unquote(m[1].trim());
  const rawValue = (m[2] || "").trim();
  if (rawValue === "") {
    // 空值：可能是容器（后续缩进行）或空值
    return { key, value: null, isContainer: true };
  }
  return { key, value: parseScalar(rawValue), isContainer: false };
}

function parseScalar(s) {
  if (s === "null" || s === "~") return null;
  if (s === "true") return true;
  if (s === "false") return false;
  if (/^-?\d+$/.test(s)) return parseInt(s, 10);
  if (/^-?\d+\.\d+$/.test(s)) return parseFloat(s);
  return unquote(s);
}

function unquote(s) {
  if (s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"') {
    try {
      return JSON.parse(s);
    } catch (e) {
      return s.slice(1, -1);
    }
  }
  if (s.length >= 2 && s[0] === "'" && s[s.length - 1] === "'")
    return s.slice(1, -1);
  return s;
}
