// Cookie 执行器：封装 chrome.cookies 相关操作。
//
// ⚠️ 高敏感权限：Cookie 等同于登录凭证，读取或修改 Cookie 可能导致账号被冒用。
// set/remove 会真实改动用户的登录态，属不可逆操作，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class CookiesExecutor {
  /** 读取指定 URL 下的单个 Cookie。 */
  async get({ url, name } = {}) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    if (!name) throw cmdError("EXEC_ERROR", "name is required");
    const cookie = await chrome.cookies.get({
      url: String(url),
      name: String(name),
    });
    return cookie ? this._toCookie(cookie) : null;
  }

  /** 读取指定 URL 或域名下的全部 Cookie。 */
  async getAll({ url, domain } = {}) {
    if (!url && !domain) {
      throw cmdError("EXEC_ERROR", "url or domain is required");
    }
    const query = {};
    if (url) query.url = String(url);
    if (domain) query.domain = String(domain);
    const cookies = await chrome.cookies.getAll(query);
    return cookies.map((c) => this._toCookie(c));
  }

  /**
   * 写入 Cookie（高敏感，会真实改动登录态）。
   * 需 url、name、value；可选 domain/path/secure/http_only/same_site/expiration_date。
   */
  async set({
    url,
    name,
    value,
    domain,
    path,
    secure,
    http_only,
    same_site,
    expiration_date,
  } = {}) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    if (!name) throw cmdError("EXEC_ERROR", "name is required");
    const details = {
      url: String(url),
      name: String(name),
      value: value != null ? String(value) : "",
    };
    if (domain) details.domain = String(domain);
    if (path) details.path = String(path);
    if (secure != null) details.secure = Boolean(secure);
    if (http_only != null) details.httpOnly = Boolean(http_only);
    if (same_site) details.sameSite = String(same_site);
    if (expiration_date != null)
      details.expirationDate = Number(expiration_date);
    const cookie = await chrome.cookies.set(details);
    return { ok: true, cookie: cookie ? this._toCookie(cookie) : null };
  }

  /** 删除 Cookie（高敏感，不可逆）。 */
  async remove({ url, name } = {}) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    if (!name) throw cmdError("EXEC_ERROR", "name is required");
    const result = await chrome.cookies.remove({
      url: String(url),
      name: String(name),
    });
    return { ok: Boolean(result), url: String(url), name: String(name) };
  }

  /** 把 chrome Cookie 转换为对外结构。 */
  _toCookie(cookie) {
    return {
      name: cookie.name ?? "",
      value: cookie.value ?? "",
      domain: cookie.domain ?? "",
      path: cookie.path ?? "",
      secure: Boolean(cookie.secure),
      http_only: Boolean(cookie.httpOnly),
      same_site: cookie.sameSite ?? "",
      session: Boolean(cookie.session),
      expiration_date: cookie.expirationDate ?? null,
      host_only: Boolean(cookie.hostOnly),
    };
  }
}
