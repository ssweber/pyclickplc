"""Report whether this Python keeps the bits of a signalling float32 NaN.

Tests that check the exact register words of a signalling NaN use the answer.
"""

import struct

_SIGNALLING_NAN = b"\x01\x00\x80\x7f"

# True if a signalling float32 NaN keeps its bits when it becomes a Python float and back.
# Python 3.14 keeps them. Python 3.11 to 3.13 and 3.15 set the quiet bit.
KEEPS_SIGNALLING_NAN = struct.pack("<f", struct.unpack("<f", _SIGNALLING_NAN)[0]) == _SIGNALLING_NAN
