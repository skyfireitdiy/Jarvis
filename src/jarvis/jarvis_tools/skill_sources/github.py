# -*- coding: utf-8 -*-
"""GitHub 搜索源实现"""

import aiohttp
from typing import List, Optional
from .base import ISkillSource, SkillResult


class GitHubSkillSource(ISkillSource):
    """GitHub SKILL.md 文件搜索源"""

    API_URL = "https://api.github.com/search/code"

    def __init__(self, token: Optional[str] = None):
        """
        参数:
            token: GitHub Token（可选，提高速率限制）
        """
        self.token = token

    @property
    def name(self) -> str:
        return "github"

    @property
    def priority(self) -> int:
        return 50  # 中等优先级

    async def search(self, query: str, limit: int = 20) -> List[SkillResult]:
        """搜索 GitHub"""
        results = []

        if not query.strip():
            return results

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-Skill-Search",
        }

        if self.token:
            headers["Authorization"] = f"token {self.token}"

        search_query = f"{query} filename:SKILL.md language:Markdown"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.API_URL,
                    params={
                        "q": search_query,
                        "per_page": limit,
                        "sort": "indexed",
                        "order": "desc",
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        return results

                    data = await resp.json()

                    for item in data.get("items", []):
                        if not item.get("download_url"):
                            continue

                        repo = item.get("repository", {})
                        skill_name = self._extract_skill_name(item.get("path", ""))

                        results.append(
                            SkillResult(
                                name=skill_name,
                                description=repo.get("description", "")
                                or "GitHub Skill",
                                download_url=item["download_url"],
                                source_url=item.get("html_url", ""),
                                relevance_score=self._calc_relevance(
                                    query, f"{skill_name} {repo.get('description', '')}"
                                ),
                                quality_score=6.0,  # 默认值
                                popularity=int(repo.get("stargazers_count", 0)),
                                platform=self.name,
                                author=repo.get("owner", {}).get("login"),
                                tags=[],
                                license=None,
                                _raw_data=item,
                            )
                        )

        except Exception:
            pass

        return results

    def _extract_skill_name(self, path: str) -> str:
        """从路径提取技能名 (skills/xxx/SKILL.md → xxx)"""
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[-1] == "SKILL.md":
            return parts[-2]
        return parts[0].replace(".md", "") if parts else "unknown"
