# -*- coding: utf-8 -*-
"""
模块管理模块
"""

import re
from pathlib import Path
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput


class ModuleManager:
    """模块管理器"""

    def __init__(self, crate_dir: Path) -> None:
        self.crate_dir = crate_dir

    def ensure_cargo_toml_bin(
        self, bin_path: str, bin_name: Optional[str] = None
    ) -> None:
        """
        在 Cargo.toml 中确保存在 [[bin]] 配置。
        - bin_path: 二进制文件的路径，相对于 crate 根目录（如 "src/bin/main.rs" 或 "src/bin/app.rs"）
        - bin_name: 二进制名称，如果为 None 则从 bin_path 推导
        """
        try:
            cargo_path = (self.crate_dir / "Cargo.toml").resolve()
            if not cargo_path.exists():
                # 如果 Cargo.toml 不存在，创建最小配置
                pkg_name = self.crate_dir.name
                content = (
                    f'[package]\nname = "{pkg_name}"\nversion = "0.1.0"\nedition = "2021"\n\n'
                    '[lib]\npath = "src/lib.rs"\n\n'
                )
                cargo_path.write_text(content, encoding="utf-8")
                PrettyOutput.auto_print(
                    f"✅ [c2rust-transpiler][cargo] 已创建 Cargo.toml: {cargo_path}"
                )

            # 读取现有内容
            txt = cargo_path.read_text(encoding="utf-8", errors="replace")

            # 从 bin_path 推导 bin_name
            if bin_name is None:
                # 从路径中提取文件名（去掉 .rs 后缀）
                bin_path_clean = bin_path.replace("\\", "/")
                if bin_path_clean.startswith("src/bin/"):
                    bin_name = bin_path_clean[len("src/bin/") :]
                    if bin_name.endswith(".rs"):
                        bin_name = bin_name[:-3]
                else:
                    # 如果路径不是 src/bin/ 格式，使用默认名称
                    bin_name = self.crate_dir.name

            # 检查是否已存在相同的 [[bin]] 配置
            # 匹配 [[bin]] 块，查找 name 和 path
            bin_pattern = re.compile(
                r"\[\[bin\]\]\s*\n(?:[^\[]*(?:\n[^\[]*)*?)(?=\[\[bin\]\]|\[\[|\[|$)",
                re.MULTILINE,
            )
            existing_bins = bin_pattern.findall(txt)

            # 检查是否已存在相同 path 的 bin
            for bin_block in existing_bins:
                # 检查 path 字段
                path_match = re.search(r'path\s*=\s*["\']([^"\']+)["\']', bin_block)
                if path_match and path_match.group(1) == bin_path:
                    # 已存在相同路径的 bin 配置
                    return
                # 检查 name 字段
                name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', bin_block)
                if name_match and name_match.group(1) == bin_name:
                    # 已存在相同名称的 bin，检查路径是否相同
                    if path_match and path_match.group(1) == bin_path:
                        # 完全相同的配置，无需添加
                        return
                    # 名称相同但路径不同，可能需要更新，但为了安全起见，我们仍然添加新的配置
                    # （因为可能存在多个同名但不同路径的 bin）

            # 添加 [[bin]] 配置
            bin_config = f'\n[[bin]]\nname = "{bin_name}"\npath = "{bin_path}"\n'

            # 在文件末尾添加（如果已有其他配置，在适当位置插入）
            # 优先在 [lib] 之后添加，如果不存在则在 [dependencies] 之前添加
            lib_match = re.search(r"(?m)^\s*\[lib\]\s*$", txt)
            deps_match = re.search(r"(?m)^\s*\[dependencies\]\s*$", txt)

            if lib_match:
                # 在 [lib] 块之后添加
                insert_pos = txt.find("\n", lib_match.end())
                if insert_pos == -1:
                    insert_pos = len(txt)
                # 找到 [lib] 块的结束位置
                next_section = re.search(r"(?m)^\s*\[", txt[insert_pos:])
                if next_section:
                    insert_pos = insert_pos + next_section.start()
                new_txt = txt[:insert_pos] + bin_config + txt[insert_pos:]
            elif deps_match:
                # 在 [dependencies] 之前添加
                insert_pos = deps_match.start()
                new_txt = txt[:insert_pos] + bin_config + txt[insert_pos:]
            else:
                # 在文件末尾添加
                new_txt = txt.rstrip() + bin_config

            cargo_path.write_text(new_txt, encoding="utf-8")
            PrettyOutput.auto_print(
                f"✅ [c2rust-transpiler][cargo] 已在 Cargo.toml 中添加 [[bin]] 配置: name={bin_name}, path={bin_path}"
            )
        except Exception as e:
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-transpiler][cargo] 更新 Cargo.toml 失败: {e}"
            )

    def ensure_top_level_pub_mod(self, mod_name: str) -> None:
        """
        在 src/lib.rs 中确保存在 `pub mod <mod_name>;`
        - 如已存在 `pub mod`，不做改动
        - 如存在 `mod <mod_name>;`，升级为 `pub mod <mod_name>;`
        - 如都不存在，则在文件末尾追加一行 `pub mod <mod_name>;`
        - 最小改动，不覆盖其他内容
        """
        try:
            if not mod_name or mod_name in ("lib", "main", "mod", "bin"):
                return
            lib_rs = (self.crate_dir / "src" / "lib.rs").resolve()
            lib_rs.parent.mkdir(parents=True, exist_ok=True)
            if not lib_rs.exists():
                try:
                    lib_rs.write_text(
                        "// Auto-generated by c2rust transpiler\n", encoding="utf-8"
                    )
                    PrettyOutput.auto_print(
                        f"✅ [c2rust-transpiler][mod] 已创建 src/lib.rs: {lib_rs}"
                    )
                except Exception:
                    return
            txt = lib_rs.read_text(encoding="utf-8", errors="replace")
            pub_pat = re.compile(rf"(?m)^\s*pub\s+mod\s+{re.escape(mod_name)}\s*;\s*$")
            mod_pat = re.compile(rf"(?m)^\s*mod\s+{re.escape(mod_name)}\s*;\s*$")
            if pub_pat.search(txt):
                return
            if mod_pat.search(txt):
                # 升级为 pub mod（保留原缩进）
                def _repl(m: re.Match) -> str:
                    line = m.group(0)
                    match = re.match(r"^(\s*)", line)
                    ws = match.group(1) if match else ""
                    return f"{ws}pub mod {mod_name};"

                new_txt = mod_pat.sub(_repl, txt, count=1)
            else:
                new_txt = txt.rstrip() + f"\npub mod {mod_name};\n"
            lib_rs.write_text(new_txt, encoding="utf-8")
            PrettyOutput.auto_print(
                f"✅ [c2rust-transpiler][mod] updated src/lib.rs: ensured pub mod {mod_name}"
            )
        except Exception:
            # 保持稳健，失败不阻塞主流程
            pass

    def ensure_mod_rs_decl(self, dir_path: Path, child_mod: str) -> None:
        """
        在 dir_path/mod.rs 中确保存在 `pub mod <child_mod>;`
        - 如存在 `mod <child_mod>;` 则升级为 `pub mod <child_mod>;`
        - 如均不存在则在文件末尾追加 `pub mod <child_mod>;`
        - 最小改动，不覆盖其他内容
        """
        try:
            if not child_mod or child_mod in ("lib", "main", "mod", "bin"):
                return
            mod_rs = (dir_path / "mod.rs").resolve()
            mod_rs.parent.mkdir(parents=True, exist_ok=True)
            if not mod_rs.exists():
                try:
                    mod_rs.write_text(
                        "// Auto-generated by c2rust transpiler\n", encoding="utf-8"
                    )
                    PrettyOutput.auto_print(
                        f"✅ [c2rust-transpiler][mod] 已创建 {mod_rs}"
                    )
                except Exception:
                    return
            txt = mod_rs.read_text(encoding="utf-8", errors="replace")
            pub_pat = re.compile(rf"(?m)^\s*pub\s+mod\s+{re.escape(child_mod)}\s*;\s*$")
            mod_pat = re.compile(rf"(?m)^\s*mod\s+{re.escape(child_mod)}\s*;\s*$")
            if pub_pat.search(txt):
                return
            if mod_pat.search(txt):
                # 升级为 pub mod（保留原缩进）
                def _repl(m: re.Match) -> str:
                    line = m.group(0)
                    match = re.match(r"^(\s*)", line)
                    ws = match.group(1) if match else ""
                    return f"{ws}pub mod {child_mod};"

                new_txt = mod_pat.sub(_repl, txt, count=1)
            else:
                new_txt = txt.rstrip() + f"\npub mod {child_mod};\n"
            mod_rs.write_text(new_txt, encoding="utf-8")
            PrettyOutput.auto_print(
                f"✅ [c2rust-transpiler][mod] updated {mod_rs}: ensured pub mod {child_mod}"
            )
        except Exception:
            pass

    def ensure_mod_chain_for_module(self, module: str) -> None:
        """
        根据目标模块文件，补齐从该文件所在目录向上的 mod.rs 声明链：
        - 对于 src/foo/bar.rs：在 src/foo/mod.rs 确保 `pub mod bar;`
          并在上层 src/mod.rs（不修改）改为在 src/lib.rs 确保 `pub mod foo;`（已由顶层函数处理）
        - 对于 src/foo/bar/mod.rs：在 src/foo/mod.rs 确保 `pub mod bar;`
        - 对多级目录，逐级在上层 mod.rs 确保对子目录的 `pub mod <child>;`
        """
        try:
            mp = Path(module)
            base = mp
            if not mp.is_absolute():
                base = (self.crate_dir / module).resolve()
            crate_root = self.crate_dir.resolve()
            # 必须在 crate/src 下
            rel = base.relative_to(crate_root)
            rel_s = str(rel).replace("\\", "/")
            if not rel_s.startswith("src/"):
                return
            # 计算起始目录与首个子模块名
            inside = rel_s[len("src/") :].strip("/")
            if not inside:
                return
            parts = [p for p in inside.split("/") if p]  # 过滤空字符串
            # 特殊处理：如果路径包含 bin/，不要生成 mod 声明
            if "bin" in parts:
                return
            if parts[-1].endswith(".rs"):
                if parts[-1] in ("lib.rs", "main.rs"):
                    return
                child = parts[-1][:-3]  # 去掉 .rs
                # 过滤掉 "mod" 和 "bin" 关键字
                if child in ("mod", "bin"):
                    return
                if len(parts) > 1:
                    start_dir = crate_root / "src" / "/".join(parts[:-1])
                else:
                    start_dir = crate_root / "src"
                # 确保 start_dir 在 crate/src 下
                try:
                    start_dir_rel = start_dir.relative_to(crate_root)
                    if not str(start_dir_rel).replace("\\", "/").startswith("src/"):
                        return
                except ValueError:
                    return
                # 在当前目录的 mod.rs 确保 pub mod <child>
                if start_dir.name != "src":
                    self.ensure_mod_rs_decl(start_dir, child)
                # 向上逐级确保父目录对当前目录的 pub mod 声明
                cur_dir = start_dir
            else:
                # 末尾为目录（mod.rs 情况）：确保父目录对该目录 pub mod
                if parts:
                    cur_dir = crate_root / "src" / "/".join(parts)
                    # 确保 cur_dir 在 crate/src 下
                    try:
                        cur_dir_rel = cur_dir.relative_to(crate_root)
                        if not str(cur_dir_rel).replace("\\", "/").startswith("src/"):
                            return
                    except ValueError:
                        return
                else:
                    return
            # 逐级向上到 src 根（不修改 src/mod.rs，顶层由 lib.rs 公开）
            while True:
                parent = cur_dir.parent
                if not parent.exists():
                    break
                # 确保不超过 crate 根目录
                try:
                    parent.relative_to(crate_root)
                except ValueError:
                    # parent 不在 crate_root 下，停止向上遍历
                    break
                if parent.name == "src":
                    # 顶层由 _ensure_top_level_pub_mod 负责
                    break
                # 在 parent/mod.rs 确保 pub mod <cur_dir.name>
                # 确保 parent 在 crate/src 下
                # 过滤掉 "mod" 和 "bin" 关键字
                if cur_dir.name in ("mod", "bin"):
                    cur_dir = parent
                    continue
                try:
                    parent_rel = parent.relative_to(crate_root)
                    if str(parent_rel).replace("\\", "/").startswith("src/"):
                        self.ensure_mod_rs_decl(parent, cur_dir.name)
                except (ValueError, Exception):
                    # parent 不在 crate/src 下，跳过
                    break
                cur_dir = parent
        except Exception:
            pass

    def module_file_to_crate_path(self, module: str) -> str:
        """
        将模块文件路径转换为 crate 路径前缀：
        - src/lib.rs -> crate
        - src/foo/mod.rs -> crate::foo
        - src/foo/bar.rs -> crate::foo::bar
        支持绝对路径：若 module 为绝对路径且位于 crate 根目录下，会自动转换为相对路径再解析；
        其它（无法解析为 crate/src 下的路径）统一返回 'crate'
        """
        mod = str(module).strip()
        # 若传入绝对路径且在 crate_dir 下，转换为相对路径以便后续按 src/ 前缀解析
        try:
            mp = Path(mod)
            if mp.is_absolute():
                try:
                    rel = mp.resolve().relative_to(self.crate_dir.resolve())
                    mod = str(rel).replace("\\", "/")
                except Exception:
                    # 绝对路径不在 crate_dir 下，保持原样
                    pass
        except Exception:
            pass
        # 规范化 ./ 前缀
        if mod.startswith("./"):
            mod = mod[2:]
        # 仅处理位于 src/ 下的模块文件
        if not mod.startswith("src/"):
            return "crate"
        p = mod[len("src/") :]
        if p.endswith("mod.rs"):
            p = p[: -len("mod.rs")]
        elif p.endswith(".rs"):
            p = p[: -len(".rs")]
        p = p.strip("/")
        return "crate" if not p else "crate::" + p.replace("/", "::")
