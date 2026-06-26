/*
 * 反例：无锁保护的读操作
 * 预期：不应该检测到 data_race_suspect 或置信度很低
 */
#include <pthread.h>
int shared_data = 0;
void *thread_func(void *arg) {
  int val = shared_data; // 读操作，风险较低
  return NULL;
}
int main() {
  pthread_t t;
  pthread_create(&t, NULL, thread_func, NULL);
  pthread_join(t, NULL);
  return 0;
}
