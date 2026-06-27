/*
 * 跨文件格式化字符串 - 日志输出模块
 * 用户输入在此文件被作为格式串使用
 * 漏报点：c_checker的_rule_format_string未覆盖syslog/err等函数的格式串参数
 */
#include <stdio.h>
#include <syslog.h>
#include <err.h>

/* 使用syslog输出 - 漏报点：未覆盖syslog格式串 */
void log_message(const char *fmt) {
    syslog(LOG_ERR, fmt);  /* fmt来自用户输入，格式串注入 */
}

/* 使用printf输出 */
void print_formatted(const char *fmt, int value) {
    printf(fmt, value);  /* fmt来自用户输入，格式串注入 */
}

/* 使用err输出 - 漏报点：未覆盖err格式串 */
void fatal_error(const char *fmt) {
    err(1, fmt);  /* fmt来自用户输入，格式串注入 */
}
