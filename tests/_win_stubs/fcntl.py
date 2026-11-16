"""Windows stand-in for fcntl so the Home Assistant test harness imports."""
LOCK_EX = LOCK_NB = LOCK_UN = LOCK_SH = 0


def flock(fd, op):
    return None


def fcntl(fd, op, arg=0):
    return 0
