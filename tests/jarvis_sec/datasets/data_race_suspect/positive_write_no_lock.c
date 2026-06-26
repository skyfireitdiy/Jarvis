/*
 * 正例：无锁保护的写操作
 * 预期：应该检测到 data_race_suspect
 */
#include <pthread.h>
int shared_data = 0;
void *thread_func(void *arg) {
  shared_data = 100; // 真实风险：无锁写
  return NULL;
}
int main() {
  pthread_t t;
  pthread_create(&t, NULL, thread_func, NULL);
  pthread_join(t, NULL);
  return 0;
}
