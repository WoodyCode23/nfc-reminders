"""Windows stand-in for resource so the Home Assistant test harness imports."""
RLIMIT_NOFILE = 7


def getrlimit(r):
    return (2048, 2048)


def setrlimit(r, limits):
    return None
