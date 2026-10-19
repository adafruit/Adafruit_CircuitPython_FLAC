# SPDX-FileCopyrightText: Copyright (c) 2026 Mikey Sklar for Adafruit Industries
# SPDX-License-Identifier: MIT
"""FLAC hot loops as turbo (@micropython.viper) functions.

Viper ports of `adafruit_flac._rice` and the LPC predictor (RFC 9639 sections 9.2.7.2 and
9.2.6). Viper ints are 32-bit and wrap, so the caller only uses `lpc_restore` when
sum(|c|) << (bps - 1) fits in 31 bits; other subframes stay on the Python path.

Compile with: mpy-cross -march=armv7emsp flac_turbo.py
"""

import micropython


@micropython.viper
def rice_decode(d: ptr8, lz: ptr8, out: ptr32, pos: int, o: int, end: int, k: int) -> int:
    """Decode Rice codes with parameter k into out[o:end] from bit pos of d. Returns the new
    bit position. lz is the 256-byte leading-zero table. d needs 5 zero guard bytes."""
    if k == 0:
        while o < end:
            i = pos >> 3
            b = (d[i] << (pos & 7)) & 0xFF
            if b:
                q = int(lz[b])
            else:
                q = 8 - (pos & 7)
                i += 1
                while not d[i]:
                    q += 8
                    i += 1
                q += int(lz[d[i]])
            pos += q + 1
            out[o] = (q >> 1) ^ -(q & 1)
            o += 1
        return pos
    rk = 32 - k
    while o < end:
        i = pos >> 3
        b = (d[i] << (pos & 7)) & 0xFF
        if b:
            q = int(lz[b])
        else:
            q = 8 - (pos & 7)
            i += 1
            while not d[i]:
                q += 8
                i += 1
            q += int(lz[d[i]])
        pos += q + 1
        # 32-bit window from the byte holding pos; uint so >> is a logical shift
        i = pos >> 3
        s = pos & 7
        w = uint(d[i]) << 24 | uint(d[i + 1]) << 16 | uint(d[i + 2]) << 8 | uint(d[i + 3])
        v = (w << s) >> rk
        if s + k > 32:
            v |= uint(d[i + 4]) >> (40 - s - k)
        pos += k
        v |= uint(q) << k
        out[o] = int(v >> 1) ^ -int(v & 1)
        o += 1
    return pos


@micropython.viper
def residual(d: ptr8, lz: ptr8, out: ptr32, pos: int, bs: int, order: int) -> int:
    """Decode a whole subframe residual (section 9.2.7) into out[order:bs] from bit pos of d:
    partition headers, escape partitions and Rice codes. Returns the new bit position, or -1
    for a reserved coding method. d needs 5 zero guard bytes."""
    i = pos >> 3
    v = ((d[i] << 8 | d[i + 1]) >> (10 - (pos & 7))) & 0x3F  # method (2 bits), order (4)
    pos += 6
    method = v >> 4
    if method > 1:
        return -1
    porder = v & 15
    pbits = 4 + method
    escape = (1 << pbits) - 1
    psize = bs >> porder
    parts = 1 << porder
    o = order
    p = 0
    while p < parts:
        p += 1
        end = psize * p
        i = pos >> 3
        k = ((d[i] << 8 | d[i + 1]) >> (16 - (pos & 7) - pbits)) & escape
        pos += pbits
        if k == escape:
            # escape: n-bit signed values, or zeros when n == 0
            i = pos >> 3
            n = ((d[i] << 8 | d[i + 1]) >> (11 - (pos & 7))) & 31
            pos += 5
            if n == 0:
                while o < end:
                    out[o] = 0
                    o += 1
                continue
            rn = 32 - n
            while o < end:
                i = pos >> 3
                s = pos & 7
                w = uint(d[i]) << 24 | uint(d[i + 1]) << 16 | uint(d[i + 2]) << 8 | uint(d[i + 3])
                u = (w << s) >> rn
                if s + n > 32:
                    u |= uint(d[i + 4]) >> (40 - s - n)
                out[o] = int(u << rn) >> rn  # sign-extend n bits
                pos += n
                o += 1
            continue
        if k == 0:
            while o < end:
                i = pos >> 3
                b = (d[i] << (pos & 7)) & 0xFF
                if b:
                    q = int(lz[b])
                else:
                    q = 8 - (pos & 7)
                    i += 1
                    while not d[i]:
                        q += 8
                        i += 1
                    q += int(lz[d[i]])
                pos += q + 1
                out[o] = (q >> 1) ^ -(q & 1)
                o += 1
            continue
        rk = 32 - k
        while o < end:
            i = pos >> 3
            b = (d[i] << (pos & 7)) & 0xFF
            if b:
                q = int(lz[b])
            else:
                q = 8 - (pos & 7)
                i += 1
                while not d[i]:
                    q += 8
                    i += 1
                q += int(lz[d[i]])
            pos += q + 1
            i = pos >> 3
            s = pos & 7
            w = uint(d[i]) << 24 | uint(d[i + 1]) << 16 | uint(d[i + 2]) << 8 | uint(d[i + 3])
            u = (w << s) >> rk
            if s + k > 32:
                u |= uint(d[i + 4]) >> (40 - s - k)
            pos += k
            u |= uint(q) << k
            out[o] = int(u >> 1) ^ -int(u & 1)
            o += 1
    return pos


@micropython.viper
def to_pcm16(pcm: ptr16, ch: ptr32, n: int, nch: int, c: int, sh: int):
    """Write channel ch (n samples) into interleaved 16-bit pcm at slot c of nch:
    ch[i] >> sh for sh >= 0 (truncate deeper sources), else ch[i] << -sh."""
    i = 0
    j = c
    if sh >= 0:
        while i < n:
            pcm[j] = ch[i] >> sh
            i += 1
            j += nch
    else:
        ls = 0 - sh
        while i < n:
            pcm[j] = ch[i] << ls
            i += 1
            j += nch


@micropython.viper
def gain(pcm: ptr16, n: int, q: int):
    """Scale n 16-bit samples in place by q / 32768, for 0 <= q <= 32768."""
    i = 0
    while i < n:
        v = int(pcm[i])  # ptr16 loads are unsigned
        if v & 0x8000:
            v -= 0x10000
        pcm[i] = (v * q) >> 15
        i += 1


@micropython.viper
def decorrelate(a: ptr32, s: ptr32, n: int, code: int):
    """Undo stereo decorrelation in place (RFC 9639 section 4.2). code 8: left/side,
    9: side/right, 10: mid/side. a and s are channels 0 and 1."""
    i = 0
    if code == 8:  # right = left - side
        while i < n:
            s[i] = a[i] - s[i]
            i += 1
    elif code == 9:  # left = side + right
        while i < n:
            a[i] = a[i] + s[i]
            i += 1
    else:
        while i < n:
            side = s[i]
            mid = (a[i] << 1) | (side & 1)
            a[i] = (mid + side) >> 1
            s[i] = (mid - side) >> 1
            i += 1


@micropython.viper
def lpc_restore(out: ptr32, coefs: ptr32, order: int, shift: int, n: int):
    """Restore out[order:n] in place: out[i] += sum(coefs[j] * out[i - 1 - j]) >> shift.
    out holds warm-up samples then residuals. The sum must fit in 32 bits."""
    i = order
    while i < n:
        s = 0
        j = 0
        p = i - 1
        while j < order:
            s += coefs[j] * out[p]
            j += 1
            p -= 1
        out[i] += s >> shift
        i += 1


@micropython.viper
def lpc_restore_split(out: ptr32, coefs: ptr32, order: int, shift: int, n: int, b: int):
    """lpc_restore for sums past 32 bits (24-bit audio). Each sample is split as
    x = h * 2**b + l with 0 <= l < 2**b, giving two dot products H and L that stay in
    32 bits, then (H * 2**b + L) >> shift is rebuilt exactly:
    (H + (L >> b)) >> (shift - b) when shift >= b, else (H << (b - shift)) + (L >> shift).
    The caller checks sum(|c|) << max(b, bps - 1 - b) fits in 31 bits."""
    lm = (1 << b) - 1
    i = order
    while i < n:
        hs = 0
        ls = 0
        j = 0
        p = i - 1
        while j < order:
            c = coefs[j]
            x = out[p]
            hs += c * (x >> b)
            ls += c * (x & lm)
            j += 1
            p -= 1
        if shift >= b:
            out[i] += (hs + (ls >> b)) >> (shift - b)
        else:
            out[i] += (hs << (b - shift)) + (ls >> shift)
        i += 1


@micropython.viper
def address(buf: ptr8) -> uint:
    """Address of a buffer, to see whether it sits in internal SRAM (0x2...) or PSRAM
    (0x11...). Viper loops over PSRAM buffers run much slower."""
    return uint(buf)


@micropython.viper
def read_signed(d: ptr8, dst: ptr32, pos: int, start: int, count: int, n: int) -> int:
    """Read count n-bit signed values (1 <= n <= 32) from bit pos of d into dst[start:].
    Returns the new bit position."""
    rn = 32 - n
    j = start
    end = start + count
    while j < end:
        i = pos >> 3
        s = pos & 7
        w = uint(d[i]) << 24 | uint(d[i + 1]) << 16 | uint(d[i + 2]) << 8 | uint(d[i + 3])
        u = (w << s) >> rn
        if s + n > 32:
            u |= uint(d[i + 4]) >> (40 - s - n)
        dst[j] = int(u << rn) >> rn
        pos += n
        j += 1
    return pos


@micropython.viper
def subframe(d_obj, lz_obj, out_obj, pos: int, bs: int, bps: int, co_obj, stats: ptr32) -> int:
    """Decode one whole subframe (RFC 9639 section 9.2) into out[0:bs] from bit pos:
    header, wasted bits, constant / verbatim / fixed / LPC, warm-up samples, coefficients,
    residual and prediction. co is a 32-entry int32 scratch array for the coefficients.
    stats counts predictions like FLACDecoder.lpc_modes (3: plain, 4: split).

    Returns the new bit position; -1 for a malformed or reserved subframe; -2 when this
    subframe needs the Python path (over 25 bits, or a predictor sum that no 32-bit
    method holds), in which case nothing has been consumed."""
    if bps > 25:
        return -2
    d = ptr8(d_obj)
    lz = ptr8(lz_obj)
    out = ptr32(out_obj)
    co = ptr32(co_obj)
    lim = 0x7FFF
    lim = (lim << 16) | 0xFFFF  # largest int32; one literal would fold to a big-int object
    i = pos >> 3
    h = ((d[i] << 8 | d[i + 1]) >> (8 - (pos & 7))) & 0xFF
    pos += 8
    kind = (h >> 1) & 0x3F
    wasted = 0
    if h & 1:
        # wasted bits: unary count of zeros, then a 1 (section 9.2.2)
        q = 0
        while True:
            i = pos >> 3
            b = (d[i] << (pos & 7)) & 0xFF
            if b:
                z = int(lz[b])
                q += z
                pos += z + 1
                break
            z = 8 - (pos & 7)
            q += z
            pos += z
        wasted = q + 1
        bps -= wasted
        if bps <= 0:
            return -1
    if kind == 0:  # constant
        pos = int(read_signed(d_obj, out_obj, pos, 0, 1, bps))
        v = out[0]
        j = 1
        while j < bs:
            out[j] = v
            j += 1
    elif kind == 1:  # verbatim
        pos = int(read_signed(d_obj, out_obj, pos, 0, bs, bps))
    elif kind >= 8 and kind <= 12:  # fixed, section 9.2.5
        order = kind - 8
        if order:
            pos = int(read_signed(d_obj, out_obj, pos, 0, order, bps))
        pos = int(residual(d_obj, lz_obj, out_obj, pos, bs, order))
        if pos < 0:
            return -1
        if order:
            if order == 1:
                co[0] = 1
            elif order == 2:
                co[0] = 2
                co[1] = -1
            elif order == 3:
                co[0] = 3
                co[1] = -3
                co[2] = 1
            else:
                co[0] = 4
                co[1] = -6
                co[2] = 4
                co[3] = -1
            # sum(|c|) <= 15, so one 32-bit sum holds it up to 27-bit samples
            lpc_run(out_obj, co_obj, order, 0, bs, bps >> 1, 0)
            stats[3] += 1
    elif kind >= 32:  # LPC, section 9.2.6
        order = kind - 31
        pos = int(read_signed(d_obj, out_obj, pos, 0, order, bps))
        i = pos >> 3
        v = ((d[i] << 8 | d[i + 1]) >> (7 - (pos & 7))) & 0x1FF  # precision (4), shift (5)
        pos += 9
        prec = (v >> 5) + 1
        if prec == 16:
            return -1
        shift = v & 31
        if shift & 16:
            return -1  # negative shift
        pos = int(read_signed(d_obj, co_obj, pos, 0, order, prec))
        # Pick a predictor whose sums provably fit in 32 bits (|x| < 2**(bps-1)).
        ca = 0
        j = 0
        while j < order:
            c = co[j]
            if c < 0:
                c = 0 - c
            ca += c
            j += 1
        b = bps >> 1
        mode = -1
        if ca <= (lim >> (bps - 1)):
            mode = 0
        else:
            m = b
            if bps - 1 - b > m:
                m = bps - 1 - b
            if ca <= (lim >> m):
                if shift >= b:
                    mode = 1
                elif ca <= (lim >> (bps - 1 - shift)):
                    mode = 1
        if mode < 0:
            return -2
        pos = int(residual(d_obj, lz_obj, out_obj, pos, bs, order))
        if pos < 0:
            return -1
        lpc_run(out_obj, co_obj, order, shift, bs, b, mode)
        stats[3 + mode] += 1
    else:
        return -1
    if wasted:
        j = 0
        while j < bs:
            out[j] = out[j] << wasted
            j += 1
    return pos


# --- BEGIN GENERATED by tools/gen_turbo_lpc.py, do not edit ---


@micropython.viper
def _lpc1(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    base = uint(out)
    i = 1
    while i < n:
        q = ptr32(base + uint((i - 1) << 2))
        q[1] += (c0 * q[0]) >> shift
        i += 1


@micropython.viper
def _lpc2(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    base = uint(out)
    i = 2
    while i < n:
        q = ptr32(base + uint((i - 2) << 2))
        q[2] += (c0 * q[1] + c1 * q[0]) >> shift
        i += 1


@micropython.viper
def _lpc3(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    base = uint(out)
    i = 3
    while i < n:
        q = ptr32(base + uint((i - 3) << 2))
        q[3] += (c0 * q[2] + c1 * q[1] + c2 * q[0]) >> shift
        i += 1


@micropython.viper
def _lpc4(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    base = uint(out)
    i = 4
    while i < n:
        q = ptr32(base + uint((i - 4) << 2))
        q[4] += (c0 * q[3] + c1 * q[2] + c2 * q[1] + c3 * q[0]) >> shift
        i += 1


@micropython.viper
def _lpc5(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    base = uint(out)
    i = 5
    while i < n:
        q = ptr32(base + uint((i - 5) << 2))
        q[5] += (c0 * q[4] + c1 * q[3] + c2 * q[2] + c3 * q[1] + c4 * q[0]) >> shift
        i += 1


@micropython.viper
def _lpc6(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    base = uint(out)
    i = 6
    while i < n:
        q = ptr32(base + uint((i - 6) << 2))
        q[6] += (c0 * q[5] + c1 * q[4] + c2 * q[3] + c3 * q[2] + c4 * q[1] + c5 * q[0]) >> shift
        i += 1


@micropython.viper
def _lpc7(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    base = uint(out)
    i = 7
    while i < n:
        q = ptr32(base + uint((i - 7) << 2))
        q[7] += (
            c0 * q[6] + c1 * q[5] + c2 * q[4] + c3 * q[3] + c4 * q[2] + c5 * q[1] + c6 * q[0]
        ) >> shift
        i += 1


@micropython.viper
def _lpc8(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    base = uint(out)
    i = 8
    while i < n:
        q = ptr32(base + uint((i - 8) << 2))
        q[8] += (
            c0 * q[7]
            + c1 * q[6]
            + c2 * q[5]
            + c3 * q[4]
            + c4 * q[3]
            + c5 * q[2]
            + c6 * q[1]
            + c7 * q[0]
        ) >> shift
        i += 1


@micropython.viper
def _lpc9(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    base = uint(out)
    i = 9
    while i < n:
        q = ptr32(base + uint((i - 9) << 2))
        q[9] += (
            c0 * q[8]
            + c1 * q[7]
            + c2 * q[6]
            + c3 * q[5]
            + c4 * q[4]
            + c5 * q[3]
            + c6 * q[2]
            + c7 * q[1]
            + c8 * q[0]
        ) >> shift
        i += 1


@micropython.viper
def _lpc10(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    c9 = co[9]
    base = uint(out)
    i = 10
    while i < n:
        q = ptr32(base + uint((i - 10) << 2))
        q[10] += (
            c0 * q[9]
            + c1 * q[8]
            + c2 * q[7]
            + c3 * q[6]
            + c4 * q[5]
            + c5 * q[4]
            + c6 * q[3]
            + c7 * q[2]
            + c8 * q[1]
            + c9 * q[0]
        ) >> shift
        i += 1


@micropython.viper
def _lpc11(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    c9 = co[9]
    c10 = co[10]
    base = uint(out)
    i = 11
    while i < n:
        q = ptr32(base + uint((i - 11) << 2))
        q[11] += (
            c0 * q[10]
            + c1 * q[9]
            + c2 * q[8]
            + c3 * q[7]
            + c4 * q[6]
            + c5 * q[5]
            + c6 * q[4]
            + c7 * q[3]
            + c8 * q[2]
            + c9 * q[1]
            + c10 * q[0]
        ) >> shift
        i += 1


@micropython.viper
def _lpc12(out: ptr32, co: ptr32, shift: int, n: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    c9 = co[9]
    c10 = co[10]
    c11 = co[11]
    base = uint(out)
    i = 12
    while i < n:
        q = ptr32(base + uint((i - 12) << 2))
        q[12] += (
            c0 * q[11]
            + c1 * q[10]
            + c2 * q[9]
            + c3 * q[8]
            + c4 * q[7]
            + c5 * q[6]
            + c6 * q[5]
            + c7 * q[4]
            + c8 * q[3]
            + c9 * q[2]
            + c10 * q[1]
            + c11 * q[0]
        ) >> shift
        i += 1


@micropython.viper
def _lpcs1(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 1
    while i < n:
        q = ptr32(base + uint((i - 1) << 2))
        hs = c0 * (q[0] >> b)
        ls = c0 * (q[0] & lm)
        q[1] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs2(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 2
    while i < n:
        q = ptr32(base + uint((i - 2) << 2))
        hs = c0 * (q[1] >> b) + c1 * (q[0] >> b)
        ls = c0 * (q[1] & lm) + c1 * (q[0] & lm)
        q[2] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs3(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 3
    while i < n:
        q = ptr32(base + uint((i - 3) << 2))
        hs = c0 * (q[2] >> b) + c1 * (q[1] >> b) + c2 * (q[0] >> b)
        ls = c0 * (q[2] & lm) + c1 * (q[1] & lm) + c2 * (q[0] & lm)
        q[3] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs4(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 4
    while i < n:
        q = ptr32(base + uint((i - 4) << 2))
        hs = c0 * (q[3] >> b) + c1 * (q[2] >> b) + c2 * (q[1] >> b) + c3 * (q[0] >> b)
        ls = c0 * (q[3] & lm) + c1 * (q[2] & lm) + c2 * (q[1] & lm) + c3 * (q[0] & lm)
        q[4] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs5(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 5
    while i < n:
        q = ptr32(base + uint((i - 5) << 2))
        hs = (
            c0 * (q[4] >> b)
            + c1 * (q[3] >> b)
            + c2 * (q[2] >> b)
            + c3 * (q[1] >> b)
            + c4 * (q[0] >> b)
        )
        ls = (
            c0 * (q[4] & lm)
            + c1 * (q[3] & lm)
            + c2 * (q[2] & lm)
            + c3 * (q[1] & lm)
            + c4 * (q[0] & lm)
        )
        q[5] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs6(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 6
    while i < n:
        q = ptr32(base + uint((i - 6) << 2))
        hs = (
            c0 * (q[5] >> b)
            + c1 * (q[4] >> b)
            + c2 * (q[3] >> b)
            + c3 * (q[2] >> b)
            + c4 * (q[1] >> b)
            + c5 * (q[0] >> b)
        )
        ls = (
            c0 * (q[5] & lm)
            + c1 * (q[4] & lm)
            + c2 * (q[3] & lm)
            + c3 * (q[2] & lm)
            + c4 * (q[1] & lm)
            + c5 * (q[0] & lm)
        )
        q[6] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs7(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 7
    while i < n:
        q = ptr32(base + uint((i - 7) << 2))
        hs = (
            c0 * (q[6] >> b)
            + c1 * (q[5] >> b)
            + c2 * (q[4] >> b)
            + c3 * (q[3] >> b)
            + c4 * (q[2] >> b)
            + c5 * (q[1] >> b)
            + c6 * (q[0] >> b)
        )
        ls = (
            c0 * (q[6] & lm)
            + c1 * (q[5] & lm)
            + c2 * (q[4] & lm)
            + c3 * (q[3] & lm)
            + c4 * (q[2] & lm)
            + c5 * (q[1] & lm)
            + c6 * (q[0] & lm)
        )
        q[7] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs8(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 8
    while i < n:
        q = ptr32(base + uint((i - 8) << 2))
        hs = (
            c0 * (q[7] >> b)
            + c1 * (q[6] >> b)
            + c2 * (q[5] >> b)
            + c3 * (q[4] >> b)
            + c4 * (q[3] >> b)
            + c5 * (q[2] >> b)
            + c6 * (q[1] >> b)
            + c7 * (q[0] >> b)
        )
        ls = (
            c0 * (q[7] & lm)
            + c1 * (q[6] & lm)
            + c2 * (q[5] & lm)
            + c3 * (q[4] & lm)
            + c4 * (q[3] & lm)
            + c5 * (q[2] & lm)
            + c6 * (q[1] & lm)
            + c7 * (q[0] & lm)
        )
        q[8] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs9(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 9
    while i < n:
        q = ptr32(base + uint((i - 9) << 2))
        hs = (
            c0 * (q[8] >> b)
            + c1 * (q[7] >> b)
            + c2 * (q[6] >> b)
            + c3 * (q[5] >> b)
            + c4 * (q[4] >> b)
            + c5 * (q[3] >> b)
            + c6 * (q[2] >> b)
            + c7 * (q[1] >> b)
            + c8 * (q[0] >> b)
        )
        ls = (
            c0 * (q[8] & lm)
            + c1 * (q[7] & lm)
            + c2 * (q[6] & lm)
            + c3 * (q[5] & lm)
            + c4 * (q[4] & lm)
            + c5 * (q[3] & lm)
            + c6 * (q[2] & lm)
            + c7 * (q[1] & lm)
            + c8 * (q[0] & lm)
        )
        q[9] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs10(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    c9 = co[9]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 10
    while i < n:
        q = ptr32(base + uint((i - 10) << 2))
        hs = (
            c0 * (q[9] >> b)
            + c1 * (q[8] >> b)
            + c2 * (q[7] >> b)
            + c3 * (q[6] >> b)
            + c4 * (q[5] >> b)
            + c5 * (q[4] >> b)
            + c6 * (q[3] >> b)
            + c7 * (q[2] >> b)
            + c8 * (q[1] >> b)
            + c9 * (q[0] >> b)
        )
        ls = (
            c0 * (q[9] & lm)
            + c1 * (q[8] & lm)
            + c2 * (q[7] & lm)
            + c3 * (q[6] & lm)
            + c4 * (q[5] & lm)
            + c5 * (q[4] & lm)
            + c6 * (q[3] & lm)
            + c7 * (q[2] & lm)
            + c8 * (q[1] & lm)
            + c9 * (q[0] & lm)
        )
        q[10] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs11(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    c9 = co[9]
    c10 = co[10]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 11
    while i < n:
        q = ptr32(base + uint((i - 11) << 2))
        hs = (
            c0 * (q[10] >> b)
            + c1 * (q[9] >> b)
            + c2 * (q[8] >> b)
            + c3 * (q[7] >> b)
            + c4 * (q[6] >> b)
            + c5 * (q[5] >> b)
            + c6 * (q[4] >> b)
            + c7 * (q[3] >> b)
            + c8 * (q[2] >> b)
            + c9 * (q[1] >> b)
            + c10 * (q[0] >> b)
        )
        ls = (
            c0 * (q[10] & lm)
            + c1 * (q[9] & lm)
            + c2 * (q[8] & lm)
            + c3 * (q[7] & lm)
            + c4 * (q[6] & lm)
            + c5 * (q[5] & lm)
            + c6 * (q[4] & lm)
            + c7 * (q[3] & lm)
            + c8 * (q[2] & lm)
            + c9 * (q[1] & lm)
            + c10 * (q[0] & lm)
        )
        q[11] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def _lpcs12(out: ptr32, co: ptr32, shift: int, n: int, b: int):
    c0 = co[0]
    c1 = co[1]
    c2 = co[2]
    c3 = co[3]
    c4 = co[4]
    c5 = co[5]
    c6 = co[6]
    c7 = co[7]
    c8 = co[8]
    c9 = co[9]
    c10 = co[10]
    c11 = co[11]
    lm = (1 << b) - 1
    # ((H << u) + (L >> v)) >> w == (H * 2**b + L) >> shift, see lpc_restore_split
    u = 0
    v = b
    w = shift - b
    if shift < b:
        u = b - shift
        v = shift
        w = 0
    base = uint(out)
    i = 12
    while i < n:
        q = ptr32(base + uint((i - 12) << 2))
        hs = (
            c0 * (q[11] >> b)
            + c1 * (q[10] >> b)
            + c2 * (q[9] >> b)
            + c3 * (q[8] >> b)
            + c4 * (q[7] >> b)
            + c5 * (q[6] >> b)
            + c6 * (q[5] >> b)
            + c7 * (q[4] >> b)
            + c8 * (q[3] >> b)
            + c9 * (q[2] >> b)
            + c10 * (q[1] >> b)
            + c11 * (q[0] >> b)
        )
        ls = (
            c0 * (q[11] & lm)
            + c1 * (q[10] & lm)
            + c2 * (q[9] & lm)
            + c3 * (q[8] & lm)
            + c4 * (q[7] & lm)
            + c5 * (q[6] & lm)
            + c6 * (q[5] & lm)
            + c7 * (q[4] & lm)
            + c8 * (q[3] & lm)
            + c9 * (q[2] & lm)
            + c10 * (q[1] & lm)
            + c11 * (q[0] & lm)
        )
        q[12] += ((hs << u) + (ls >> v)) >> w
        i += 1


@micropython.viper
def lpc_run(out, co, order: int, shift: int, n: int, b: int, mode: int):
    """Predict out[order:n] in place with the unrolled function for this order
    (mode 0: one 32-bit sum, mode 1: split), or the general loop past order 12."""
    if mode == 0:
        if order == 1:
            _lpc1(out, co, shift, n)
        elif order == 2:
            _lpc2(out, co, shift, n)
        elif order == 3:
            _lpc3(out, co, shift, n)
        elif order == 4:
            _lpc4(out, co, shift, n)
        elif order == 5:
            _lpc5(out, co, shift, n)
        elif order == 6:
            _lpc6(out, co, shift, n)
        elif order == 7:
            _lpc7(out, co, shift, n)
        elif order == 8:
            _lpc8(out, co, shift, n)
        elif order == 9:
            _lpc9(out, co, shift, n)
        elif order == 10:
            _lpc10(out, co, shift, n)
        elif order == 11:
            _lpc11(out, co, shift, n)
        elif order == 12:
            _lpc12(out, co, shift, n)
        else:
            lpc_restore(out, co, order, shift, n)
    elif order == 1:
        _lpcs1(out, co, shift, n, b)
    elif order == 2:
        _lpcs2(out, co, shift, n, b)
    elif order == 3:
        _lpcs3(out, co, shift, n, b)
    elif order == 4:
        _lpcs4(out, co, shift, n, b)
    elif order == 5:
        _lpcs5(out, co, shift, n, b)
    elif order == 6:
        _lpcs6(out, co, shift, n, b)
    elif order == 7:
        _lpcs7(out, co, shift, n, b)
    elif order == 8:
        _lpcs8(out, co, shift, n, b)
    elif order == 9:
        _lpcs9(out, co, shift, n, b)
    elif order == 10:
        _lpcs10(out, co, shift, n, b)
    elif order == 11:
        _lpcs11(out, co, shift, n, b)
    elif order == 12:
        _lpcs12(out, co, shift, n, b)
    else:
        lpc_restore_split(out, co, order, shift, n, b)


# --- END GENERATED ---
