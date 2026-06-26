/*
 * 正例：SQL字符串拼接
 * 预期：应该检测到 sql_injection
 */
#include <stdio.h>
#include <string.h>
void execute_user_query(char *user_id) {
  char query[256];
  sprintf(query, "SELECT * FROM users WHERE id = %s", user_id);
  // 危险：直接拼接用户输入到SQL语句
  printf("Executing: %s\n", query);
}
