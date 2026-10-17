# SPDX-FileCopyrightText: Copyright (c) 2026 Mikey Sklar for Adafruit Industries
# SPDX-License-Identifier: MIT
"""Play an album of FLAC files from the Fruit Jam's microSD card, up to 24-bit/96 kHz.

Reads the card over 4-bit SDIO instead of the SPI mount that CircuitPython and
Peripherals use. Needs CIRCUITPY_SDCARD_USB = false in settings.toml so the card is free
for SDIO; a card that was used over SPI needs a power cycle first. 88.2/96 kHz needs an
adafruit_tlv320 with those clock settings.
"""

import microcontroller

microcontroller.cpu.frequency = 150_000_000  # set first; 300_000_000 for more headroom

import os  # noqa: E402
from array import array  # noqa: E402

import audiobusio  # noqa: E402
import audiocore  # noqa: E402
import board  # noqa: E402
import displayio  # noqa: E402
import neopixel  # noqa: E402
import pwmio  # noqa: E402
import sdioio  # noqa: E402
import storage  # noqa: E402

RATE = 96000
ALBUM = "/sd/music"
VOLUME = 0.5

displayio.release_displays()
neopixel.NeoPixel(board.NEOPIXEL, 5).fill(0)  # LED switching is audible on headphones

# Order matters: import the decoder and allocate the audio buffers while internal
# RAM is free. Writing decoded audio to PSRAM is too slow for 24/96.
import adafruit_flac  # noqa: E402

half = RATE * 64 // 1000 * 2  # 64 ms of stereo samples
out_buf = array("h", [0]) * (2 * half)
audio = audiobusio.I2SOut(board.I2S_BCLK, board.I2S_WS, board.I2S_DIN)
audio.play(
    audiocore.RawSample(out_buf, channel_count=2, sample_rate=RATE, single_buffer=False),
    loop=True,
)
audio.stop()  # keeps the DMA buffers reserved

sd = sdioio.SDCard(
    clock=board.SDIO_CLOCK, command=board.SDIO_COMMAND, data=board.SDIO_DATA, frequency=40_000_000
)
storage.mount(storage.VfsFat(sd), "/sd")
tracks = sorted(
    ALBUM + "/" + n for n in os.listdir(ALBUM) if n.endswith(".flac") and not n.startswith(".")
)
decoder = adafruit_flac.FLACDecoder(tracks[0])  # reused for every track

import adafruit_tlv320  # noqa: E402

mclk = pwmio.PWMOut(board.I2S_MCLK, frequency=15_000_000, duty_cycle=2**15)
dac = adafruit_tlv320.TLV320DAC3100(board.I2C())
dac.configure_clocks(sample_rate=RATE, bit_depth=16, mclk_freq=mclk.frequency)
dac.headphone_output = True
dac.speaker_output = False
dac.dac_volume = -63 + VOLUME * 86

player = adafruit_flac.FLACPlayer(audio, buffer=out_buf)
while True:
    for path in tracks:
        decoder.open(path)
        if decoder.sample_rate != RATE:
            continue
        print("Playing", path)
        player.play(decoder)
        while player.playing:
            player.update()
