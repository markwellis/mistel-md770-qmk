// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "spi_master.h"
#include "flash_spi.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include "keyboards/mistel/md770rgb_bt/storage.c"

bool pins[64];
static bool selected, chip_asleep = true, busy, write_enabled, fail_start, fail_write, cs_output;
static uint32_t now;
static std::vector<std::vector<uint8_t>> transactions;
static uint8_t memory[512];
static unsigned wake_delays, sleep_delays;
static uint8_t fail_opcode;
static unsigned bad_ids, busy_reads, id_reads, status_reads, busy_delays;
static uint8_t status_low = 0x1c, status_high = 2;

void gpio_write_pin_high(unsigned pin) { assert(pin == A9); pins[pin] = true; }
void gpio_set_pin_output(unsigned pin) { assert(pin == A9); cs_output = true; }
void palSetLineMode(unsigned pin, unsigned mode) {
    if (pin == A9) { assert(!mode); cs_output = false; }
    else assert((pin == C2 && mode == SPI_SCK_FLAGS) || (pin == C3 && mode == SPI_MOSI_FLAGS) || (pin == B6 && mode == SPI_MISO_FLAGS));
}
uint32_t timer_read32(void) { return now++; }
void wait_us(unsigned delay) {
    assert((delay == 10 || delay == 100) && !selected);
    if (delay == 100) ++busy_delays;
    else if (chip_asleep) ++sleep_delays;
    else ++wake_delays;
}
bool spi_start(unsigned pin, bool lsb, unsigned mode, unsigned divisor) {
    assert(pin == A9 && !lsb && !mode && divisor == EXTERNAL_FLASH_SPI_CLOCK_DIVISOR && !selected);
    if (fail_start) { fail_start = false; return false; }
    assert(cs_output && pins[A9]);
    selected = true;
    transactions.emplace_back();
    return true;
}
spi_status_t spi_write(uint8_t value) {
    assert(selected);
    if (fail_write && (!fail_opcode || value == fail_opcode)) { fail_write = false; return -1; }
    transactions.back().push_back(value);
    return 0;
}
spi_status_t spi_read(void) {
    assert(selected && transactions.back() == std::vector<uint8_t>{5} && !chip_asleep);
    ++status_reads;
    bool writing = busy || busy_reads;
    if (busy_reads) --busy_reads;
    return status_low | writing;
}
spi_status_t spi_transmit(const uint8_t *data, size_t size) {
    assert(selected && !chip_asleep);
    transactions.back().insert(transactions.back().end(), data, data + size);
    return 0;
}
spi_status_t spi_receive(uint8_t *data, size_t size) {
    auto &command = transactions.back();
    assert(selected && !chip_asleep);
    if (command == std::vector<uint8_t>{0x9f}) {
        assert(size == 3);
        ++id_reads;
        const uint8_t identity[] = {0xc8, 0x40, 0x13};
        memcpy(data, identity, size);
        if (bad_ids) { --bad_ids; data[0] = 0; }
        return 0;
    }
    assert(command.size() == 4 && command[0] == 3);
    unsigned address = command[1] << 16 | command[2] << 8 | command[3];
    assert(address + size <= sizeof(memory));
    memcpy(data, memory + address, size);
    return 0;
}
void spi_stop(void) {
    assert(selected);
    auto &command = transactions.back();
    if (!command.empty()) {
        if (command[0] == 0xab) chip_asleep = false;
        else if (command[0] == 0xb9) { assert(!busy); chip_asleep = true; }
        else {
            assert(!chip_asleep);
            if (command[0] == 6) write_enabled = true;
            if (command[0] == 4) write_enabled = false;
            if (command[0] == 1) {
                assert(write_enabled && command == std::vector<uint8_t>({1, 2, 0}));
                status_low = command[1] & ~2;
                status_high = command[2];
                write_enabled = false;
            }
            if (command[0] == 2) {
                assert(write_enabled && !status_low && !status_high && command.size() >= 4);
                unsigned address = command[1] << 16 | command[2] << 8 | command[3];
                assert(address + command.size() - 4 <= sizeof(memory));
                for (size_t index = 4; index < command.size(); ++index) memory[address + index - 4] &= command[index];
            }
        }
    }
    selected = false;
}

int main(void) {
    memset(memory, 0xff, sizeof(memory));
    flash_init();
    assert(md770_storage_sleep() && transactions.empty());
    uint8_t value = 0;
    assert(flash_read_range(4, &value, 1) == FLASH_STATUS_SUCCESS && value == 0xff);
    assert(transactions[0] == std::vector<uint8_t>{0xab} && wake_delays == 1);
    assert(transactions[1] == std::vector<uint8_t>{0x9f});
    assert(transactions[2] == std::vector<uint8_t>{6});
    assert(transactions[3] == std::vector<uint8_t>({1, 2, 0}));
    assert(!status_low && !status_high);
    busy = true;
    assert(!md770_storage_sleep() && !chip_asleep && cs_output);
    busy = false;
    assert(md770_storage_sleep() && chip_asleep && !cs_output && sleep_delays == 1);
    size_t count = transactions.size();
    assert(md770_storage_sleep() && transactions.size() == count);
    fail_start = true;
    assert(flash_read_range(4, &value, 1) == FLASH_STATUS_ERROR && chip_asleep);
    fail_write = true;
    assert(flash_read_range(4, &value, 1) == FLASH_STATUS_ERROR && chip_asleep);
    count = transactions.size();
    const uint8_t expected[] = {0xa5, 0x5a};
    assert(flash_write_range(4, expected, sizeof(expected)) == FLASH_STATUS_SUCCESS);
    assert(transactions[count] == std::vector<uint8_t>{0xab} && wake_delays == 2 && cs_output);
    uint8_t result[2]{};
    assert(flash_read_range(4, result, sizeof(result)) == FLASH_STATUS_SUCCESS && memcmp(result, expected, sizeof(result)) == 0);
    fail_write = true;
    fail_opcode = 0xb9;
    assert(!md770_storage_sleep() && !chip_asleep);
    assert(md770_storage_sleep() && chip_asleep && !cs_output);
    for (unsigned failures : {2, 1024}) {
        bad_ids = failures;
        busy_reads = failures == 2 ? 2 : 600;
        id_reads = status_reads = busy_delays = 0;
        unsigned delays_before = wake_delays;
        assert(spi_flash_start());
        spi_stop();
        unsigned expected = failures == 2 ? 3 : 1024;
        assert(id_reads == expected && wake_delays - delays_before == expected);
        assert(status_reads == (failures == 2 ? 3 : 600));
        assert(busy_delays == (failures == 2 ? 2 : 600));
        assert(md770_storage_sleep());
    }
    puts("Flash status initialisation, bounded retries, busy deferral, lazy wake and failure recovery passed");
}
