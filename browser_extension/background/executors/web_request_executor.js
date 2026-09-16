// 网络规则执行器：基于 declarativeNetRequest 管理网络拦截/改向规则。
//
// ⚠️ 高敏感权限：可拦截、阻断或重定向用户的网络请求。
// MV3 下 chrome.webRequest 已无法阻断请求，阻断能力统一由 declarativeNetRequest 提供；
// 动态规则需在 manifest 声明 declarativeNetRequest 权限（本扩展已声明 webRequest，
// 若需实际生效请补充 declarativeNetRequest 权限与 host 权限）。
// register 会真实影响用户上网，属高风险操作，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class WebRequestExecutor {
  /** 列出当前已注册的动态规则。 */
  async listRules() {
    this._ensureSupported();
    const rules = await chrome.declarativeNetRequest.getDynamicRules();
    return rules.map((r) => this._toRule(r));
  }

  /**
   * 注册一条动态规则（高敏感）。
   * 需 rule_id、url_filter；可选 action_type（block/allow/redirect）、redirect_url、priority。
   */
  async registerRule({
    rule_id,
    url_filter,
    action_type,
    redirect_url,
    priority,
  } = {}) {
    this._ensureSupported();
    if (rule_id == null) throw cmdError("NO_ID", "rule_id is required");
    if (!url_filter) throw cmdError("EXEC_ERROR", "url_filter is required");
    const type = action_type ? String(action_type) : "block";
    const action = { type };
    if (type === "redirect") {
      if (!redirect_url) {
        throw cmdError(
          "EXEC_ERROR",
          "redirect_url is required for redirect action",
        );
      }
      action.redirect = { url: String(redirect_url) };
    }
    const rule = {
      id: Number(rule_id),
      priority: priority != null ? Number(priority) : 1,
      action,
      condition: { urlFilter: String(url_filter) },
    };
    await chrome.declarativeNetRequest.updateDynamicRules({
      addRules: [rule],
      removeRuleIds: [Number(rule_id)],
    });
    return { ok: true, rule_id: Number(rule_id) };
  }

  /** 注销指定动态规则。 */
  async unregisterRule({ rule_id } = {}) {
    this._ensureSupported();
    if (rule_id == null) throw cmdError("NO_ID", "rule_id is required");
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: [Number(rule_id)],
    });
    return { ok: true, rule_id: Number(rule_id) };
  }

  /** 检查 API 是否可用。 */
  _ensureSupported() {
    if (!chrome.declarativeNetRequest) {
      throw cmdError(
        "NOT_SUPPORTED",
        "chrome.declarativeNetRequest is not available; add the declarativeNetRequest permission",
      );
    }
  }

  /** 把 chrome 规则转换为对外结构。 */
  _toRule(rule) {
    return {
      rule_id: rule.id ?? null,
      priority: rule.priority ?? 1,
      action_type: rule.action?.type ?? "",
      redirect_url: rule.action?.redirect?.url ?? null,
      url_filter: rule.condition?.urlFilter ?? "",
    };
  }
}
