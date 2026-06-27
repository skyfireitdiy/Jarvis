/*
 * 跨文件路径遍历 - 输入获取模块
 * 用户输入从此文件获取，跨文件传播到文件操作
 */
#include <stdio.h>
#include <stdlib.h>

/* 从用户获取文件名 */
const char *get_filename(void) {
    static char buf[256];
    printf("Enter filename: ");
    fgets(buf, sizeof(buf), stdin);
    return buf;
}
