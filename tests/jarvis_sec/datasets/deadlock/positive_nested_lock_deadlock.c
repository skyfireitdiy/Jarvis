#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

pthread_mutex_t lockA = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lockB = PTHREAD_MUTEX_INITIALIZER;
pthread_mutex_t lockC = PTHREAD_MUTEX_INITIALIZER;

void *thread1_func(void *arg) {
  // 线程1: A -> B -> C
  pthread_mutex_lock(&lockA);
  printf("Thread1: lockA acquired\n");
  sleep(1);

  pthread_mutex_lock(&lockB);
  printf("Thread1: lockB acquired\n");
  sleep(1);

  pthread_mutex_lock(&lockC);
  printf("Thread1: lockC acquired\n");

  pthread_mutex_unlock(&lockC);
  pthread_mutex_unlock(&lockB);
  pthread_mutex_unlock(&lockA);
  return NULL;
}

void *thread2_func(void *arg) {
  // 线程2: C -> B -> A (与线程1完全相反)
  pthread_mutex_lock(&lockC);
  printf("Thread2: lockC acquired\n");
  sleep(1);

  pthread_mutex_lock(&lockB);
  printf("Thread2: lockB acquired\n");
  sleep(1);

  pthread_mutex_lock(&lockA);
  printf("Thread2: lockA acquired\n");

  pthread_mutex_unlock(&lockA);
  pthread_mutex_unlock(&lockB);
  pthread_mutex_unlock(&lockC);
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
