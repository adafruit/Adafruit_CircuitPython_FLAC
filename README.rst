Introduction
============


.. image:: https://readthedocs.org/projects/adafruit-circuitpython-flac/badge/?version=latest
    :target: https://docs.circuitpython.org/projects/flac/en/latest/
    :alt: Documentation Status


.. image:: https://raw.githubusercontent.com/adafruit/Adafruit_CircuitPython_Bundle/main/badges/adafruit_discord.svg
    :target: https://adafru.it/discord
    :alt: Discord


.. image:: https://github.com/adafruit/Adafruit_CircuitPython_FLAC/workflows/Build%20CI/badge.svg
    :target: https://github.com/adafruit/Adafruit_CircuitPython_FLAC/actions
    :alt: Build Status


.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
    :target: https://github.com/astral-sh/ruff
    :alt: Code Style: Ruff

Play FLAC files on CircuitPython. ``FLACDecoder`` decodes FLAC (lossless) audio to 16-bit PCM,
and ``FLACPlayer`` streams it to an ``I2SOut``, ``PWMAudioOut`` or ``AudioOut`` while your code
keeps running. On an RP2350 it plays 16-bit/44.1 kHz and 24-bit/96 kHz files from a microSD
card at the stock 150 MHz.

The decoder is written from RFC 9639 and decodes bit-exact. Its hot loops run in a turbo
(``@micropython.viper``) kernel, prebuilt for each chip architecture.


Dependencies
=============
This library depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_ 11 or later, on a board
  that can load native ``.mpy`` files (``microcontroller.cpu.architecture`` is not ``None``)

The decoding loops are a precompiled kernel, one file per architecture:

======================  =============================================
``flac_kernel`` file    Boards
======================  =============================================
``armv6m``              RP2040
``armv7emsp``           SAMD51 (M4), nRF52840, RP2350, STM32F4
``xtensawin``           ESP32-S2, ESP32-S3
``rv32imc``             ESP32-C3, C5, C6
======================  =============================================

Without a kernel the decoder falls back to plain Python, which is correct but far slower than
real time for music. Only the RP2350 has been tested for playback.

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_
or individual libraries can be installed using
`circup <https://github.com/adafruit/circup>`_.

Installing to a Connected CircuitPython Device with Circup
==========================================================

Make sure that you have ``circup`` installed in your Python environment.
Install it with the following command if necessary:

.. code-block:: shell

    pip3 install circup

With ``circup`` installed and your CircuitPython device connected use the
following command to install:

.. code-block:: shell

    circup install adafruit_flac

Or the following command to update an existing version:

.. code-block:: shell

    circup update

Usage Example
=============

.. code-block:: python

    import adafruit_flac
    from adafruit_fruitjam.peripherals import Peripherals

    decoder = adafruit_flac.FLACDecoder("song.flac")
    fruit_jam = Peripherals(audio_output="headphone", sample_rate=decoder.sample_rate)

    player = adafruit_flac.FLACPlayer(fruit_jam.audio)
    player.play(decoder)
    while player.playing:
        player.update()  # decode the next piece; call this often while playing

Speed and memory
================

Measured on an Adafruit Fruit Jam (RP2350B). Load is decode time divided by audio time; under
100% keeps up.

=========================  ===========  ===========
Format                     150 MHz      300 MHz
=========================  ===========  ===========
16-bit, 44.1 kHz stereo    30%          15%
24-bit, 96 kHz stereo      89%          46%
=========================  ===========  ===========

- Keep the decoder and the audio buffer in internal SRAM. On the RP2350, decoding into PSRAM
  nearly doubled the load at 96 kHz. Create them first in ``code.py``, before other large
  allocations, or pass a preallocated ``array("h")`` as ``FLACPlayer(audio, buffer=...)``.
- ``FLACPlayer`` decodes straight into the half of its buffer that the audio DMA has already
  copied, so it does not work with ``audiomixer``, which reads the buffer in place.
- At 24/96 the decoder uses about 83 KB and a 64 ms double buffer 48 KB (plus the output's own
  DMA buffers).
- ``examples/flac_fruitjam_sd_hires.py`` plays 24/96 from the Fruit Jam's microSD card over
  4-bit SDIO.

Building the kernel
===================

``src/flac_turbo.py`` is the kernel source, turbo (``@micropython.viper``) functions.
``tools/gen_turbo_lpc.py`` writes the unrolled predictors into it. ``src/Makefile`` compiles it
with ``mpy-cross -march`` for each architecture into ``adafruit_flac/flac_kernel.<arch>.mpy``:

.. code-block:: shell

    cd src
    make MPY_CROSS=path/to/circuitpython/mpy-cross/build/mpy-cross

Use an ``mpy-cross`` from the CircuitPython version the files will run on.

Testing
=======

``tools/make_test_media.py`` builds test clips (it downloads a CC0 recording and needs ``flac``
and ``ffmpeg``). ``tests/test_decoder.py`` checks the plain Python decoder against libFLAC under
CPython, ``tests/test_kernel_model.py`` runs the same with a CPython model of the kernel that
fails on any 32-bit overflow, and ``tools/turbo_check.py`` compares the kernel with the plain
Python path on a board.

Documentation
=============
API documentation for this library can be found on `Read the Docs <https://docs.circuitpython.org/projects/flac/en/latest/>`_.

For information on building library documentation, please check out
`this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/adafruit/Adafruit_CircuitPython_FLAC/blob/HEAD/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.
