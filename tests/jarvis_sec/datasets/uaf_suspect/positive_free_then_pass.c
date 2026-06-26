/*
 * 正例：free后传递给函数
 * 预期：应该检测到 uaf_suspect
 */
#include <stdlib.h>
#include <stdio.h>
void foo() {
    char *p = malloc(100);
    free(p);
    printf("%p\n", p);  // 真实风险：UAF
}
