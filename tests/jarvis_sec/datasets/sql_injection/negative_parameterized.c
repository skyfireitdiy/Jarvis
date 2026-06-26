/*
 * 反例：使用参数化查询（模拟）
 * 预期：不应该检测到 sql_injection
 */
#include <stdio.h>
void safe_query(const char *user_id) {
  // 安全：使用参数化查询（这里用注释模拟）
  // PREPARE stmt FROM 'SELECT * FROM users WHERE id = ?';
  // EXECUTE stmt USING user_id;
  printf("Using parameterized query for id: %s\n", user_id);
}
