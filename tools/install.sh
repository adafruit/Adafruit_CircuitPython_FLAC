#!/bin/sh
# SPDX-FileCopyrightText: Copyright (c) 2026 Mikey Sklar for Adafruit Industries
# SPDX-License-Identifier: MIT
#
# Copy adafruit_flac, 3 s test clips (to /flac) and optionally one
# script (as code.py) to a mounted CIRCUITPY drive. An existing code.py is
# kept as code.py.bak.
#
# usage: tools/install.sh /Volumes/CIRCUITPY [script]
#   script: turbo_check (from tools/), or an example name such as
#   flac_simpletest (from examples/)
#
# Check boot_out.txt first when several boards are plugged in: CIRCUITPY
# volume names get renumbered.
set -e
dest="$1"
example="$2"
here="$(cd "$(dirname "$0")/.." && pwd)"
[ -d "$dest" ] || { echo "usage: $0 /path/to/CIRCUITPY [example]"; exit 1; }
[ -d "$here/media-device" ] || FLAC_MEDIA="$here/media-device" python3 "$here/tools/make_test_media.py" 3

mkdir -p "$dest/lib" "$dest/flac"
rm -rf "$dest/lib/adafruit_flac"
cp -R "$here/adafruit_flac" "$dest/lib/"
for f in s16_44k_l5 s16_44k_l8 s24_48k_l8n s24_96k_l5 s24_96k_l8n \
         m16_22k_l5 m16_11k_l5 m16_8k_l5 s16_22k_l5; do
    cp "$here/media-device/$f.flac" "$dest/flac/$f.flac"
done
if [ -n "$example" ]; then
    src="$here/tools/$example.py"
    [ -f "$src" ] || src="$here/examples/$example.py"
    [ -f "$src" ] || { echo "no script $example in tools/ or examples/"; exit 1; }
    [ -f "$dest/code.py" ] && cp "$dest/code.py" "$dest/code.py.bak"
    cp "$src" "$dest/code.py"
fi
sync
echo "installed adafruit_flac ${example:+and $example as code.py }on $dest"
