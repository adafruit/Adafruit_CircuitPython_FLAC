# SPDX-FileCopyrightText: Copyright (c) 2026 Mikey Sklar for Adafruit Industries
# SPDX-License-Identifier: MIT
"""Check the turbo kernel on a board: same PCM as the plain Python path, and how fast.

For every .flac in /flac, decodes with turbo=False and turbo=True side by side and compares
each chunk, then times a turbo-only decode. load% = decode time / audio time.
"""

import gc
import os
import time
from array import array

import adafruit_flac

DIR = "/flac"
print("kernel:", adafruit_flac._kernel)
buf_a = array("h", bytes(2 * 4096))
buf_b = array("h", bytes(2 * 4096))


def same(path):
    a = adafruit_flac.FLACDecoder(path, turbo=False)
    b = adafruit_flac.FLACDecoder(path, turbo=True)
    total = 0
    while True:
        na = a.readinto(buf_a)
        nb = b.readinto(buf_b)
        if na != nb or bytes(memoryview(buf_a)[:na]) != bytes(memoryview(buf_b)[:nb]):
            return False, total
        total += na
        if na < len(buf_a):
            return True, total


def timed(path, turbo):
    gc.collect()
    d = adafruit_flac.FLACDecoder(path, turbo=turbo)
    t0 = time.monotonic_ns()
    while d.readinto(buf_a) == len(buf_a):
        pass
    t = (time.monotonic_ns() - t0) / 1e9
    return 100 * t / d.duration, list(d.lpc_modes)


def main():
    print("%-16s %-6s %8s %9s  %s" % ("clip", "exact", "turbo", "python", "lpc modes"))
    for name in sorted(os.listdir(DIR)):
        if not name.endswith(".flac"):
            continue
        path = DIR + "/" + name
        ok, n = same(path)
        load, modes = timed(path, True)
        py = ""
        if name.startswith("s16_44k_l5"):
            py = "%8.1f%%" % timed(path, False)[0]
        print(
            "%-16s %-6s %7.1f%% %9s  %s"
            % (name[:-5], "yes" if ok else "NO@%d" % n, load, py, modes)
        )
    print("done")


if __name__ == "__main__":
    main()
