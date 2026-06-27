/*
 * 误报测试：UAF - free后赋值NULL
 * 漏洞类型：use_after_free_suspect
 * 说明：free后立即将指针置NULL是安全的防御性编程模式，
 *       不应被误报为UAF嫌疑
 * 预期：不应检测到use_after_free_suspect
 */
#include <stdlib.h>

void foo() {
    char *p = (char*)malloc(100);
    free(p);
    p = NULL;  /* 安全：free后置NULL，防止悬空指针 */
}

void bar() {
    int *arr = (int*)malloc(50 * sizeof(int));
    free(arr);
    arr = NULL;  /* 安全：free后置NULL */
}
