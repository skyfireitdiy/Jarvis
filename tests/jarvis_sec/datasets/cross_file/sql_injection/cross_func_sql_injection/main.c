/*
 * 跨文件SQL注入 - 主入口
 * 漏洞类型：sql_injection (跨文件)
 * 漏报原因：用户输入跨文件传播到SQL执行，
 *          c_checker的_rule_sql_injection仅检测单文件内的sprintf/snprintf拼接
 * 数据流：main.c -> input.c(get_user_input) -> query_builder.c(build_select_query) -> executor.c(execute_query)
 * 预期：应检测到sql_injection，但当前版本因跨文件分析限制而漏报
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern const char *get_user_input(void);
extern void build_select_query(char *sql, const char *username);
extern void execute_query(void *conn, const char *sql);

int main(void) {
    char sql[512];
    void *conn = NULL;  /* 简化，实际应初始化MySQL连接 */

    /* 跨文件SQL注入数据流 */
    const char *username = get_user_input();     /* input.c: 获取用户输入 */
    build_select_query(sql, username);           /* query_builder.c: 拼接SQL */
    execute_query(conn, sql);                    /* executor.c: 执行SQL */

    return 0;
}
