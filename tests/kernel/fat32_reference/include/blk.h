/* The block device interface from agent/kernel_spec/subsystems/drivers.md
 * ("SLM-Managed Driver Interfaces"). FAT32 calls nothing else below it. */
#ifndef AUTON_BLK_H
#define AUTON_BLK_H
#include <stdint.h>

int blk_read(uint32_t dev_id, uint64_t lba, uint32_t count, void *buf);
int blk_write(uint32_t dev_id, uint64_t lba, uint32_t count, const void *buf);

typedef struct blk_info {
    uint64_t sector_count;
    uint32_t sector_size;
    char     model[40];
    char     serial[20];
} blk_info_t;

int blk_get_info(uint32_t dev_id, blk_info_t *info);

#endif
