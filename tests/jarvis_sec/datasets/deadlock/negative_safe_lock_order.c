#include <pthread.h>
#include <stdio.h>

pthread_mutex_t lockA = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lockB = PTHREAD_MUTEX_INITIALIZER;

void *thread1_func(void *arg) {
  // 线程1: 先锁A，再锁B (AB顺序)
  pthread_mutex_lock(&lockA);
  printf("Thread1: lockA acquired\n");

  pthread_mutex_lock(&lockB);
  printf("Thread1: lockB acquired\n");

  pthread_mutex_unlock(&lockB);
  pthread_mutex_unlock(&lockA);
  return NULL;
}

void *thread2_func(void *arg) {
  // 线程2: 也是先锁A，再锁B (AB顺序) - 与线程1相同，不会死锁
  pthread_mutex_lock(&lockA);
  printf("Thread2: lockA acquired\n");

  pthread_mutex_lock(&lockB);
  printf("Thread2: lockB acquired\n");

  pthread_mutex_unlock(&lockB);
  pthread_mutex_unlock(&lockA);
  return NULL;
}

int main() {
  pthread_t t1, t2;
  pthread_create(&t1, NULL, thread1_func, NULL);
  pthread_create(&t2, NULL, thread2_func, NULL);

  pthread_join(t1, NULL);
  pthread_join(t2, NULL);
  return 0;
}
