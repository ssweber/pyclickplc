"""What the running Python does to a signalling float32 NaN, for tests that pin its registers."""

import struct

_SIGNALLING_NAN = b"\x01\x00\x80\x7f"

# True if a signalling float32 NaN keeps its bits on the way to a Python float and back. Python
# 3.14 keeps them; 3.11 to 3.13 and 3.15 set the quiet bit.
KEEPS_SIGNALLING_NAN = struct.pack("<f", struct.unpack("<f", _SIGNALLING_NAN)[0]) == _SIGNALLING_NAN
