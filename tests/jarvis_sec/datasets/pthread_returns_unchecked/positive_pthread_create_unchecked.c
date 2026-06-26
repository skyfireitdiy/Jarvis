/*
 * 正例：pthread_create返回值未检查
 * 预期：应该检测到 pthread_returns_unchecked
 */
#include <pthread.h>
void foo() {
  pthread_t t;
  pthread_create(&t, NULL, NULL, NULL); // 真实风险：未检查返回值
}
