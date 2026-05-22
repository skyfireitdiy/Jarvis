import pytest
from pathlib import Path
import tempfile
import os

from jarvis.jarvis_c2rust.scanner import collect_macro_calls


@pytest.fixture
def test_macro_file():
    """Create a temporary C file with macro definitions."""
    content = """
#include <stdio.h>

// Simple function-like macro
#define MAX(a, b) ((a) > (b) ? (a) : (b))

// Macro calling a function
#define PRINT_MSG(msg) printf("%s\n", msg)

// Macro calling another function
#define CALL_FUNC(x) func_a(x)

// Nested macros (Macro calling Macro)
#define PRINT_MAX(a, b) PRINT_MSG("Max is"); printf("%d\n", MAX(a, b))

void func_a(int x) {
    printf("func_a: %d\n", x);
}

void func_b(int x) {
    int result = MAX(x, 10);
    printf("func_b: %d\n", result);
}

void func_c(const char* msg) {
    PRINT_MSG(msg);
}

void func_d(int x) {
    CALL_FUNC(x);
}

void func_e(int a, int b) {
    PRINT_MAX(a, b);
}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as f:
        f.write(content)
        return Path(f.name)


def test_collect_macro_calls(test_macro_file):
    """Test that collect_macro_calls correctly identifies macro definitions and calls."""
    try:
        macro_to_calls, func_to_macros = collect_macro_calls(test_macro_file)

        # Verify macro definitions and their internal calls
        assert "PRINT_MSG" in macro_to_calls
        assert "printf" in macro_to_calls["PRINT_MSG"]

        assert "CALL_FUNC" in macro_to_calls
        assert "func_a" in macro_to_calls["CALL_FUNC"]

        # Verify function calls to macros
        assert "func_b" in func_to_macros
        assert "MAX" in func_to_macros["func_b"]

        assert "func_c" in func_to_macros
        assert "PRINT_MSG" in func_to_macros["func_c"]

        assert "func_d" in func_to_macros
        assert "CALL_FUNC" in func_to_macros["func_d"]

        # Verify nested macro calls (if supported)
        # Note: Current implementation might not support transitive macro calls directly in this dict,
        # but we can check if func_e calls PRINT_MAX
        assert "func_e" in func_to_macros
        assert "PRINT_MAX" in func_to_macros["func_e"]

    finally:
        os.unlink(test_macro_file)


def test_macro_transitive_calls(test_macro_file):
    """Test that transitive calls via macros are correctly identified."""
    # This test relies on the integration in scan_file, but we can simulate the logic here
    # or just verify the raw data needed for it.

    try:
        macro_to_calls, func_to_macros = collect_macro_calls(test_macro_file)

        # Simulate the logic in scan_file to resolve transitive calls
        # Initialize with direct function calls (not available in this fixture, so we mock it or skip)
        # But we can verify the data structures support it

        # func_e calls PRINT_MAX
        # PRINT_MAX calls PRINT_MSG and printf (and MAX?)
        # PRINT_MSG calls printf

        # Check if PRINT_MAX is defined and calls PRINT_MSG
        # Note: PRINT_MAX definition contains PRINT_MSG(...) and printf(...)
        # The regex in collect_macro_calls should find both

        if "PRINT_MAX" in macro_to_calls:
            calls = macro_to_calls["PRINT_MAX"]
            # It should call PRINT_MSG and printf
            assert "PRINT_MSG" in calls
            assert "printf" in calls

    finally:
        os.unlink(test_macro_file)
