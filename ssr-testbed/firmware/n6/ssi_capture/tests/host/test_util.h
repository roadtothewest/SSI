#ifndef TEST_UTIL_H
#define TEST_UTIL_H

#include <stdio.h>

static int g_fail;

#define CHECK(c)                                                          \
  do {                                                                    \
    if (!(c)) {                                                           \
      fprintf(stderr, "%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #c);      \
      g_fail++;                                                           \
    }                                                                     \
  } while (0)

#define CHECK_EQ(a, b)                                                                  \
  do {                                                                                  \
    long long _a = (long long)(a), _b = (long long)(b);                                 \
    if (_a != _b) {                                                                     \
      fprintf(stderr, "%s:%d: %s == %lld, expected %lld\n", __FILE__, __LINE__, #a, _a, \
              _b);                                                                      \
      g_fail++;                                                                         \
    }                                                                                   \
  } while (0)

#define TEST_END()                                                    \
  do {                                                                \
    if (g_fail) fprintf(stderr, "%d check(s) failed\n", g_fail);     \
    return g_fail ? 1 : 0;                                            \
  } while (0)

#endif
