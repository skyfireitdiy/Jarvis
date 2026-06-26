/*
 * 预期检测结果: 不应报告漏洞
 * 陷阱: 看起来像SQL注入，但实际是安全的静态查询
 * 安全实践: 静态SQL语句或参数化查询
 */
#include <stdio.h>
#include <string.h>

void safe_static_query() {
  char query[256];
  // 安全: 完全静态的SQL语句
  strcpy(query, "SELECT * FROM users WHERE status = 'active'");
}

void safe_parameterized_simulation(int user_id) {
  char query[256];
  // 安全: 使用整数参数（不是字符串拼接）
  snprintf(query, sizeof(query), "SELECT * FROM users WHERE id = %d", user_id);
}

void safe_table_whitelist(const char *table) {
  char query[256];
  // 安全: 白名单检查表名
  const char *allowed_tables[] = {"users", "logs", "config"};
  int valid = 0;
  for (int i = 0; i < 3; i++) {
    if (strcmp(table, allowed_tables[i]) == 0) {
      valid = 1;
      break;
    }
  }
  if (valid) {
    snprintf(query, sizeof(query), "SELECT * FROM %s", table);
  }
}
