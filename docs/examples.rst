Simple test
------------

Ensure your device works with this simple test. It plays ``song.flac`` from CIRCUITPY through
the Fruit Jam headphone jack.

.. literalinclude:: ../examples/flac_simpletest.py
    :caption: examples/flac_simpletest.py
    :linenos:

Fruit Jam microSD playlist
--------------------------

Plays every FLAC file on the microSD card, using the card mount CircuitPython sets up.

.. literalinclude:: ../examples/flac_fruitjam_sd_playlist.py
    :caption: examples/flac_fruitjam_sd_playlist.py
    :linenos:

Fruit Jam 24-bit/96 kHz from microSD
------------------------------------

Reads the card over 4-bit SDIO and keeps every buffer in internal SRAM, for high resolution
files.

.. literalinclude:: ../examples/flac_fruitjam_sd_hires.py
    :caption: examples/flac_fruitjam_sd_hires.py
    :linenos:

Feather with a MAX98357A I2S amp
--------------------------------

Plays ``song.flac`` through a mono I2S amp and speaker on any Feather, at a lower ``level``.

.. literalinclude:: ../examples/flac_feather_i2s_amp_max98357a.py
    :caption: examples/flac_feather_i2s_amp_max98357a.py
    :linenos:
