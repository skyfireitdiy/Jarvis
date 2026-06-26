/*
 * 预期检测结果: 应检测到SQL注入
 * 陷阱: 看起来使用了参数化，但实际仍是拼接
 * 漏洞类型: 隐藏的SQL注入
 */
#include <stdio.h>
#include <string.h>

void tricky_sql_injection(char *user_id) {
  char query[500];
  // 陷阱: 看起来像参数化查询，实际仍是字符串拼接
  snprintf(query, sizeof(query), "SELECT * FROM users WHERE id = '%s'",
           user_id); // SQL注入!
}

void sql_via_concat(char *table, char *condition) {
  char query[1000];
  strcpy(query, "SELECT * FROM ");
  // 陷阱: 表名拼接
  strcat(query, table); // SQL注入!
  strcat(query, " WHERE ");
  strcat(query, condition); // SQL注入!
}

void hidden_sql_injection(char *input) {
  char query[256];
  // 陷阱: 使用sprintf看起来"安全"，但仍是拼接
  sprintf(query, "DELETE FROM logs WHERE name='%s'", input); // SQL注入!
}
