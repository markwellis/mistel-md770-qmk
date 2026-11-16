.syntax unified
.cpu cortex-m0
.thumb

.global __main_stack_end__, __process_stack_end__
.set __main_stack_end__, 0x20004000
.set __process_stack_end__, 0x20003000

.section .text
.word __main_stack_end__
.space 128
.word scan_irq
.space 12
.word radio_irq

.global thread, masked_thread, unaligned_thread, sleep_thread, scan_irq, radio_irq
.thumb_func
thread:
    nop
    bx lr

.thumb_func
masked_thread:
    cpsid i
    nop
    cpsie i
    nop
    bx lr

.thumb_func
unaligned_thread:
    ldr r0, =0x20000201
    ldr r0, [r0]
    bx lr

.thumb_func
sleep_thread:
    wfi
    bx lr

.thumb_func
scan_irq:
    mrs r0, apsr
    ldr r1, =0x20000100
    str r0, [r1]
    mrs r0, ipsr
    str r0, [r1, #4]
    mrs r0, msp
    str r0, [r1, #8]
    movs r0, #17
    movs r2, #22
    movs r3, #33
    bx lr

.thumb_func
radio_irq:
    mrs r0, ipsr
    ldr r1, =0x20000110
    str r0, [r1]
    movs r0, #21
    bx lr
