"""A UUID version 7 (RFC 9562): 48 bits of Unix milliseconds, then random bits, so ids sort roughly by creation time.
Local because ``uuid.uuid7`` exists only from Python 3.14 and the server supports 3.11 and later."""
import os
import time
import uuid


def uuid7() -> str:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")                         # 80 random bits: 12 for rand_a, 62 for rand_b (6 spare)
    n = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | (rand >> 68) << 64 | 0b10 << 62 | (rand & ((1 << 62) - 1))
    return str(uuid.UUID(int=n))
