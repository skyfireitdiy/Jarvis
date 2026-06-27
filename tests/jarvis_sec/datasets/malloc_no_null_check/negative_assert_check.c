/*
 * 误报测试：malloc未检查NULL - 使用assert检查
 * 漏洞类型：alloc_no_null_check
 * 说明：使用assert(ptr != NULL)是合法的NULL检查方式，
 *       不应被误报为"未检查NULL"
 * 预期：不应检测到alloc_no_null_check
 */
#include <stdlib.h>
#include <assert.h>

void foo() {
    char *p = (char*)malloc(100);
    assert(p != NULL);  /* 合法的NULL检查方式 */
    p[0] = 'x';
}

void bar() {
    int *arr = (int*)malloc(50 * sizeof(int));
    assert(arr);  /* assert(ptr)也是合法的NULL检查 */
    arr[0] = 42;
}
