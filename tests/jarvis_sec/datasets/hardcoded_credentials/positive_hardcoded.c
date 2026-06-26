/*
 * 预期检测结果: 应检测到硬编码凭证
 * 漏洞类型: 敏感信息硬编码
 */
#include <string.h>

// 硬编码密码 - 安全风险
const char *DB_PASSWORD = "admin123";
const char *API_KEY = "sk-1234567890abcdef";
#define SECRET_KEY "my_secret_key_123"

void connect_database() {
  char password[] = "root_password"; // 硬编码
  char *key = "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE";

  // 使用硬编码凭证
  if (strcmp(password, DB_PASSWORD) == 0) {
    // 连接数据库
  }
}
