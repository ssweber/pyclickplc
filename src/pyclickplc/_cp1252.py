"""The cp1252 codec of the nickname CSV, the check for a character that it cannot hold, and
the map between a TXT byte and its character.

This module imports no other module of pyclickplc. Importing it registers the codec.
"""

from __future__ import annotations

import codecs
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer

# The encoding of the nickname CSV that CLICK exports and that write_csv writes. It is
# Windows code page 1252. Python's cp1252 codec has no character for the five bytes 0x81,
# 0x8D, 0x8F, 0x90 and 0x9D. Windows maps each of them to the control character with the same
# number. CLICK was observed to store U+0081 in a nickname and to export it as the byte 0x81.
# CSV_ENCODING names a codec that is Python's cp1252 with those five bytes added. Importing
# this module registers the codec.
CSV_ENCODING = "pyclickplc_cp1252"
"""The name of the codec that `read_csv` and `write_csv` use for the nickname CSV."""

_CP1252_DECODING_TABLE = "".join(
    bytes([byte]).decode("cp1252", errors="ignore") or chr(byte) for byte in range(256)
)
_CP1252_ENCODING_TABLE = codecs.charmap_build(_CP1252_DECODING_TABLE)


class _Cp1252Codec(codecs.Codec):
    def encode(self, input: str, errors: str = "strict") -> tuple[bytes, int]:
        return codecs.charmap_encode(input, errors, _CP1252_ENCODING_TABLE)

    def decode(self, input: ReadableBuffer, errors: str = "strict") -> tuple[str, int]:
        return codecs.charmap_decode(input, errors, _CP1252_DECODING_TABLE)


class _Cp1252IncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, input: str, final: bool = False) -> bytes:
        return codecs.charmap_encode(input, self.errors, _CP1252_ENCODING_TABLE)[0]


class _Cp1252IncrementalDecoder(codecs.IncrementalDecoder):
    def decode(self, input: ReadableBuffer, final: bool = False) -> str:
        return codecs.charmap_decode(input, self.errors, _CP1252_DECODING_TABLE)[0]


class _Cp1252StreamWriter(_Cp1252Codec, codecs.StreamWriter):
    pass


class _Cp1252StreamReader(_Cp1252Codec, codecs.StreamReader):
    pass


def _find_cp1252(name: str) -> codecs.CodecInfo | None:
    if name != CSV_ENCODING:
        return None
    return codecs.CodecInfo(
        name=CSV_ENCODING,
        encode=_Cp1252Codec().encode,
        decode=_Cp1252Codec().decode,
        incrementalencoder=_Cp1252IncrementalEncoder,
        incrementaldecoder=_Cp1252IncrementalDecoder,
        streamwriter=_Cp1252StreamWriter,
        streamreader=_Cp1252StreamReader,
    )


codecs.register(_find_cp1252)


def first_non_cp1252_char(text: str) -> str | None:
    """Return the first character in *text* that cp1252 does not have, or None.

    A nickname CSV is cp1252, so it cannot hold that character. Here cp1252
    means Windows code page 1252. Unlike Python's ``cp1252`` codec, it has
    U+0081, U+008D, U+008F, U+0090 and U+009D. ``format_csv``
    and ``write_csv`` raise ``ValueError`` for a nickname, comment or initial
    value that has one. ``validate_nickname`` and ``validate_comment`` reject
    a nickname or comment that has one. An editor can call this function to
    flag the cell before it saves.
    """
    try:
        text.encode(CSV_ENCODING)
    except UnicodeEncodeError as exc:
        return text[exc.start]
    return None


# A CLICK TXT address holds one byte. A PLC stores the cp1252 byte for a text constant. So
# pyclickplc maps each TXT byte to the character that CSV_ENCODING decodes it to.
def txt_byte_to_char(byte: int) -> str:
    """Return the character for the TXT byte *byte*.

    Raises:
        ValueError: *byte* is not in 0..255.
    """
    if not 0 <= byte <= 0xFF:
        raise ValueError(f"TXT byte {byte} is not in 0..255")
    return _CP1252_DECODING_TABLE[byte]


def txt_char_to_byte(char: str) -> int | None:
    """Return the TXT byte for the one character *char*, or None if cp1252 does not have it.

    Return None too if *char* is not one character.
    """
    if len(char) != 1:
        return None
    try:
        return char.encode(CSV_ENCODING)[0]
    except UnicodeEncodeError:
        return None
