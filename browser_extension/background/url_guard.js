// URL 安全守卫：判定一个 URL 是否允许被扩展主动拉取。
//
// 用途：`script.install_from_url` 会按用户/Agent 给定的 URL 去下载脚本源码。
// 若不限制，该能力可被用来探测内网服务（SSRF）或读取本机文件，因此这里做白名单式校验：
//   - 仅允许 http / https 协议（禁 file:、ftp:、data: 等）；
//   - 拒绝回环、私有、链路本地等内网地址（IPv4 与 IPv6 均覆盖）；
//   - 拒绝 localhost 及其子域。
//
// 本模块**刻意不依赖任何 chrome API 或其它模块**，以便被 node 直接 import 做单元测试。

/** 允许的协议白名单。 */
const ALLOWED_PROTOCOLS = ["http:", "https:"];

/**
 * 判定 IPv4 字面量是否属于「不可访问」网段。
 * 覆盖：0.0.0.0/8、10/8、127/8、169.254/16、172.16/12、192.168/16。
 * @param {string} host 形如 "127.0.0.1"
 * @returns {boolean} true 表示应拒绝
 */
function isBlockedIPv4(host) {
  const parts = host.split(".");
  if (parts.length !== 4) return false;
  const nums = [];
  for (const p of parts) {
    // 只接受纯十进制数字（拒绝 0x7f.1 这类非标准写法）
    if (!/^\d{1,3}$/.test(p)) return false;
    const n = Number(p);
    if (n > 255) return false;
    nums.push(n);
  }
  const [a, b] = nums;
  if (a === 0) return true; // 0.0.0.0/8
  if (a === 10) return true; // 10.0.0.0/8
  if (a === 127) return true; // 127.0.0.0/8
  if (a === 169 && b === 254) return true; // 169.254.0.0/16
  if (a === 172 && b >= 16 && b <= 31) return true; // 172.16.0.0/12
  if (a === 192 && b === 168) return true; // 192.168.0.0/16
  return false;
}

/**
 * 判定 IPv6 字面量是否属于「不可访问」地址。
 * 覆盖：::1（回环）、::（未指定）、fe80::/10（链路本地）、fc00::/7（唯一本地）。
 * @param {string} host 形如 "::1" 或 "[::1]"（方括号已去除）
 * @returns {boolean} true 表示应拒绝
 */
function isBlockedIPv6(host) {
  const h = host.toLowerCase().replace(/^\[|\]$/g, "");
  if (!h.includes(":")) return false;
  if (h === "::1" || h === "::" || h === "0:0:0:0:0:0:0:1") return true;
  // fe80::/10 链路本地
  if (/^fe[89ab]/.test(h)) return true;
  // fc00::/7 唯一本地地址
  if (/^f[cd]/.test(h)) return true;
  return false;
}

/**
 * 判定 hostname 是否属于内网 / 回环 / 本机。
 * @param {string} hostname URL 的 hostname（不含端口）
 * @returns {boolean} true 表示应拒绝
 */
function isBlockedHostname(hostname) {
  const h = String(hostname || "")
    .trim()
    .toLowerCase();
  if (!h) return true;
  // localhost 及其子域
  if (h === "localhost" || h.endsWith(".localhost")) return true;
  // 去掉 IPv6 的方括号后判断
  const bare = h.replace(/^\[|\]$/g, "");
  if (isBlockedIPv6(bare)) return true;
  if (isBlockedIPv4(bare)) return true;
  return false;
}

/**
 * 校验脚本下载 URL 是否安全可用。
 *
 * @param {string} url 待校验的 URL
 * @returns {{ok: boolean, reason?: string}} ok=false 时 reason 为拒绝原因
 */
export function isAllowedScriptUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return { ok: false, reason: "url is required" };

  let parsed;
  try {
    parsed = new URL(raw);
  } catch (e) {
    return { ok: false, reason: `invalid url: ${raw}` };
  }

  if (!ALLOWED_PROTOCOLS.includes(parsed.protocol)) {
    return {
      ok: false,
      reason: `only http/https is allowed, got: ${parsed.protocol}`,
    };
  }

  if (isBlockedHostname(parsed.hostname)) {
    return {
      ok: false,
      reason: `refusing to fetch from private/loopback host: ${parsed.hostname}`,
    };
  }

  return { ok: true };
}

/**
 * 从 URL 推导脚本名：取 pathname 末段文件名，去掉 .js 后缀。
 * 推导不出时返回空字符串（由调用方决定是否报错）。
 *
 * @param {string} url 脚本 URL
 * @returns {string} 推导出的脚本名；无法推导时为空串
 */
export function deriveNameFromUrl(url) {
  try {
    const parsed = new URL(String(url || "").trim());
    const segs = parsed.pathname.split("/").filter(Boolean);
    if (!segs.length) return "";
    const last = decodeURIComponent(segs[segs.length - 1]);
    return last.replace(/\.js$/i, "").trim();
  } catch (e) {
    return "";
  }
}
