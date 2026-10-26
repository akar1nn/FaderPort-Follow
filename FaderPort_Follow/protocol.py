"""PreSonus FaderPort V2, Studio One native protocol, manual section 8.2.

Only channel 0 is input. RGB messages on channels 1-3 are output only.
The manual calls the encoder sign 'bit 7'; MIDI data is 7-bit, so signed-bit
encoding uses 0x40 as the direction bit (0x01 right, 0x41 left). The format
is configurable for firmware verification; diagnostics preserve the raw bytes.
"""

ARM = 0x00
BYPASS = 0x03
LINK = 0x05
SOLO = 0x08
MUTE = 0x10
ENCODER_PUSH = 0x20
PAN = 0x2A
PREV = 0x2E
NEXT = 0x2F
CHANNEL = 0x36
SCROLL = 0x38
MASTER = 0x3A
CLICK = 0x3B
SECTION = 0x3C
MARKER = 0x3D
SHIFT = 0x46
READ = 0x4A
WRITE = 0x4B
TOUCH = 0x4D
LOOP = 0x56
REWIND = 0x5B
FORWARD = 0x5C
STOP = 0x5D
PLAY = 0x5E
RECORD = 0x5F
FOOTSWITCH = 0x66
FADER_TOUCH = 0x68
ENCODER_CC = 0x3C
# FP2 firmware uses CC 0x10 as well as the documented 0x3C variant.
ENCODER_CCS = (0x10, ENCODER_CC)
NATIVE_KEEPALIVE = (0xA0, 0x00, 0x00)
# Startup CC pair used by ReaSonus' native FP2 implementation and included
# in the successful observed duplex motor test. This is not a factory reset.
NATIVE_STARTUP = ((0xB0, 0x00, 0x06), (0xB0, 0x20, 0x27))

BUTTONS = (ARM, BYPASS, LINK, SOLO, MUTE, ENCODER_PUSH, PAN, PREV, NEXT,
           CHANNEL, SCROLL, MASTER, CLICK, SECTION, MARKER, SHIFT, READ,
           WRITE, TOUCH, LOOP, REWIND, FORWARD, STOP, PLAY, RECORD,
           FOOTSWITCH, FADER_TOUCH)
LEDS = tuple(note for note in BUTTONS
             if note not in (ENCODER_PUSH, FOOTSWITCH, FADER_TOUCH))
RGB = {LINK: (0, 90, 100), PAN: (127, 65, 0), CHANNEL: (0, 50, 127),
       SCROLL: (80, 0, 127), READ: (0, 127, 0), WRITE: (127, 0, 0),
       TOUCH: (127, 65, 0)}
NAMES = {value: name for name, value in tuple(globals().items())
         if name.isupper() and isinstance(value, int) and name != "ENCODER_CC"}


def encoder_delta(value, encoding="signed_bit"):
    if encoding == "signed_bit":
        return -(value & 0x3F) if value & 0x40 else value
    if encoding == "twos_complement":
        return value - 128 if value >= 64 else value
    if encoding == "binary_offset":
        return value - 64
    raise ValueError("Unknown ENCODER_FORMAT: " + str(encoding))


def decode(message, encoding="signed_bit", invert=False):
    """Return (kind, identifier, value), or None for unrelated/invalid MIDI."""
    if len(message) != 3:
        return None
    status, data1, data2 = message
    if not all(isinstance(b, int) for b in message):
        return None
    if not (0 <= data1 < 128 and 0 <= data2 < 128):
        return None
    if status in (0x80, 0x90) and data1 in BUTTONS:
        return ("button", data1, status == 0x90 and data2 != 0)
    if status == 0xE0:
        return ("fader", None, data1 | (data2 << 7))
    if status == 0xB0 and data1 in ENCODER_CCS:
        delta = encoder_delta(data2, encoding)
        return ("encoder", None, -delta if invert else delta)
    return None


def fader_message(normalized):
    value = int(round(max(0.0, min(1.0, normalized)) * 16383))
    return (0xE0, value & 0x7F, value >> 7)


def led_message(note, state):
    # state: 0 off, 1 on, 2 flashing (the wire values are 0, 127, 1).
    return (0x90, note, (0, 127, 1)[state])


def color_messages(note, color):
    return tuple((0x91 + channel, note, level)
                 for channel, level in enumerate(color))


def describe(message):
    raw = " ".join("%02X" % byte for byte in message)
    event = decode(message)
    if not event:
        return raw + " (unmapped)"
    kind, identifier, value = event
    return "%s %s %s %s" % (raw, kind, NAMES.get(identifier, ""), value)

