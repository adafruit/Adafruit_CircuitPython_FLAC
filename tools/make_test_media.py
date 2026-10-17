# SPDX-FileCopyrightText: Copyright (c) 2026 Mikey Sklar for Adafruit Industries
# SPDX-License-Identifier: MIT
"""Make the FLAC test clips in media/ and their reference decodes.

Source music is a CC0 recording of Bach, BWV 147 (Musopen, from Wikimedia Commons:
https://commons.wikimedia.org/wiki/File:Bach,_BWV_147,_10._Jesus_bleibet_meine_Freude.ogg).
It is downloaded to media/source.ogg on first use; set FLAC_SOURCE to use another file.
Needs ``flac`` and ``ffmpeg`` on the PATH.
Clips are encoded with libFLAC (the ``flac`` CLI) and with ffmpeg, so both
encoders' choices are covered. Each clip gets a ``.ref.wav`` reference decoded by
``flac -d``.

usage: python3 tools/make_test_media.py [seconds]

Set FLAC_MEDIA to write somewhere else (tools/install.sh uses 3 s clips).
"""

import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.environ.get("FLAC_MEDIA") or os.path.join(HERE, "media")
SRC = os.environ.get("FLAC_SOURCE") or os.path.join(MEDIA, "source.ogg")
SRC_URL = (
    "https://commons.wikimedia.org/wiki/Special:FilePath/"
    "Bach,_BWV_147,_10._Jesus_bleibet_meine_Freude.ogg"
)
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 10
START = 30  # skip the quiet intro

# name, rate, channels, bits, encoder, encoder args, ffmpeg filter
CLIPS = (
    # the benchmark set, matching the dr_flac bare-metal table
    ("s16_44k_l5", 44100, 2, 16, "flac", ["-5"], None),
    ("s16_44k_l8", 44100, 2, 16, "flac", ["-8"], None),
    ("s24_48k_l8n", 48000, 2, 24, "flac", ["-8"], "noise"),
    ("s24_96k_l5", 96000, 2, 24, "flac", ["-5"], None),
    ("s24_96k_l8n", 96000, 2, 24, "flac", ["-8"], "noise"),
    # low rates, where Python has a chance
    ("m16_22k_l5", 22050, 1, 16, "flac", ["-5"], None),
    ("m16_11k_l5", 11025, 1, 16, "flac", ["-5"], None),
    ("m16_8k_l5", 8000, 1, 16, "flac", ["-5"], None),
    ("s16_22k_l5", 22050, 2, 16, "flac", ["-5"], None),
    # edge cases for correctness
    ("s16_44k_ff", 44100, 2, 16, "ffmpeg", ["-compression_level", "12"], None),
    ("s24_96k_ff", 96000, 2, 24, "ffmpeg", ["-compression_level", "8"], "noise"),
    ("s16_44k_l0", 44100, 2, 16, "flac", ["-0"], None),
    ("s16_44k_lpc32", 44100, 2, 16, "flac", ["--lax", "-l", "32", "-b", "4608"], None),
    ("s16_44k_b192", 44100, 2, 16, "flac", ["-b", "192"], None),
    ("s16_44k_vbs", 44100, 2, 16, "flac", ["-b", "1000"], None),
    ("m8_22k", 22050, 1, 8, "flac", ["-5"], None),
    ("m12_22k", 22050, 1, 12, "flac", ["-5"], None),
    ("s20_48k", 48000, 2, 20, "flac", ["-8"], "noise"),
    ("s32_48k", 48000, 2, 32, "flac", ["-5"], "noise"),
    ("s24_44k_wasted", 44100, 2, 24, "flac", ["-5"], "pad8"),
    ("s16_44k_silence", 44100, 2, 16, "flac", ["-5"], "silence"),
    ("q16_44k", 44100, 4, 16, "flac", ["-5"], None),
)

FMT = {8: "s8", 12: "s16", 16: "s16", 20: "s32", 24: "s32", 32: "s32"}


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reduce_wav(wav, bits, ch, rate):
    data = open(wav, "rb").read()
    i = data.index(b"data") + 8
    cont = 16 if bits == 12 else 24
    step = cont // 8
    keep = ~((1 << (cont - bits)) - 1)
    pcm = bytearray()
    for j in range(i, len(data) - step + 1, step):
        v = int.from_bytes(data[j : j + step], "little", signed=True) & keep
        pcm += v.to_bytes(step, "little", signed=True)
    fmt = struct.pack(
        "<HHIIHHHHIH14s",
        0xFFFE,
        ch,
        rate,
        rate * ch * step,
        ch * step,
        cont,
        22,
        bits,
        0,
        1,
        b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71",
    )
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(pcm))
        + pcm
    )
    open(wav, "wb").write(b"RIFF" + struct.pack("<I", len(body)) + body)


def main():
    os.makedirs(MEDIA, exist_ok=True)
    if not os.path.exists(SRC):
        print("downloading", SRC_URL)
        subprocess.run(
            ["curl", "-sSfL", "-A", "adafruit_flac test media", "-o", SRC, SRC_URL], check=True
        )
    for name, rate, ch, bits, enc, args, filt in CLIPS:
        out = os.path.join(MEDIA, name + ".flac")
        wav = os.path.join(MEDIA, name + ".wav")
        af = ["aresample=%d" % rate]
        if ch == 1:
            af.append("pan=mono|c0=0.5*c0+0.5*c1")
        elif ch == 4:
            af.append("pan=4.0|c0=c0|c1=c1|c2=0.5*c0|c3=0.5*c1")
        if filt == "noise":
            # -96 dBFS white noise mimics a hi-res noise floor
            af.append("volume=0.9")
        if filt == "silence":
            af.append("volume=0")
        cmd = ["ffmpeg", "-y", "-ss", str(START), "-t", str(SECONDS), "-i", SRC]
        if filt == "noise":
            cmd += [
                "-f",
                "lavfi",
                "-t",
                str(SECONDS),
                "-i",
                "anoisesrc=a=0.0000158:c=white:r=%d" % rate,
                "-filter_complex",
                "[0:a]%s[m];[1:a]aformat=channel_layouts=%s[n];[m][n]amix=inputs=2:normalize=0"
                % (",".join(af), "mono" if ch == 1 else "stereo"),
            ]
        else:
            cmd += ["-af", ",".join(af)]
        if filt == "pad8":
            # 16-bit audio in a 24-bit file: every sample has 8 wasted bits
            cmd += ["-sample_fmt", "s16", "-ac", str(ch), wav + ".16.wav"]
            run(cmd)
            run(["ffmpeg", "-y", "-i", wav + ".16.wav", "-c:a", "pcm_s24le", wav])
            os.remove(wav + ".16.wav")
        elif bits in (12, 20):
            # make a wav at the container depth, then let flac reduce it
            cmd += ["-c:a", "pcm_s%dle" % (16 if bits == 12 else 24), "-ac", str(ch), wav]
            run(cmd)
        else:
            codec = {8: "pcm_u8", 16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}[bits]
            cmd += ["-c:a", codec, "-ac", str(ch), wav]
            run(cmd)
        if enc == "flac":
            if bits in (12, 20):
                # rewrite as WAVE_FORMAT_EXTENSIBLE with fewer valid bits so
                # flac stores the reduced depth in STREAMINFO
                _reduce_wav(wav, bits, ch, rate)
            run(["flac", "-f", "-s"] + args + ["-o", out, wav])
        else:
            run(["ffmpeg", "-y", "-i", wav, "-c:a", "flac"] + args + [out])
        os.remove(wav)
        # flac writes 12/20-bit samples left-justified in 16/24-bit WAV slots
        ref = os.path.join(MEDIA, name + ".ref.wav")
        run(["flac", "-d", "-f", "-s", "-o", ref, out])
        print("%-18s %7d bytes" % (name, os.path.getsize(out)))


if __name__ == "__main__":
    main()
