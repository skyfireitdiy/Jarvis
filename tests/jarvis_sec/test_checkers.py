# -*- coding: utf-8 -*-
"""
jarvis_sec 基础单元测试（阶段一）

覆盖点：
- C/C++ 启发式检查器：不安全API、内存管理、缓冲区操作、错误处理
- Rust 启发式检查器：unsafe/原始指针/unwrap/FFI等
- workflow.direct_scan 与 checkers 集成
- report 聚合与 Markdown 渲染

运行：
- 使用 pytest 执行：pytest -q
"""

from __future__ import annotations

from pathlib import Path


from jarvis.jarvis_sec.checkers import (
    analyze_c_cpp_text,
    analyze_rust_text,
)
from jarvis.jarvis_sec.workflow import direct_scan, format_markdown_report
from jarvis.jarvis_sec.report import build_json_and_markdown


def test_c_checker_detects_multiple_categories():
    src = r"""
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

void foo(char *dst, const char *src) {
    // 不安全API（应命中）
    strcpy(dst, src);

    // 边界操作（应命中），且长度来源可疑
    size_t n = strlen(src);
    memcpy(dst, src, n);

    // realloc 直接覆盖（应命中）
    char *p = (char*)malloc(10);
    p = realloc(p, 20);
    if (!dst) { printf("unrelated"); } // 无关检查

    // 分配后未检查 NULL（应命中）
    char *q = (char*)malloc(100);
    q[0] = 'x'; // 使用 q

    // I/O 返回值未检查（应命中）
    FILE *fp = fopen("x.txt", "r");
    char buf[32];
    fread(buf, 1, 10, fp);
    fclose(fp);

    // UAF 线索（应命中）
    char *z = (char*)malloc(16);
    free(z);
    printf("%p\n", z); // 使用 z
}
"""
    issues = analyze_c_cpp_text("sample.c", src)
    cats = {i.category for i in issues}
    assert "unsafe_api" in cats, f"未检测到不安全API，实际类别：{cats}"
    assert "buffer_overflow" in cats, f"未检测到缓冲区边界问题，实际类别：{cats}"
    assert "memory_mgmt" in cats, f"未检测到内存管理问题，实际类别：{cats}"
    assert "error_handling" in cats, f"未检测到错误处理问题，实际类别：{cats}"
    # 至少有若干问题
    assert len(issues) >= 5


def test_rust_checker_detects_core_patterns():
    src = r"""
pub fn risky(p: *mut u8) {
    // 原始指针
    let _ = p;
    // unsafe 块
    unsafe {
        let _v = std::ptr::read(p);
    }
    // unwrap 滥用
    let s = std::fs::read_to_string("foo.txt").unwrap();
}

extern "C" {
    fn c_func(p: *mut u8);
}

unsafe impl Send for MyType {}
"""
    issues = analyze_rust_text("src/lib.rs", src)
    cats = {i.category for i in issues}
    assert "unsafe_usage" in cats, f"未检测到 unsafe 使用，实际类别：{cats}"
    assert "error_handling" in cats, f"未检测到 unwrap 错误处理问题，实际类别：{cats}"
    assert "ffi" in cats, f"未检测到 FFI 边界问题，实际类别：{cats}"
    assert "concurrency" in cats, f"未检测到并发不安全实现问题，实际类别：{cats}"
    assert len(issues) >= 4


def test_direct_scan_integration_with_temp_files(tmp_path: Path):
    # 构造临时项目结构
    project = tmp_path / "proj"
    project.mkdir()
    # C 文件
    (project / "a.c").write_text(
        "#include <string.h>\nvoid f(char *d, const char *s){ strcpy(d,s); }",
        encoding="utf-8",
    )
    # Rust 文件
    (project / "lib.rs").write_text(
        'pub fn g(){ let _ = "x".to_string().unwrap(); }',
        encoding="utf-8",
    )

    result = direct_scan(str(project))
    assert isinstance(result, dict)
    summary = result.get("summary", {})
    issues = result.get("issues", [])
    assert summary.get("scanned_files", 0) >= 2
    assert summary.get("total", 0) >= 2
    assert any(i.get("language") == "c/cpp" for i in issues), "未包含 C/C++ 问题"
    assert any(i.get("language") == "rust" for i in issues), "未包含 Rust 问题"



def test_direct_scan_and_format_markdown(tmp_path: Path):
    # 构造临时项目
    project = tmp_path / "proj2"
    project.mkdir()
    (project / "b.c").write_text(
        "#include <stdio.h>\nvoid f(){ char b[4]; sprintf(b, \"%s\", \"x\"); }",
        encoding="utf-8",
    )
    result = direct_scan(str(project))
    text = format_markdown_report(result)
    # 验证 Markdown 格式报告
    assert text.startswith("# Jarvis 安全问题分析报告（直扫基线）")
    assert "- 扫描根目录:" in text
    assert "- 扫描文件数:" in text
    assert "- 检出问题总数:" in text
    assert "## 统计概览" in text
    assert "## 详细问题" in text


def test_c_checker_new_rules_batch():
    src = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void demo() {
    char fmtbuf[32];
    // 格式化字符串非常量（应命中 format_string）
    printf(fmtbuf);

    // 不安全临时文件（应命中 insecure_tmpfile）
    char tname[L_tmpnam];
    tmpnam(tname);

    // 命令执行参数非常量（应命中 command_exec）
    char cmd[16] = "ls";
    system(cmd);

    // scanf %s 未限制宽度（应命中 scanf_%s_no_width）
    char s[8];
    scanf("%s", s);

    // 分配大小包含乘法且未使用 sizeof（应命中 alloc_size_overflow）
    size_t n = 4, m = 256;
    char *p = (char*)malloc(n * m);
    (void)p;
}
"""
    issues = analyze_c_cpp_text("demo.c", src)
    patterns = {i.pattern for i in issues}
    expected = {
        "format_string",
        "insecure_tmpfile",
        "command_exec",
        "scanf_%s_no_width",
        "alloc_size_overflow",
    }
    missing = expected - patterns
    assert not missing, f"新规则未全部命中，缺少: {missing}; 实际: {patterns}"


def test_report_build_json_with_meta():
    issues = [
        {
            "language": "c/cpp",
            "category": "unsafe_api",
            "pattern": "strcpy",
            "file": "src/foo.c",
            "line": 1,
            "evidence": "strcpy(d, s);",
            "description": "不安全API",
            "suggestion": "使用安全替代",
            "confidence": 0.9,
            "severity": "high",
        }
    ]
    meta = [
        {
            "task_id": "T1",
            "workspace_restore": {
                "performed": True,
                "changed_files_count": 2,
                "action": "git checkout -- .",
            },
        }
    ]
    text = build_json_and_markdown(issues, scanned_root="/tmp", scanned_files=1, meta=meta)
    # 现在仅返回 Markdown，检查关键内容
    assert text.startswith("# 安全问题分析报告（聚合）")
    assert "- 扫描根目录: /tmp" in text
    assert "- 扫描文件数: 1" in text
    assert "## 统计概览" in text