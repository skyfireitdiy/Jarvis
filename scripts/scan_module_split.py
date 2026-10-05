#!/usr/bin/env python3
"""模块单例分裂扫描器（static analysis）。

背景：Python 中「同一个物理 .py 文件」若被以两个不同的模块名导入
（如 jarvis.jarvis_tools.timer 与裸顶层名 timer），会被当作两个不同的模块对象，
导致模块级单例 / 缓存分裂（典型症状：A 处创建的任务/状态，B 处看不到、无法操作）。

触发条件：某目录被动态加入 sys.path（如 sys.path.insert(0, parent_dir)），
使该目录下的文件既能按「裸文件名」导入，又能按「包路径」导入。

本脚本静态扫描：
  1) 找出所有被动态插入 sys.path 的目录；
  2) 对每个这样的目录，检查其中的 .py 文件是否同时被「包路径」与「裸名」引用；
  3) 命中即报出该文件及其两个模块名。

用法：
    python3 scripts/scan_module_split.py [SRC]
    SRC 默认为本仓库 src 目录。

退出码：0=未发现风险；1=发现潜在单例分裂点。

另有 --selftest 参数：用内置的合成缺陷项目验证检测逻辑本身可用。
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
import tempfile
from collections import defaultdict


def collect(src: str):
    """返回 (module_to_file, imported_names, dynamic_bare_imports, import_by_file)。

    - module_to_file: 包路径 -> 文件绝对路径
    - imported_names: 全代码库所有被引用的模块名（含裸名）
    - dynamic_bare_imports: 动态导入调用点列表 [(file, module_name)]，
      来自 importlib.import_module("...") / __import__("...")，module_name 为字面量
    - import_by_file: 文件 -> 该文件引用的模块名集合
    """
    module_to_file = {}
    for root, _dirs, files in os.walk(src):
        for f in files:
            if not f.endswith(".py"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src)
            mod = rel[:-3].replace(os.sep, ".")
            module_to_file[mod] = full

    imported = set()
    import_by_file = defaultdict(set)
    dynamic_bare_imports = []

    for root, _dirs, files in os.walk(src):
        for f in files:
            if not f.endswith(".py"):
                continue
            full = os.path.join(root, f)
            try:
                with open(full, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        imported.add(a.name)
                        import_by_file[full].add(a.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module)
                        import_by_file[full].add(node.module)
                elif isinstance(node, ast.Call):
                    fn = node.func
                    # importlib.import_module("...") / __import__("...")
                    if (
                        isinstance(fn, ast.Attribute)
                        and fn.attr == "import_module"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        name = node.args[0].value
                        imported.add(name)
                        import_by_file[full].add(name)
                        if "." not in name:  # 裸名动态导入
                            dynamic_bare_imports.append((full, name))
                    elif (
                        isinstance(fn, ast.Name)
                        and fn.id == "__import__"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        name = node.args[0].value
                        imported.add(name)
                        import_by_file[full].add(name)
                        if "." not in name:
                            dynamic_bare_imports.append((full, name))

    return module_to_file, imported, dynamic_bare_imports, import_by_file


def scan(src: str):
    """返回风险列表 [(file_path, canonical_package_path, bare_stem, sites)]。

    检测逻辑：同一物理 .py 文件若被「包路径」与「裸名」两种方式导入，即为
    模块单例分裂点。裸名导入必须是**动态**的
    `importlib.import_module("X")` / `__import__("X")`（X 无点号）——
    因为只有动态导入配合 sys.path 动态插入目录时，才会把「包内文件」按
    裸顶层名导入，从而产生与包路径不同的第二个模块对象（这正是
    register_tool_by_file 旧实现的机制）。

    静态 `import X` 不会造成分裂：若 X 不是真实顶层模块，静态导入本身就会
    ImportError；若 X 是真实顶层模块，则与包内文件不是同一个物理文件。
    因此只以「动态裸名导入」为风险信号，避免把不同包同名文件误判为分裂点。
    """
    module_to_file, imported, dynamic_bare_imports, _ = collect(src)

    # 动态裸名导入的调用点：module_name -> 调用文件列表
    dynamic_by_stem = defaultdict(list)
    for src_file, name in dynamic_bare_imports:
        dynamic_by_stem[name].append(src_file)

    risks = []
    for canon, full in module_to_file.items():
        if "." not in canon:
            continue  # 顶层文件（裸名即其规范名），不存在分裂
        stem = os.path.splitext(os.path.basename(full))[0]
        # 仅当该文件被「动态裸名」导入（真正可能产生第二个模块对象的路径）
        # 且同时被其规范包路径导入时，才判定为分裂点。
        if stem in dynamic_by_stem and canon in imported:
            risks.append((full, canon, stem, tuple(dynamic_by_stem.get(stem, []))))
    return risks


def selftest() -> int:
    """构造一个含缺陷的合成项目，验证扫描能命中；并验证无误报。"""
    tmp = tempfile.mkdtemp()
    pkg = os.path.join(tmp, "pkg")
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "__init__.py"), "w") as f:
        f.write("")
    # 缺陷文件：pkg/timer.py，既被包路径导入，又被动态裸名导入
    with open(os.path.join(pkg, "timer.py"), "w") as f:
        f.write("_mgr=None\ndef get_timer_manager():\n    return _mgr\n")
    with open(os.path.join(tmp, "a.py"), "w") as f:
        f.write("from pkg.timer import get_timer_manager\n")
    with open(os.path.join(tmp, "b.py"), "w") as f:
        f.write(
            "import importlib\n"
            "import sys\n"
            "sys.path.insert(0, 'pkg')\n"
            "importlib.import_module('timer')\n"
        )
    # 对照：另一包的同名文件 events.py，仅被包路径引用，不应误报
    pkg2 = os.path.join(tmp, "pkg2")
    os.makedirs(pkg2, exist_ok=True)
    with open(os.path.join(pkg2, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(pkg2, "events.py"), "w") as f:
        f.write("EVENT = 1\n")
    with open(os.path.join(tmp, "c.py"), "w") as f:
        f.write("from pkg2.events import EVENT\n")

    risks = scan(tmp)
    if not risks:
        print("❌ selftest 失败：未检测到合成缺陷")
        return 1
    for full, canon, stem, _sites in sorted(set(risks)):
        print(
            f"✅ selftest 命中：{full}\n   规范包路径: {canon}  同时被裸名引用: {stem}"
        )
    # 确认只命中缺陷文件，没有把 pkg2/events.py 误报
    if any("pkg2" in r[0] for r in risks):
        print("❌ selftest 失败：误报了对照文件 pkg2/events.py")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="模块单例分裂静态扫描器")
    parser.add_argument(
        "src", nargs="?", default=None, help="要扫描的源码根目录（默认本仓库 src）"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="运行内置自检（验证检测逻辑）"
    )
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    src = args.src
    if src is None:
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(os.path.dirname(here), "src")
    if not os.path.isdir(src):
        print(f"❌ 目录不存在: {src}")
        return 1

    risks = scan(src)
    if not risks:
        print("✅ 未发现模块单例分裂点")
        return 0
    print(f"⚠️  发现 {len(set(risks))} 处潜在模块单例分裂点：")
    for full, canon, stem, sites in sorted(set(risks)):
        print(f"\n  {full}")
        print(f"    规范包路径: {canon}  同时被裸名引用: {stem}")
        if sites:
            print(f"    动态裸名导入调用点: {', '.join(sites)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
