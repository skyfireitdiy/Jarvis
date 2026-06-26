/*
 * 正例：inet_aton使用
 * 预期：应该检测到 inet_legacy
 */
#include <arpa/inet.h>
void foo() {
  struct in_addr addr;
  inet_aton("127.0.0.1", &addr); // 真实风险：旧版API
}
