// SQL注入反例：使用参数化查询
// 不应该检测到：使用参数化查询防止SQL注入

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void safe_query(const char *username) {
  // 使用参数化查询（模拟）
  const char *sql = "SELECT * FROM users WHERE name=?";

  printf("Executing: %s (parameter: %s)\n", sql, username); // 安全：参数化查询
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    safe_query(argv[1]);
  }
  return 0;
}
