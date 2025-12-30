# -*- coding: utf-8 -*-
import subprocess
import sys
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple


class git_work_summary:
    """
    Git工作总结生成工具
    
    根据时间段和作者筛选Git仓库提交记录，自动分类生成工作总结和述职报告。
    支持多种提交类型自动识别，生成结构化的Markdown格式报告。
    """
    
    # 工具基本信息
    name = "git_work_summary"
    description = """根据时间段和作者筛选Git仓库提交记录，自动分类生成工作总结和述职报告。

功能要求：
1. 支持指定Git仓库路径、开始日期、结束日期、作者名称
2. 使用git log命令获取提交记录（格式：hash|date|message）
3. 自动分析提交信息，按类型分类：
   - fix: 修复类（包含fix、bug、修复等关键词）
   - refactor: 优化/重构类（包含refactor、optimize、优化等关键词）
   - feat: 实现类（包含feat、add、new、新增等关键词）
   - docs: 文档类（包含doc、文档等关键词）
   - test: 测试类（包含test、测试等关键词）
   - chore: 杂项/工具类（包含chore、build、lint等关键词）
   - style: 样式类（包含style、format等关键词）
4. 生成结构化的工作总结，包含：
   - 提交统计概览（总数、时间范围）
   - 各类别的详细列表
   - 工作亮点总结
5. 支持生成述职报告格式（可选）
6. 返回结构化的JSON结果，包含success、stdout（Markdown格式总结）、stderr"""
    
    parameters = {
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": "Git仓库路径（默认当前目录）"
            },
            "start_date": {
                "type": "string",
                "description": "开始日期（YYYY-MM-DD格式）"
            },
            "end_date": {
                "type": "string",
                "description": "结束日期（YYYY-MM-DD格式，默认今天）"
            },
            "author": {
                "type": "string",
                "description": "作者名称（必须）"
            },
            "generate_report": {
                "type": "boolean",
                "description": "是否生成述职报告格式（布尔值，默认false）",
                "default": False
            }
        },
        "required": ["author"]
    }
    
    # ---------------- 内部实现 ----------------
    
    @staticmethod
    def check() -> bool:
        """检查git命令是否可用"""
        try:
            result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                check=True
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    @staticmethod
    def _validate_date_format(date_str: str) -> bool:
        """验证日期格式是否为YYYY-MM-DD"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    @staticmethod
    def _classify_commit(message: str) -> str:
        """
        根据提交信息分类
        
        返回分类类型：fix, refactor, feat, docs, test, chore, style, other
        """
        msg_lower = message.lower()
        
        # 定义分类关键词
        categories = {
            'fix': ['fix', 'bug', '修复', '修复bug', 'bugfix', 'hotfix'],
            'refactor': ['refactor', 'optimize', '优化', '重构', 'refactoring'],
            'feat': ['feat', 'add', 'new', '新增', 'feature', 'implement', '实现'],
            'docs': ['doc', '文档', 'readme', 'changelog'],
            'test': ['test', '测试', 'testing', 'unit test', '测试用例'],
            'chore': ['chore', 'build', 'lint', '依赖', 'dependency', 'config', '配置'],
            'style': ['style', 'format', '格式', '代码风格', 'formatting']
        }
        
        # 按优先级匹配
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in msg_lower:
                    return category
        
        return 'other'
    
    def _get_commits(self, repo_path: str, start_date: str, 
                     end_date: str, author: str) -> Tuple[List[Tuple[str, str, str]], str]:
        """
        获取Git提交记录
        
        返回: (提交列表, 错误信息)
        提交列表格式: [(hash, date, message), ...]
        """
        # 切换到仓库目录
        original_dir = os.getcwd()
        try:
            os.chdir(repo_path)
        except FileNotFoundError:
            return [], f"仓库路径不存在: {repo_path}"
        
        try:
            # 构造git log命令
            cmd = [
                'git', 'log',
                f'--pretty=format:%H|%ai|%s',
                f'--author={author}',
                f'--after={start_date}',
                f'--before={end_date}'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                # 可能是空仓库或其他错误
                if 'not a git repository' in result.stderr:
                    return [], f"目录不是Git仓库: {repo_path}"
                # 其他错误但可能有输出
                
            # 解析输出
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('|', 2)
                    if len(parts) == 3:
                        commit_hash, commit_date, commit_msg = parts
                        commits.append((commit_hash, commit_date, commit_msg))
            
            return commits, ""
            
        except Exception as e:
            return [], f"执行git命令失败: {str(e)}"
        finally:
            os.chdir(original_dir)
    
    def _generate_summary(self, commits: List[Tuple[str, str, str]], 
                         start_date: str, end_date: str,
                         author: str, generate_report: bool) -> str:
        """
        生成工作总结报告
        
        返回: Markdown格式的总结文本
        """
        total_commits = len(commits)
        
        if total_commits == 0:
            return f"""# Git工作总结

**时间范围**: {start_date} 至 {end_date}
**作者**: {author}
**提交总数**: 0

---

⚠️ 未找到符合条件的提交记录。
"""
        
        # 分类提交
        categorized: Dict[str, List[Tuple[str, str, str]]] = {
            'fix': [],
            'refactor': [],
            'feat': [],
            'docs': [],
            'test': [],
            'chore': [],
            'style': [],
            'other': []
        }
        
        for commit in commits:
            commit_hash, commit_date, commit_msg = commit
            category = self._classify_commit(commit_msg)
            categorized[category].append(commit)
        
        # 统计各类型数量
        stats = {k: len(v) for k, v in categorized.items()}
        
        # 确定时间范围（实际有提交的时间）
        if commits:
            first_date = commits[-1][1][:10]  # 最早的提交
            last_date = commits[0][1][:10]   # 最新的提交
        else:
            first_date = start_date
            last_date = end_date
        
        # 生成报告
        if generate_report:
            report = self._generate_duty_report(
                commits, categorized, stats, 
                first_date, last_date, author
            )
        else:
            report = self._generate_standard_report(
                commits, categorized, stats,
                first_date, last_date, author
            )
        
        return report
    
    def _generate_standard_report(self, commits: List[Tuple[str, str, str]],
                                   categorized: Dict[str, List[Tuple[str, str, str]]],
                                   stats: Dict[str, int],
                                   first_date: str, last_date: str,
                                   author: str) -> str:
        """生成标准工作总结报告"""
        report = []
        
        # 标题和概览
        report.append(f"# Git工作总结")
        report.append("")
        report.append(f"**时间范围**: {first_date} 至 {last_date}")
        report.append(f"**作者**: {author}")
        report.append(f"**提交总数**: {len(commits)}")
        report.append("")
        report.append("---")
        report.append("")
        
        # 统计概览
        report.append("## 📊 统计概览")
        report.append("")
        for category, count in stats.items():
            if count > 0:
                emoji = {
                    'fix': '🐛',
                    'refactor': '♻️',
                    'feat': '✨',
                    'docs': '📝',
                    'test': '🧪',
                    'chore': '🔧',
                    'style': '💅',
                    'other': '📌'
                }.get(category, '•')
                report.append(f"- {emoji} **{category}**: {count} 次")
        report.append("")
        
        # 各类别详细列表
        category_names = {
            'feat': '✨ 功能实现',
            'fix': '🐛 问题修复',
            'refactor': '♻️ 优化重构',
            'docs': '📝 文档更新',
            'test': '🧪 测试相关',
            'chore': '🔧 构建工具',
            'style': '💅 代码风格',
            'other': '📌 其他'
        }
        
        for category, commits_list in categorized.items():
            if commits_list:
                report.append(f"## {category_names.get(category, category)}")
                report.append("")
                
                # 按时间倒序排列
                sorted_commits = sorted(commits_list, key=lambda x: x[1], reverse=True)
                
                for commit_hash, commit_date, commit_msg in sorted_commits:
                    short_hash = commit_hash[:7]
                    date_only = commit_date[:10]
                    report.append(f"- **{date_only}** `{short_hash}`: {commit_msg}")
                
                report.append("")
        
        # 工作亮点总结
        report.append("## 💡 工作亮点")
        report.append("")
        
        highlights = []
        if stats['feat'] > 0:
            highlights.append(f"- 完成了 {stats['feat']} 项新功能开发")
        if stats['fix'] > 0:
            highlights.append(f"- 修复了 {stats['fix']} 个问题")
        if stats['refactor'] > 0:
            highlights.append(f"- 进行了 {stats['refactor']} 次代码优化和重构")
        if stats['test'] > 0:
            highlights.append(f"- 提交了 {stats['test']} 个测试相关改动")
        if stats['docs'] > 0:
            highlights.append(f"- 完成了 {stats['docs']} 次文档更新")
        
        if not highlights:
            highlights.append("- 持续维护和改进")
        
        report.extend(highlights)
        report.append("")
        
        return "\n".join(report)
    
    def _generate_duty_report(self, commits: List[Tuple[str, str, str]],
                               categorized: Dict[str, List[Tuple[str, str, str]]],
                               stats: Dict[str, int],
                               first_date: str, last_date: str,
                               author: str) -> str:
        """生成述职报告格式"""
        report = []
        
        # 标题
        report.append(f"# 工作述职报告")
        report.append("")
        report.append(f"**述职人**: {author}")
        report.append(f"**工作周期**: {first_date} 至 {last_date}")
        report.append(f"**提交次数**: {len(commits)}")
        report.append("")
        report.append("---")
        report.append("")
        
        # 工作概述
        report.append("## 一、工作概述")
        report.append("")
        report.append(f"在本工作周期内，共完成 {len(commits)} 次代码提交，主要工作包括：")
        report.append("")
        
        if stats['feat'] > 0:
            report.append(f"- 新功能开发：{stats['feat']} 项")
        if stats['fix'] > 0:
            report.append(f"- 问题修复：{stats['fix']} 个")
        if stats['refactor'] > 0:
            report.append(f"- 代码优化重构：{stats['refactor']} 次")
        if stats['docs'] > 0:
            report.append(f"- 文档更新：{stats['docs']} 次")
        if stats['test'] > 0:
            report.append(f"- 测试相关工作：{stats['test']} 次")
        if stats['chore'] > 0:
            report.append(f"- 构建和工具改进：{stats['chore']} 次")
        
        report.append("")
        
        # 主要工作内容
        report.append("## 二、主要工作内容")
        report.append("")
        
        if categorized['feat']:
            report.append("### 1. 新功能开发")
            report.append("")
            for commit_hash, commit_date, commit_msg in categorized['feat']:
                short_hash = commit_hash[:7]
                date_only = commit_date[:10]
                report.append(f"- **{date_only}**: {commit_msg} (`{short_hash}`)")
            report.append("")
        
        if categorized['fix']:
            report.append("### 2. 问题修复")
            report.append("")
            for commit_hash, commit_date, commit_msg in categorized['fix']:
                short_hash = commit_hash[:7]
                date_only = commit_date[:10]
                report.append(f"- **{date_only}**: {commit_msg} (`{short_hash}`)")
            report.append("")
        
        if categorized['refactor']:
            report.append("### 3. 代码优化与重构")
            report.append("")
            for commit_hash, commit_date, commit_msg in categorized['refactor']:
                short_hash = commit_hash[:7]
                date_only = commit_date[:10]
                report.append(f"- **{date_only}**: {commit_msg} (`{short_hash}`)")
            report.append("")
        
        # 其他工作
        other_work = []
        if categorized['docs']:
            other_work.append(f"文档更新 ({stats['docs']} 次)")
        if categorized['test']:
            other_work.append(f"测试相关工作 ({stats['test']} 次)")
        if categorized['chore']:
            other_work.append(f"构建工具改进 ({stats['chore']} 次)")
        if categorized['style']:
            other_work.append(f"代码风格调整 ({stats['style']} 次)")
        
        if other_work:
            report.append("### 4. 其他工作")
            report.append("")
            for work in other_work:
                report.append(f"- {work}")
            report.append("")
        
        # 工作成果与亮点
        report.append("## 三、工作成果与亮点")
        report.append("")
        
        if stats['feat'] > 5:
            report.append(f"- **高效交付**: 完成多达 {stats['feat']} 项新功能")
        if stats['fix'] == 0:
            report.append(f"- **质量稳定**: 本周期内无缺陷修复记录，代码质量良好")
        elif stats['fix'] < stats['feat'] * 0.3:
            report.append(f"- **质量控制**: 缺陷率控制在较低水平 ({stats['fix']}/{stats['feat']})")
        if stats['refactor'] > 0:
            report.append(f"- **持续改进**: 主动进行代码优化重构 {stats['refactor']} 次")
        if stats['test'] > stats['feat']:
            report.append(f"- **测试意识**: 测试相关提交 ({stats['test']} 次) 超过功能开发")
        
        if not any([stats['feat'] > 5, stats['fix'] == 0, stats['fix'] < stats['feat'] * 0.3, 
                    stats['refactor'] > 0, stats['test'] > stats['feat']]):
            report.append("- 按计划完成了各项开发任务")
        
        report.append("")
        
        # 总结
        report.append("## 四、总结")
        report.append("")
        report.append(f"在本工作周期内，共完成 {len(commits)} 次提交，")
        
        if stats['feat'] > 0:
            report.append(f"主要完成了 {stats['feat']} 项新功能的开发，")
        if stats['fix'] > 0:
            report.append(f"修复了 {stats['fix']} 个问题，")
        if stats['refactor'] > 0:
            report.append(f"进行了 {stats['refactor']} 次代码优化，")
        
        report.append("整体工作进展顺利。")
        report.append("")
        report.append("---")
        report.append("")
        report.append("*本报告由 git_work_summary 工具自动生成*")
        
        return "\n".join(report)
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具主逻辑
        
        参数:
            args: 包含工具参数的字典
                - repo_path: Git仓库路径
                - start_date: 开始日期
                - end_date: 结束日期
                - author: 作者名称
                - generate_report: 是否生成述职报告格式
        
        返回:
            Dict[str, Any]: 执行结果
                - success: 是否成功
                - stdout: Markdown格式总结
                - stderr: 错误信息
        """
        # 自举能力：可以调用 CodeAgent 对自身进行分析和改进
        # from jarvis.jarvis_code_agent.code_agent import CodeAgent
        # 
        # if args.get('self_analyze'):
        #     agent = CodeAgent()
        #     return agent.run("分析git_work_summary工具的性能瓶颈并提出改进方案")
        
        try:
            # 参数解析
            repo_path = args.get('repo_path', os.getcwd())
            start_date = args.get('start_date')
            end_date = args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
            author = args.get('author')
            generate_report = bool(args.get('generate_report', False))
            
            # 参数校验
            if not author:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必填参数: author"
                }
            
            if start_date and not self._validate_date_format(start_date):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"开始日期格式错误，应为 YYYY-MM-DD 格式: {start_date}"
                }
            
            if not self._validate_date_format(end_date):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"结束日期格式错误，应为 YYYY-MM-DD 格式: {end_date}"
                }
            
            # 默认start_date为end_date前30天
            if not start_date:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                start_dt = end_dt.replace(day=1)  # 默认月初
                start_date = start_dt.strftime('%Y-%m-%d')
            
            # 检查仓库路径
            if not os.path.exists(repo_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"仓库路径不存在: {repo_path}"
                }
            
            # 获取提交记录
            print(f"[git_work_summary] 正在分析仓库: {repo_path}", flush=True)
            print(f"[git_work_summary] 时间范围: {start_date} 至 {end_date}", flush=True)
            print(f"[git_work_summary] 作者: {author}", flush=True)
            
            commits, error = self._get_commits(repo_path, start_date, end_date, author)
            
            if error:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error
                }
            
            print(f"[git_work_summary] 找到 {len(commits)} 条提交记录", flush=True)
            
            # 生成总结
            summary = self._generate_summary(
                commits, start_date, end_date, author, generate_report
            )
            
            print(f"[git_work_summary] 总结生成完成", flush=True)
            
            return {
                "success": True,
                "stdout": summary,
                "stderr": ""
            }
            
        except Exception as e:
            error_msg = f"工具执行失败: {str(e)}"
            print(f"[git_work_summary] {error_msg}", file=sys.stderr, flush=True)
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg
            }
