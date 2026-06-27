/*
 * 跨文件格式化字符串 - 主入口
 * 漏洞类型：format_string (跨文件)
 * 漏报原因：用户输入跨文件传播到格式化输出函数，
 *          c_checker的_rule_format_string未覆盖syslog/err等函数
 * 数据流：main.c -> input.c(get_message_format) -> logger.c(log_message)
 * 预期：应检测到format_string，但当前版本因跨文件分析限制和函数覆盖不全而漏报
 */
#include <stdio.h>
#include <stdlib.h>

extern const char *get_message_format(void);
extern void log_message(const char *fmt);
extern void print_formatted(const char *fmt, int value);

int main(void) {
    /* 跨文件格式化字符串数据流 */
    const char *fmt = get_message_format();  /* input.c: 获取用户输入 */
    log_message(fmt);                        /* logger.c: syslog使用用户输入作为格式串 */
    print_formatted(fmt, 42);                /* logger.c: printf使用用户输入作为格式串 */

    return 0;
}
