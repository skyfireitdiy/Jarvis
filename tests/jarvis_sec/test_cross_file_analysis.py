# -*- coding: utf-8 -*-
"""跨文件分析能力测试框架（数据集驱动 + 自发现模式）

测试内容：
1. 跨文件UAF检测
2. 跨文件Double Free检测
3. 跨文件数据流分析

测试集目录结构：
- tests/jarvis_sec/datasets/cross_file/：跨文件分析测试集
  - uaf/：跨文件UAF测试
  - double_free/：跨文件Double Free测试
  - data_flow/：跨文件数据流测试

添加新数据集：只需在对应类别目录下创建子目录，放入.c文件和metadata.json，
测试框架会自动发现并生成测试，无需修改测试代码。
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path

from jarvis.jarvis_sec.checkers.c_checker import analyze_files
from jarvis.jarvis_sec.types import Issue

# 测试数据集根目录
DATASETS_ROOT = Path(__file__).parent / "datasets" / "cross_file"


# ============================================================================
# 测试框架工具函数
# ============================================================================


def discover_datasets(category: str) -> list[tuple[str, Path, dict]]:
    """自动发现指定类别下的所有数据集"""
    results = []
    category_dir = DATASETS_ROOT / category
    if not category_dir.exists():
        return results
    for case_dir in sorted(category_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        metadata_file = case_dir / "metadata.json"
        if not metadata_file.exists():
            continue
        with open(metadata_file) as f:
            metadata = json.load(f)
        results.append((case_dir.name, case_dir, metadata))
    return results


def discover_all_datasets() -> list[tuple[str, str, Path, dict]]:
    """自动发现所有类别下的所有数据集

    Returns:
        [(category, case_name, case_dir, metadata), ...]
    """
    results = []
    for category_dir in sorted(DATASETS_ROOT.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for case_name, case_dir, metadata in discover_datasets(category):
            results.append((category, case_name, case_dir, metadata))
    return results


def run_checker(project_dir: Path) -> list[Issue]:
    """运行checker分析"""
    from jarvis.jarvis_sec.project_database import ProjectDatabase
    from jarvis.jarvis_sec.data_collector import DataCollector

    c_files = list(project_dir.rglob("*.c"))
    c_files.extend(project_dir.rglob("*.cpp"))
    c_files.extend(project_dir.rglob("*.h"))
    c_files.extend(project_dir.rglob("*.hpp"))

    rel_files = [str(f.relative_to(project_dir)) for f in c_files]

    db_path = project_dir / ".jarvis" / "jsec" / "analysis.db"
    db_path.resolve().parent.mkdir(parents=True, exist_ok=True)
    database = ProjectDatabase(str(project_dir), db_path=str(db_path.resolve()))

    collector = DataCollector(database)
    for file_path in c_files:
        collector.analyze_file(str(file_path), "c")

    issues = analyze_files(str(project_dir), rel_files, database=database)
    return issues


def create_test_project(base_dir: Path, test_name: str, files: dict[str, str]) -> Path:
    """创建测试项目目录结构（仅用于集成测试）"""
    project_dir = base_dir / test_name
    project_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        file_path = project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
    return project_dir


class TestDatasetDriven:
    """数据集驱动的跨文件分析测试

    自动发现 datasets/cross_file/ 下所有包含 metadata.json 的子目录，
    根据 metadata.json 中的 expected_issues 驱动断言。
    添加新数据集无需修改测试代码。
    """

    @pytest.mark.parametrize(
        "category,case_name,case_dir,metadata",
        discover_all_datasets(),
        ids=[f"{cat}/{name}" for cat, name, _, _ in discover_all_datasets()],
    )
    def test_dataset(self, category, case_name, case_dir, metadata):
        """数据集驱动测试：自动发现并验证所有数据集"""
        issues = run_checker(case_dir)

        print(f"\n数据集: {category}/{case_name}")
        print(f"检测到 {len(issues)} 个问题")
        for issue in issues:
            print(f"  - {issue.pattern}: {issue.file}:{issue.line}")

        assert metadata["cross_file"] is True, f"{case_name} 应标记为跨文件"

        expected = metadata.get("expected_issues", [])
        for exp in expected:
            pattern = exp["pattern"]
            matched = None
            for issue in issues:
                if issue.pattern == pattern:
                    if "file" in exp and issue.file != exp["file"]:
                        continue
                    matched = issue
                    break
            assert matched is not None, (
                f"{case_name}: 期望检测到 pattern={pattern}"
                + (f" file={exp['file']}" if "file" in exp else "")
                + f"，但未找到。实际检测到: {[(i.pattern, i.file) for i in issues]}"
            )

        if not expected:
            vuln_type = metadata.get("vulnerability_type", "")
            if vuln_type == "data_flow":
                null_deref_count = sum(
                    1 for i in issues if i.pattern == "possible_null_deref"
                )
                assert null_deref_count == 0, "不应该有NULL解引用误报"


@pytest.fixture
def temp_test_dir():
    """创建临时测试目录"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


class TestDirectoryScan:
    """目录扫描集成测试"""

    def test_scan_with_database(self, temp_test_dir):
        """测试：目录扫描时构建数据库"""
        from jarvis.jarvis_sec.workflow import direct_scan

        project_dir = create_test_project(
            temp_test_dir,
            "scan_with_db",
            {
                "main.c": "\n#include <stdlib.h>\n\nint main() {\n    void* p = malloc(100);\n    free(p);\n    return 0;\n}\n",
                "helper.c": "\nvoid helper_function() {\n}\n",
            },
        )

        result = direct_scan(str(project_dir), languages=["c"])

        db_path = project_dir / ".jarvis" / "jsec" / "analysis.db"
        assert db_path.exists(), "数据库文件应该创建"
        assert "summary" in result
        assert result["summary"]["scanned_files"] >= 2

    def test_database_statistics(self, temp_test_dir):
        """测试：数据库统计信息"""
        from jarvis.jarvis_sec.workflow import direct_scan

        project_dir = create_test_project(
            temp_test_dir,
            "db_stats",
            {
                "main.c": "\n#include <stdlib.h>\n\nvoid main_func() {\n    void* p = malloc(100);\n    free(p);\n}\n",
                "helper.c": "\nvoid helper_func() {\n}\n",
            },
        )

        result = direct_scan(str(project_dir), languages=["c"])

        assert "database_stats" in result
        stats = result["database_stats"]
        assert stats["files_count"] >= 2
        assert stats["symbols_count"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
