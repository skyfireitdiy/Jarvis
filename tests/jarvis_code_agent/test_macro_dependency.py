import pytest

from jarvis.jarvis_code_agent.code_analyzer.languages.c_cpp_language import (
    CDependencyAnalyzer,
    CppDependencyAnalyzer,
)


@pytest.fixture
def test_project(tmp_path):
    """Create a temporary C project with macro dependencies."""
    # Create header file with macro definition
    header_content = """
#ifndef UTILS_H
#define UTILS_H

#define PRINT_MSG(msg) printf("%s\\n", msg)

#endif
"""
    header_file = tmp_path / "utils.h"
    header_file.write_text(header_content)

    # Create source file using the macro
    source_content = """
#include <stdio.h>
#include "utils.h"

void test_func() {
    PRINT_MSG("Hello");
}
"""
    source_file = tmp_path / "main.c"
    source_file.write_text(source_content)

    return tmp_path


def test_c_macro_dependency(test_project):
    """Test that macro dependencies are detected in C files."""
    analyzer = CDependencyAnalyzer()
    graph = analyzer.build_dependency_graph(str(test_project))

    main_c = str(test_project / "main.c")
    utils_h = str(test_project / "utils.h")

    # Check if main.c depends on utils.h
    deps = graph.get_dependencies(main_c)
    assert utils_h in deps, (
        f"Expected {utils_h} in dependencies of {main_c}, got {deps}"
    )


def test_cpp_macro_dependency(test_project):
    """Test that macro dependencies are detected in C++ files."""
    # Create C++ source file
    cpp_content = """
#include <iostream>
#include "utils.h"

void cpp_func() {
    PRINT_MSG("Hello from C++");
}
"""
    cpp_file = test_project / "main.cpp"
    cpp_file.write_text(cpp_content)

    analyzer = CppDependencyAnalyzer()
    graph = analyzer.build_dependency_graph(str(test_project))

    main_cpp = str(test_project / "main.cpp")
    utils_h = str(test_project / "utils.h")

    # Check if main.cpp depends on utils.h
    deps = graph.get_dependencies(main_cpp)
    assert utils_h in deps, (
        f"Expected {utils_h} in dependencies of {main_cpp}, got {deps}"
    )
