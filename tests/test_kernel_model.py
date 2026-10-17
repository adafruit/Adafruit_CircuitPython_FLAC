# SPDX-FileCopyrightText: Copyright (c) 2026 Mikey Sklar for Adafruit Industries
# SPDX-License-Identifier: MIT
"""Run test_decoder with a CPython model of the turbo kernel (src/flac_turbo.py).

Viper can't run on the desktop, so this mirrors the kernel's integer math line by line
and fails if any product or running sum leaves the signed 32-bit range a viper int has.
That checks the bounds _predict uses to pick a kernel function, and the exactness of the
split predictor, against libFLAC's reference decode.

usage: python3 tests/test_kernel_model.py [clip-name ...]
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_decoder  # noqa: E402

import adafruit_flac  # noqa: E402

LO, HI = -(1 << 31), (1 << 31) - 1


def i32(v):
    if not LO <= v <= HI:
        raise OverflowError("32-bit overflow: %d" % v)
    return v


class Kernel:
    """Same signatures and arithmetic as src/flac_turbo.py."""

    calls = {"rice": 0, "residual": 0, "pcm": 0, "decorrelate": 0, "lpc": 0, "lpc_split": 0}

    class _NoKernel:
        _kernel = None

    @staticmethod
    def rice_decode(d, lz, out, pos, o, end, k):
        Kernel.calls["rice"] += 1
        return adafruit_flac._rice(d, pos, out, o, end, k)

    @staticmethod
    def residual(d, lz, out, pos, bs, order):
        # Same bitstream walk as the Python path; the viper version only adds shifts
        # and masks on 32-bit windows, checked bit-exact on the board.
        Kernel.calls["residual"] += 1
        b = adafruit_flac._Bits(d, pos)
        try:
            adafruit_flac.FLACDecoder._residual_py(Kernel._NoKernel(), b, out, bs, order)
        except adafruit_flac.FLACError:
            return -1
        return b.pos

    @staticmethod
    def subframe(d, lz, out, pos, bs, bps, co, stats):
        # The viper subframe walk is checked bit-exact on the board; here hand every
        # subframe to the Python path, which still calls the 32-bit-checked kernels below.
        return -2

    @staticmethod
    def to_pcm16(pcm, ch, n, nch, c, sh):
        Kernel.calls["pcm"] += 1
        for i in range(n):
            v = ch[i] >> sh if sh >= 0 else i32(ch[i] << -sh)
            pcm[c + i * nch] = v  # array('h') raises if it does not fit 16 bits

    @staticmethod
    def decorrelate(a, s, n, code):
        Kernel.calls["decorrelate"] += 1
        for i in range(n):
            if code == 8:
                s[i] = i32(a[i] - s[i])
            elif code == 9:
                a[i] = i32(a[i] + s[i])
            else:
                side = s[i]
                mid = i32(i32(a[i] << 1) | (side & 1))
                a[i] = i32(mid + side) >> 1
                s[i] = i32(mid - side) >> 1

    @staticmethod
    def lpc_restore(out, coefs, order, shift, n):
        Kernel.calls["lpc"] += 1
        for i in range(order, n):
            s = 0
            for j in range(order):
                s = i32(s + i32(coefs[j] * out[i - 1 - j]))
            out[i] = i32(out[i] + (s >> shift))

    @staticmethod
    def lpc_restore_split(out, coefs, order, shift, n, b):
        Kernel.calls["lpc_split"] += 1
        lm = (1 << b) - 1
        for i in range(order, n):
            hs = ls = 0
            for j in range(order):
                c = coefs[j]
                x = out[i - 1 - j]
                hs = i32(hs + i32(c * (x >> b)))
                ls = i32(ls + i32(c * (x & lm)))
            if shift >= b:
                p = i32(hs + (ls >> b)) >> (shift - b)
            else:
                p = i32(i32(hs << (b - shift)) + (ls >> shift))
            out[i] = i32(out[i] + p)


def test_kernel_model(monkeypatch):
    """pytest entry: the decoder tests again, through the 32-bit-checked kernel model."""
    monkeypatch.setattr(adafruit_flac, "_kernel", Kernel)
    test_decoder.test_decoder()


if __name__ == "__main__":
    adafruit_flac._kernel = Kernel
    try:
        test_decoder.main()
    finally:
        print("kernel calls:", Kernel.calls)
