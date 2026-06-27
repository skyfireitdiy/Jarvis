/*
 * 跨文件SQL注入 - 输入获取模块
 * 用户输入从此文件获取，跨文件传播到SQL执行
 */
#include <stdio.h>
#include <stdlib.h>

/* 从用户获取输入 */
const char *get_user_input(void) {
    static char buf[256];
    printf("Enter username: ");
    fgets(buf, sizeof(buf), stdin);
    return buf;
}
