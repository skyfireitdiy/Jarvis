/*
 * 反例：pthread_create返回值已检查
 * 预期：不应该检测到 pthread_returns_unchecked
 */
#include <pthread.h>
void foo() {
  pthread_t t;
  if (pthread_create(&t, NULL, NULL, NULL) != 0) {
    return; // 安全：有检查
  }
}
