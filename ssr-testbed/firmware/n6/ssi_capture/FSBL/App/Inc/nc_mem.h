#ifndef NC_MEM_H
#define NC_MEM_H

/* DMA buffers and GPDMA linked-list nodes. ssi_capture_fsbl.ld places .noncacheable in
   NC (0x341F8000-0x341FFFFF), which MPU region 0 marks non-cacheable, so CPU and DMA
   stay coherent without cache maintenance. NOLOAD: contents start undefined. */
#define NC_MEM __attribute__((section(".noncacheable"), aligned(32)))

#endif
