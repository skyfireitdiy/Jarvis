// SQL注入正例：用户输入 -> SQL语句拼接
// 应该检测到：用户输入直接拼接到SQL语句

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void vulnerable_query(const char *username) {
  char sql[256];

  // 污点汇：用户输入拼接到SQL语句
  // 污点传播路径：argv -> username -> sprintf -> sql
  sprintf(sql, "SELECT * FROM users WHERE name='%s'", username); // SQL注入风险

  printf("Executing: %s\n", sql);
}

int main(int argc, char *argv[]) {
  if (argc > 1) {
    // 污点源：命令行参数
    vulnerable_query(argv[1]);
  }
  return 0;
}
