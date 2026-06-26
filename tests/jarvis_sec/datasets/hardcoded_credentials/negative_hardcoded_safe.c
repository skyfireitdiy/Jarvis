/*
 * 预期检测结果: 不应报告漏洞
 * 安全实践: 从环境变量或配置文件读取凭证
 */
#include <stdlib.h>
#include <string.h>

const char *get_db_password() {
  // 安全: 从环境变量读取
  return getenv("DB_PASSWORD");
}

const char *get_api_key() {
  // 安全: 从环境变量读取
  return getenv("API_KEY");
}

void connect_database_safe() {
  const char *password = get_db_password();
  if (password == NULL) {
    return; // 错误处理
  }
  // 使用从环境变量获取的凭证
}
