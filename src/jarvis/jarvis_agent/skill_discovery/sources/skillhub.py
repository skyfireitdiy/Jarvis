# -*- coding: utf-8 -*-
"""SkillHub 技能发现源实现"""

import aiohttp
from typing import List, Optional, Dict
from .base import ISkillSource, SkillResult


class SkillHubSource(ISkillSource):
    """SkillHub 技能发现源"""

    BASE_URL = "https://www.skillhub.club/api"

    @property
    def name(self) -> str:
        return "skillhub"

    @property
    def priority(self) -> int:
        return 10  # 高优先级

    def _parse_repo_url(self, repo_url: str) -> Optional[Dict]:
        """
        解析 SkillHub repo_url 格式
        格式：https://github.com/owner/repo#path~to~skill
        返回：{"clone_url": "...", "subdir": "path/to/skill", "owner": "...", "repo": "..."}
        """
        if not repo_url or "github.com" not in repo_url:
            return None

        try:
            # 分离锚点
            parts = repo_url.split("#")
            base_url = parts[0]
            anchor = parts[1] if len(parts) > 1 else ""

            # 提取 owner/repo
            path_parts = (
                base_url.replace("https://github.com/", "").strip("/").split("/")
            )
            if len(path_parts) < 2:
                return None

            owner = path_parts[0]
            repo = path_parts[1]
            clone_url = f"https://github.com/{owner}/{repo}.git"

            # 解析子目录路径 (skills~owner~skill-name -> skills/owner/skill-name)
            subdir = ""
            if anchor:
                subdir = anchor.replace("~", "/")

            return {
                "clone_url": clone_url,
                "subdir": subdir,
                "owner": owner,
                "repo": repo,
            }
        except Exception:
            return None

    async def search(self, query: str, limit: int = 20) -> List[SkillResult]:
        """搜索 SkillHub"""
        results = []

        if not query.strip():
            return results

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/search",
                    params={"q": query, "limit": limit},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        return results

                    data = await resp.json()

                    for item in data.get("skills", []):
                        repo_url = item.get("repo_url", "")
                        skill_id = item.get("id", "")

                        # 解析 repo_url 获取仓库信息
                        repo_info = self._parse_repo_url(repo_url)

                        # download_url 存储 git clone URL
                        download_url = repo_info["clone_url"] if repo_info else ""

                        results.append(
                            SkillResult(
                                name=item.get("name", "unknown"),
                                description=item.get("description", ""),
                                download_url=download_url,
                                source_url=f"https://www.skillhub.club/skills/{skill_id}"
                                if skill_id
                                else "",
                                relevance_score=self._calc_relevance(
                                    query,
                                    f"{item.get('name', '')} {item.get('description', '')}",
                                ),
                                quality_score=float(item.get("rating", 0)),
                                popularity=int(item.get("stars", 0)),
                                platform=self.name,
                                author=item.get("author"),
                                tags=item.get("tags", []),
                                _raw_data={**item, "repo_info": repo_info},
                            )
                        )

        except Exception:
            # 静默失败，不影响其他源
            pass

        return results
