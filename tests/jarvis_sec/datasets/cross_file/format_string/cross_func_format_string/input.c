/*
 * 跨文件格式化字符串 - 输入获取模块
 * 用户输入从此文件获取，跨文件传播到格式化输出
 */
#include <stdio.h>
#include <stdlib.h>

/* 从用户获取消息格式 */
const char *get_message_format(void) {
    static char buf[256];
    printf("Enter log format: ");
    fgets(buf, sizeof(buf), stdin);
    return buf;
}

/* 从环境变量获取 */
const char *get_env_format(const char *var) {
    return getenv(var);  /* 环境变量可能被攻击者控制 */
}
