#include "audio_decode.h"
#include "test_util.h"

int main(void)
{
  CHECK_EQ(audio_sign_extend24(0x000000u), 0);
  CHECK_EQ(audio_sign_extend24(0x7FFFFFu), 8388607);
  CHECK_EQ(audio_sign_extend24(0x800000u), -8388608);
  CHECK_EQ(audio_sign_extend24(0xFFFFFFu), -1);
  CHECK_EQ(audio_sign_extend24(0xFF000001u), 1);  /* bits 31..24 ignored */
  CHECK_EQ(audio_sign_extend24(0xFFFFFFFEu), -2); /* already sign-extended input */

  const uint32_t st[8] = {0x000001u, 0u, 0xFFFFFFu, 0u, 0x800000u, 5u, 0x7FFFFFu, 0u};
  int32_t out[4];
  audio_extract_left(st, out, 4);
  CHECK_EQ(out[0], 1);
  CHECK_EQ(out[1], -1);
  CHECK_EQ(out[2], -8388608);
  CHECK_EQ(out[3], 8388607);
  CHECK_EQ(audio_right_activity(st, 4), 1);
  TEST_END();
}
