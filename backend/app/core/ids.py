"""UUID v7 generation. See docs/database.md §1: "Primary keys are UUID v7 where available,
v4 otherwise." The stdlib gains uuid.uuid7 in 3.14; until then we generate it directly per
RFC 9562 so the schema doesn't wait on the interpreter version.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand = int.from_bytes(os.urandom(10), "big")

    version = 0x7
    variant = 0b10
    rand_a = (rand >> 62) & 0x0FFF
    rand_b = rand & 0x3FFFFFFFFFFFFFFF

    value = (unix_ms << 80) | (version << 76) | (rand_a << 64) | (variant << 62) | rand_b
    return uuid.UUID(int=value)
