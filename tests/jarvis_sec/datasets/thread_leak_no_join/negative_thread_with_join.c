/*
 * 反例：线程创建后有join
 * 预期：不应该检测到 thread_leak_no_join
 */
#include <pthread.h>
void foo() {
  pthread_t t;
  pthread_create(&t, NULL, NULL, NULL);
  pthread_join(t, NULL); // 安全：有join
}
