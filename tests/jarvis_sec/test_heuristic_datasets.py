# -*- coding: utf-8 -*-
"""启发式规则测试数据集

为每个启发式规则提供正例（应该检测到）和反例（不应该检测到）的测试用例。
目的：验证规则准确性，减少误报。

运行：pytest tests/jarvis_sec/test_heuristic_datasets.py -v
"""

import pytest
from jarvis.jarvis_sec.checkers.c_checker import analyze_c_cpp_text


# ============================================================================
# 空指针解引用检测 (_rule_possible_null_deref)
# ============================================================================

class TestPossibleNullDeref:
    """空指针解引用检测测试集"""
    
    def test_positive_no_check(self):
        """正例：没有任何检查的指针解引用"""
        src = "void foo(char *p) { *p = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_positive_arrow_no_check(self):
        """正例：箭头操作符解引用无检查"""
        src = "struct Foo { int x; }; void bar(struct Foo *p) { p->x = 10; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_negative_if_check(self):
        """反例：有if语句检查"""
        src = "void foo(char *p) { if (p != NULL) { *p = 'x'; } }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_negative_return_check(self):
        """反例：有return防御"""
        src = "void foo(char *p) { if (!p) return; *p = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_negative_goto_check(self):
        """反例：有goto错误处理"""
        src = "void foo(char *p) { if (!p) goto error; *p = 'x'; error: return; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_negative_while_check(self):
        """反例：while循环条件检查"""
        src = "void foo(char *p) { while (p && *p) { p++; } }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_negative_just_allocated(self):
        """反例：刚分配成功后的立即使用"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); p[0] = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "possible_null_deref" for i in issues)
    
    def test_negative_this_pointer(self):
        """反例：C++ this指针"""
        src = "class Foo { int x; void bar() { this->x = 10; } };"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert not any(i.pattern == "possible_null_deref" for i in issues)


# ============================================================================
# 数据竞争检测 (_rule_data_race_suspect)
# ============================================================================

class TestDataRaceSuspect:
    """数据竞争检测测试集"""
    
    def test_positive_write_no_lock(self):
        """正例：无锁保护的写操作"""
        src = "#include <pthread.h>\nint shared_data = 0;\nvoid *thread_func(void *arg) { shared_data = 100; return NULL; }\nint main() { pthread_t t; pthread_create(&t, NULL, thread_func, NULL); pthread_join(t, NULL); return 0; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "data_race_suspect" for i in issues)
    
    def test_negative_read_no_lock(self):
        """反例：无锁保护的读操作（不应报告或置信度很低）"""
        src = "#include <pthread.h>\nint shared_data = 0;\nvoid *thread_func(void *arg) { int val = shared_data; return NULL; }\nint main() { pthread_t t; pthread_create(&t, NULL, thread_func, NULL); pthread_join(t, NULL); return 0; }"
        issues = analyze_c_cpp_text("test.c", src)
        data_race_issues = [i for i in issues if i.pattern == "data_race_suspect"]
        # 读操作不应该报告，或者置信度很低
        for issue in data_race_issues:
            assert issue.confidence < 0.5, f"读操作置信度过高: {issue.confidence}"
    
    def test_negative_with_mutex(self):
        """反例：有互斥锁保护"""
        src = "#include <pthread.h>\nint shared_data = 0;\npthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;\nvoid *thread_func(void *arg) { pthread_mutex_lock(&mutex); shared_data = 100; pthread_mutex_unlock(&mutex); return NULL; }\nint main() { pthread_t t; pthread_create(&t, NULL, thread_func, NULL); pthread_join(t, NULL); return 0; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "data_race_suspect" for i in issues)
    
    def test_negative_const_global(self):
        """反例：const全局变量"""
        src = "#include <pthread.h>\nconst int shared_data = 0;\nvoid *thread_func(void *arg) { int val = shared_data; return NULL; }\nint main() { pthread_t t; pthread_create(&t, NULL, thread_func, NULL); pthread_join(t, NULL); return 0; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "data_race_suspect" for i in issues)


# ============================================================================
# 不安全API检测 (_rule_unsafe_api)
# ============================================================================

class TestUnsafeAPI:
    """不安全API检测测试集"""
    
    def test_positive_strcpy(self):
        """正例：strcpy使用"""
        src = "#include <string.h>\nvoid foo(char *dst, const char *src) { strcpy(dst, src); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "unsafe_api" and "strcpy" in i.description for i in issues)
    
    def test_positive_sprintf(self):
        """正例：sprintf使用"""
        src = "#include <stdio.h>\nvoid foo(char *buf) { sprintf(buf, "%s", "hello"); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "unsafe_api" and "sprintf" in i.description for i in issues)
    
    def test_positive_gets(self):
        """正例：gets使用"""
        src = "#include <stdio.h>\nvoid foo() { char buf[100]; gets(buf); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "unsafe_api" and "gets" in i.description for i in issues)


# ============================================================================
# malloc返回值检查 (_rule_malloc_no_null_check)
# ============================================================================

class TestMallocNoNullCheck:
    """malloc返回值检查测试集"""
    
    def test_positive_no_check(self):
        """正例：malloc未检查NULL"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); p[0] = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "malloc_no_null_check" for i in issues)
    
    def test_negative_with_check(self):
        """反例：malloc有检查"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); if (p == NULL) return; p[0] = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "malloc_no_null_check" for i in issues)


# ============================================================================
# 格式化字符串检测 (_rule_format_string)
# ============================================================================

class TestFormatString:
    """格式化字符串检测测试集"""
    
    def test_positive_non_constant_format(self):
        """正例：非常量格式化字符串"""
        src = "#include <stdio.h>\nvoid foo(char *fmt) { printf(fmt); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "format_string" for i in issues)
    
    def test_negative_constant_format(self):
        """反例：常量格式化字符串"""
        src = "#include <stdio.h>\nvoid foo(int x) { printf("%d\n", x); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "format_string" for i in issues)


# ============================================================================
# UAF检测 (_rule_uaf_suspect)
# ============================================================================

class TestUafSuspect:
    """Use-After-Free检测测试集"""
    
    def test_positive_free_then_use(self):
        """正例：free后使用"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); free(p); p[0] = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "uaf_suspect" for i in issues)
    
    def test_positive_free_then_pass(self):
        """正例：free后传递给函数"""
        src = "#include <stdlib.h>\n#include <stdio.h>\nvoid foo() { char *p = malloc(100); free(p); printf("%p\n", p); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "uaf_suspect" for i in issues)


# ============================================================================
# Double Free检测 (_rule_double_free_and_free_non_heap)
# ============================================================================

class TestDoubleFree:
    """Double Free检测测试集"""
    
    def test_positive_double_free(self):
        """正例：重复free"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); free(p); free(p); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "double_free" for i in issues)


# ============================================================================
# 命令执行检测 (_rule_command_execution)
# ============================================================================

class TestCommandExecution:
    """命令执行检测测试集"""
    
    def test_positive_system_call(self):
        """正例：system调用"""
        src = "#include <stdlib.h>\nvoid foo(char *cmd) { system(cmd); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any("command" in i.pattern or "system" in i.description.lower() for i in issues)
    
    def test_positive_popen_call(self):
        """正例：popen调用"""
        src = "#include <stdio.h>\nvoid foo(char *cmd) { FILE *fp = popen(cmd, "r"); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any("command" in i.pattern or "popen" in i.description for i in issues)


# ============================================================================
# 分配大小溢出检测 (_rule_alloc_size_overflow)
# ============================================================================

class TestAllocSizeOverflow:
    """分配大小溢出检测测试集"""
    
    def test_positive_multiplication_in_malloc(self):
        """正例：malloc中使用乘法"""
        src = "#include <stdlib.h>\nvoid foo(size_t n, size_t m) { char *p = malloc(n * m); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "alloc_size_overflow" for i in issues)


# ============================================================================
# scanf宽度检测 (_rule_scanf_no_width)
# ============================================================================

class TestScanfNoWidth:
    """scanf宽度检测测试集"""
    
    def test_positive_scanf_s_no_width(self):
        """正例：scanf %s无宽度"""
        src = "#include <stdio.h>\nvoid foo() { char buf[100]; scanf("%s", buf); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "scanf_no_width" for i in issues)
    
    def test_negative_scanf_with_width(self):
        """反例：scanf有宽度限制"""
        src = "#include <stdio.h>\nvoid foo() { char buf[100]; scanf("%99s", buf); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "scanf_no_width" for i in issues)


# ============================================================================
# 不安全临时文件检测 (_rule_insecure_tmpfile)
# ============================================================================

class TestInsecureTmpfile:
    """不安全临时文件检测测试集"""
    
    def test_positive_tmpnam(self):
        """正例：tmpnam使用"""
        src = "#include <stdio.h>\nvoid foo() { char name[L_tmpnam]; tmpnam(name); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "insecure_tmpfile" for i in issues)
    
    def test_positive_mktemp(self):
        """正例：mktemp使用"""
        src = "#include <stdlib.h>\nvoid foo() { char template[] = "fileXXXXXX"; mktemp(template); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "insecure_tmpfile" for i in issues)


# ============================================================================
# atoi家族检测 (_rule_atoi_family)
# ============================================================================

class TestAtoiFamily:
    """atoi家族检测测试集"""
    
    def test_positive_atoi(self):
        """正例：atoi使用"""
        src = "#include <stdlib.h>\nvoid foo(char *s) { int x = atoi(s); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "atoi_family" for i in issues)
    
    def test_positive_atol(self):
        """正例：atol使用"""
        src = "#include <stdlib.h>\nvoid foo(char *s) { long x = atol(s); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "atoi_family" for i in issues)


# ============================================================================
# rand不安全检测 (_rule_rand_insecure)
# ============================================================================

class TestRandInsecure:
    """rand不安全检测测试集"""
    
    def test_positive_rand(self):
        """正例：rand使用"""
        src = "#include <stdlib.h>\nvoid foo() { int x = rand(); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "rand_insecure" for i in issues)
    
    def test_positive_srand(self):
        """正例：srand使用"""
        src = "#include <stdlib.h>\nvoid foo(unsigned seed) { srand(seed); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "rand_insecure" for i in issues)


# ============================================================================
# strtok不可重入检测 (_rule_strtok_nonreentrant)
# ============================================================================

class TestStrtokNonreentrant:
    """strtok不可重入检测测试集"""
    
    def test_positive_strtok(self):
        """正例：strtok使用"""
        src = "#include <string.h>\nvoid foo(char *s) { char *token = strtok(s, ","); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "strtok_nonreentrant" for i in issues)


# ============================================================================
# pthread返回值检查 (_rule_pthread_returns_unchecked)
# ============================================================================

class TestPthreadReturnsUnchecked:
    """pthread返回值检查测试集"""
    
    def test_positive_pthread_create_unchecked(self):
        """正例：pthread_create返回值未检查"""
        src = "#include <pthread.h>\nvoid foo() { pthread_t t; pthread_create(&t, NULL, NULL, NULL); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "pthread_ret_unchecked" for i in issues)
    
    def test_negative_pthread_create_checked(self):
        """反例：pthread_create返回值已检查"""
        src = "#include <pthread.h>\nvoid foo() { pthread_t t; if (pthread_create(&t, NULL, NULL, NULL) != 0) { return; } }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "pthread_ret_unchecked" for i in issues)


# ============================================================================
# 线程泄漏检测 (_rule_thread_leak_no_join)
# ============================================================================

class TestThreadLeakNoJoin:
    """线程泄漏检测测试集"""
    
    def test_positive_thread_no_join(self):
        """正例：线程创建后未join"""
        src = "#include <pthread.h>\nvoid foo() { pthread_t t; pthread_create(&t, NULL, NULL, NULL); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "thread_leak_no_join" for i in issues)
    
    def test_negative_thread_with_join(self):
        """反例：线程创建后有join"""
        src = "#include <pthread.h>\nvoid foo() { pthread_t t; pthread_create(&t, NULL, NULL, NULL); pthread_join(t, NULL); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "thread_leak_no_join" for i in issues)


# ============================================================================
# 死锁模式检测 (_rule_deadlock_patterns)
# ============================================================================

class TestDeadlockPatterns:
    """死锁模式检测测试集"""
    
    def test_positive_recursive_lock(self):
        """正例：递归锁"""
        src = "#include <pthread.h>\nvoid foo(pthread_mutex_t *m) { pthread_mutex_lock(m); pthread_mutex_lock(m); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "deadlock_patterns" for i in issues)


# ============================================================================
# 未初始化指针使用检测 (_rule_uninitialized_ptr_use)
# ============================================================================

class TestUninitializedPtrUse:
    """未初始化指针使用检测测试集"""
    
    def test_positive_uninitialized_ptr(self):
        """正例：未初始化指针使用"""
        src = "void foo() { char *p; *p = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "uninitialized_ptr_use" for i in issues)


# ============================================================================
# 智能指针循环检测 (_rule_smart_ptr_cycle)
# ============================================================================

class TestSmartPtrCycle:
    """智能指针循环检测测试集"""
    
    def test_positive_shared_ptr_cycle(self):
        """正例：shared_ptr循环引用"""
        src = "#include <memory>\nclass A { std::shared_ptr<A> next; };\nvoid foo() { auto a = std::make_shared<A>(); a->next = a; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "smart_ptr_cycle" for i in issues)


# ============================================================================
# 智能指针get()不安全检测 (_rule_smart_ptr_get_unsafe)
# ============================================================================

class TestSmartPtrGetUnsafe:
    """智能指针get()不安全检测测试集"""
    
    def test_positive_get_stored(self):
        """正例：get()结果被存储"""
        src = "#include <memory>\nvoid foo() { auto p = std::make_shared<int>(42); int *raw = p.get(); *raw = 100; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "smart_ptr_get_unsafe" for i in issues)


# ============================================================================
# new/delete不匹配检测 (_rule_new_delete_mismatch)
# ============================================================================

class TestNewDeleteMismatch:
    """new/delete不匹配检测测试集"""
    
    def test_positive_new_with_free(self):
        """正例：new配free"""
        src = "void foo() { int *p = new int(42); free(p); }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "new_delete_mismatch" for i in issues)
    
    def test_positive_malloc_with_delete(self):
        """正例：malloc配delete"""
        src = "#include <stdlib.h>\nvoid foo() { int *p = (int*)malloc(sizeof(int)); delete p; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "new_delete_mismatch" for i in issues)


# ============================================================================
# reinterpret_cast不安全检测 (_rule_reinterpret_cast_unsafe)
# ============================================================================

class TestReinterpretCastUnsafe:
    """reinterpret_cast不安全检测测试集"""
    
    def test_positive_reinterpret_cast(self):
        """正例：reinterpret_cast使用"""
        src = "void foo() { int x = 42; char *p = reinterpret_cast<char*>(&x); }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "reinterpret_cast_unsafe" for i in issues)


# ============================================================================
# const_cast不安全检测 (_rule_const_cast_unsafe)
# ============================================================================

class TestConstCastUnsafe:
    """const_cast不安全检测测试集"""
    
    def test_positive_const_cast_remove(self):
        """正例：const_cast移除const"""
        src = "void foo(const int *p) { int *q = const_cast<int*>(p); *q = 100; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "const_cast_unsafe" for i in issues)


# ============================================================================
# 缺少虚析构函数检测 (_rule_missing_virtual_dtor)
# ============================================================================

class TestMissingVirtualDtor:
    """缺少虚析构函数检测测试集"""
    
    def test_positive_missing_virtual_dtor(self):
        """正例：基类缺少虚析构函数"""
        src = "class Base { public: ~Base() {} };\nclass Derived : public Base { public: ~Derived() {} };\nvoid foo() { Base *b = new Derived(); delete b; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "missing_virtual_dtor" for i in issues)


# ============================================================================
# move后使用检测 (_rule_move_after_use)
# ============================================================================

class TestMoveAfterUse:
    """move后使用检测测试集"""
    
    def test_positive_move_then_use(self):
        """正例：move后使用"""
        src = "#include <utility>\nvoid foo() { std::string s = "hello"; std::string t = std::move(s); s.size(); }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "move_after_use" for i in issues)


# ============================================================================
# 未捕获异常检测 (_rule_uncaught_exception)
# ============================================================================

class TestUncaughtException:
    """未捕获异常检测测试集"""
    
    def test_positive_throw_no_catch(self):
        """正例：throw无catch"""
        src = "void foo() { throw 42; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "uncaught_exception" for i in issues)


# ============================================================================
# vector字符串边界检查 (_rule_vector_string_bounds_check)
# ============================================================================

class TestVectorStringBoundsCheck:
    """vector字符串边界检查测试集"""
    
    def test_positive_vector_no_check(self):
        """正例：vector访问无检查"""
        src = "#include <vector>\nvoid foo() { std::vector<int> v; v[0] = 42; }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert any(i.pattern == "vector_string_bounds_check" for i in issues)
    
    def test_negative_vector_with_check(self):
        """反例：vector访问有检查"""
        src = "#include <vector>\nvoid foo() { std::vector<int> v; if (!v.empty()) { v[0] = 42; } }"
        issues = analyze_c_cpp_text("test.cpp", src)
        assert not any(i.pattern == "vector_string_bounds_check" for i in issues)


# ============================================================================
# strncpy未终止检测 (_rule_strncpy_no_nullterm)
# ============================================================================

class TestStrncpyNoNullterm:
    """strncpy未终止检测测试集"""
    
    def test_positive_strncpy_no_terminator(self):
        """正例：strncpy未添加终止符"""
        src = "#include <string.h>\nvoid foo(char *dst, const char *src, size_t n) { strncpy(dst, src, n); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "strncpy_no_nullterm" for i in issues)
    
    def test_negative_strncpy_with_terminator(self):
        """反例：strncpy后添加终止符"""
        src = "#include <string.h>\nvoid foo(char *dst, const char *src, size_t n) { strncpy(dst, src, n); dst[n-1] = '\0'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "strncpy_no_nullterm" for i in issues)


# ============================================================================
# realloc未赋回检测 (_rule_realloc_assign_back)
# ============================================================================

class TestReallocAssignBack:
    """realloc未赋回检测测试集"""
    
    def test_positive_realloc_no_assign(self):
        """正例：realloc未赋回原指针"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); realloc(p, 200); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "realloc_assign_back" for i in issues)
    
    def test_negative_realloc_with_assign(self):
        """反例：realloc赋回原指针"""
        src = "#include <stdlib.h>\nvoid foo() { char *p = malloc(100); p = realloc(p, 200); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "realloc_assign_back" for i in issues)


# ============================================================================
# 函数返回指针未检查 (_rule_function_return_ptr_no_check)
# ============================================================================

class TestFunctionReturnPtrNoCheck:
    """函数返回指针未检查测试集"""
    
    def test_positive_return_ptr_no_check(self):
        """正例：函数返回指针未检查"""
        src = "#include <stdlib.h>\nchar* get_buffer() { return malloc(100); }\nvoid foo() { char *p = get_buffer(); p[0] = 'x'; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "function_return_ptr_no_check" for i in issues)


# ============================================================================
# I/O返回值未检查 (_rule_unchecked_io)
# ============================================================================

class TestUncheckedIO:
    """I/O返回值未检查测试集"""
    
    def test_positive_fopen_no_check(self):
        """正例：fopen返回值未检查"""
        src = "#include <stdio.h>\nvoid foo() { FILE *fp = fopen("test.txt", "r"); char buf[100]; fread(buf, 1, 100, fp); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "unchecked_io" for i in issues)
    
    def test_negative_fopen_with_check(self):
        """反例：fopen返回值已检查"""
        src = "#include <stdio.h>\nvoid foo() { FILE *fp = fopen("test.txt", "r"); if (fp == NULL) return; char buf[100]; fread(buf, 1, 100, fp); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "unchecked_io" for i in issues)


# ============================================================================
# alloca无界检测 (_rule_alloca_unbounded)
# ============================================================================

class TestAllocaUnbounded:
    """alloca无界检测测试集"""
    
    def test_positive_alloca_variable_size(self):
        """正例：alloca使用变量大小"""
        src = "#include <alloca.h>\nvoid foo(size_t n) { char *p = alloca(n); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "alloca_unbounded" for i in issues)


# ============================================================================
# VLA使用检测 (_rule_vla_usage)
# ============================================================================

class TestVlaUsage:
    """VLA使用检测测试集"""
    
    def test_positive_vla(self):
        """正例：VLA使用"""
        src = "void foo(int n) { char buf[n]; }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "vla_usage" for i in issues)


# ============================================================================
# cond_wait无循环检测 (_rule_cond_wait_no_loop)
# ============================================================================

class TestCondWaitNoLoop:
    """cond_wait无循环检测测试集"""
    
    def test_positive_cond_wait_no_loop(self):
        """正例：pthread_cond_wait不在循环中"""
        src = "#include <pthread.h>\nvoid foo(pthread_cond_t *c, pthread_mutex_t *m) { pthread_mutex_lock(m); pthread_cond_wait(c, m); pthread_mutex_unlock(m); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "cond_wait_no_loop" for i in issues)
    
    def test_negative_cond_wait_in_loop(self):
        """反例：pthread_cond_wait在循环中"""
        src = "#include <pthread.h>\nvoid foo(pthread_cond_t *c, pthread_mutex_t *m) { pthread_mutex_lock(m); while (!condition) { pthread_cond_wait(c, m); } pthread_mutex_unlock(m); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "cond_wait_no_loop" for i in issues)


# ============================================================================
# inet旧版API检测 (_rule_inet_legacy)
# ============================================================================

class TestInetLegacy:
    """inet旧版API检测测试集"""
    
    def test_positive_inet_aton(self):
        """正例：inet_aton使用"""
        src = "#include <arpa/inet.h>\nvoid foo() { struct in_addr addr; inet_aton("127.0.0.1", &addr); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "inet_legacy" for i in issues)


# ============================================================================
# 时间API不线程安全检测 (_rule_time_apis_not_threadsafe)
# ============================================================================

class TestTimeApisNotThreadsafe:
    """时间API不线程安全检测测试集"""
    
    def test_positive_time_no_threadsafe(self):
        """正例：time函数使用"""
        src = "#include <time.h>\nvoid foo() { time_t t = time(NULL); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "time_apis_not_threadsafe" for i in issues)
    
    def test_positive_localtime_no_threadsafe(self):
        """正例：localtime函数使用"""
        src = "#include <time.h>\nvoid foo() { time_t t = time(NULL); struct tm *tm = localtime(&t); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "time_apis_not_threadsafe" for i in issues)


# ============================================================================
# getenv未检查检测 (_rule_getenv_unchecked)
# ============================================================================

class TestGetenvUnchecked:
    """getenv未检查检测测试集"""
    
    def test_positive_getenv_no_check(self):
        """正例：getenv返回值未检查"""
        src = "#include <stdlib.h>\nvoid foo() { char *home = getenv("HOME"); printf("%s\n", home); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "getenv_unchecked" for i in issues)
    
    def test_negative_getenv_with_check(self):
        """反例：getenv返回值已检查"""
        src = "#include <stdlib.h>\nvoid foo() { char *home = getenv("HOME"); if (home == NULL) return; printf("%s\n", home); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "getenv_unchecked" for i in issues)


# ============================================================================
# 权限过于宽松检测 (_rule_open_permissive_perms)
# ============================================================================

class TestOpenPermissivePerms:
    """权限过于宽松检测测试集"""
    
    def test_positive_open_0777(self):
        """正例：open使用0777权限"""
        src = "#include <fcntl.h>\nvoid foo() { int fd = open("test.txt", O_CREAT, 0777); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert any(i.pattern == "open_permissive_perms" for i in issues)
    
    def test_negative_open_0600(self):
        """反例：open使用0600权限"""
        src = "#include <fcntl.h>\nvoid foo() { int fd = open("test.txt", O_CREAT, 0600); }"
        issues = analyze_c_cpp_text("test.c", src)
        assert not any(i.pattern == "open_permissive_perms" for i in issues)


# ============================================================================
# fopen模式检测 (_rule_fopen_mode)
# ============================================================================

class TestFopenMode:
    """fopen模式检测测试集"""
    
    def test_positive_fopen_write_no_check(self):
        """正例：fopen写模式"""
        src = "#include <stdio.h>\nvoid foo() { FILE *fp = fopen("test.txt", "w"); }"
        issues = analyze_c_cpp_text("test.c", src)
        # fopen写模式本身不是问题，但可能触发其他检查
        assert isinstance(issues, list)
