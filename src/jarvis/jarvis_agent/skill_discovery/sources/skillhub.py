# -*- coding: utf-8 -*-
"""SkillHub 技能发现源实现"""

import aiohttp
from typing import List
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
                        repo_full = item.get("repo", "")
                        skill_id = item.get("id", "")

                        results.append(
                            SkillResult(
                                name=item.get("name", "unknown"),
                                description=item.get("description", ""),
                                download_url=f"https://raw.githubusercontent.com/{repo_full}/main/SKILL.md"
                                if repo_full
                                else "",
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
                                _raw_data=item,
                            )
                        )

        except Exception:
            # 静默失败，不影响其他源
            pass

        return results
