#ifndef SSI_CONFIG_H
#define SSI_CONFIG_H

/* Acquisition constants shared by drivers, pure logic and packet format (spec v0.2). */
#define SSI_AUDIO_FS_HZ    16000u
#define SSI_EMG_DIV        8u                               /* EMG fs = audio fs / 8 = 2 kHz */
#define SSI_EMG_CH         3u
#define SSI_WIN_AUDIO      160u                             /* frames per 10 ms window */
#define SSI_WIN_EMG        (SSI_WIN_AUDIO / SSI_EMG_DIV)    /* 20 = tuples per SPI block */
#define SSI_AUDIO_STARTUP  4800u                            /* INMP441 start-up (~300 ms): diag skips it */
#define SSI_SYNC_C         0                                /* audio frame of EMG sample 0 (spec §4) */

#define SSI_FW_VERSION     0x000100u                        /* 0.1.0 */

#endif
