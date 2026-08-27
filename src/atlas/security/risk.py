from enum import IntEnum


class RiskLevel(IntEnum):
    READ_ONLY = 0
    SAFE = 1
    LOCAL_MODIFICATION = 2
    ADMIN = 3
    CRITICAL = 4