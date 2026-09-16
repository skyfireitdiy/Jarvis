// 常用站点执行器：封装 chrome.topSites 相关操作。
import { cmdError } from "../command_router.js";

export class TopSitesExecutor {
  /** 列出用户最常访问的站点。 */
  async list() {
    if (!chrome.topSites) {
      throw cmdError("NOT_SUPPORTED", "chrome.topSites is not available");
    }
    const sites = await chrome.topSites.get();
    return sites.map((s) => ({ title: s.title ?? "", url: s.url ?? "" }));
  }
}
