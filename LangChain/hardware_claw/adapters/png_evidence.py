"""Validate complete, bounded PNG evidence using its chunks and image stream."""
import base64
import binascii
import struct
import zlib

MAX_BYTES = 16 * 1024 * 1024


def decode_png(encoded):
    if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES * 4 // 3 + 4):
        raise ValueError("PNG exceeds output limit")
    data = base64.b64decode(encoded, validate=True)
    return data, png_info(data)


def png_info(data):
    if len(data) > MAX_BYTES or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("Invalid PNG signature or size")
    pos, chunks, compressed = 8, [], bytearray()
    header = None
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        length = struct.unpack('>I', data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]
        end = pos+12+length
        if end > len(data):
            raise ValueError("Truncated PNG data")
        payload = data[pos+8:pos+8+length]
        crc = struct.unpack('>I', data[end-4:end])[0]
        if binascii.crc32(kind+payload) & 0xffffffff != crc:
            raise ValueError("PNG CRC mismatch")
        if kind == b'IHDR':
            if chunks or length != 13:
                raise ValueError("Invalid PNG header")
            header = struct.unpack('>IIBBBBB', payload)
        if kind == b'IDAT':
            compressed.extend(payload)
        chunks.append(kind)
        pos = end
        if kind == b'IEND':
            if length or pos != len(data):
                raise ValueError("Invalid PNG end")
            break
    if not header or not chunks or chunks[-1] != b'IEND' or not compressed:
        raise ValueError("Incomplete PNG")
    width, height, depth, color, compression, filtering, interlace = header
    channels = {0:1, 2:3, 3:1, 4:2, 6:4}.get(color)
    if not width or not height or width*height > 4_194_304 or not channels or compression or filtering or interlace:
        raise ValueError("Unsupported PNG format or dimensions")
    allowed_depths = {0:{1,2,4,8,16},2:{8,16},3:{1,2,4,8},4:{8,16},6:{8,16}}
    if depth not in allowed_depths[color]:
        raise ValueError("Invalid PNG depth")
    row = (width*channels*depth+7)//8 + 1
    expected = row*height
    if expected > MAX_BYTES:
        raise ValueError("Decoded PNG exceeds limit")
    decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(bytes(compressed), expected+1)
    except zlib.error as exc:
        raise ValueError("Invalid PNG compression stream") from exc
    if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Incomplete or oversized PNG pixel stream")
    if any(pixels[y*row] > 4 for y in range(height)):
        raise ValueError("Invalid PNG row filter")
    return {"mime_type":"image/png", "width":width, "height":height, "bytes":len(data), "complete":True}
