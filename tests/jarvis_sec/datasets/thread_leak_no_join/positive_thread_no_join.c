/*
 * 正例：线程创建后未join
 * 预期：应该检测到 thread_leak_no_join
 */
#include <pthread.h>
void foo() {
  pthread_t t;
  pthread_create(&t, NULL, NULL, NULL); // 真实风险：未join
}
