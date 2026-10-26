"""Windows-only direct motor diagnostic. Close Live and keep hands clear.

Explicitly run: python tools/motor_probe.py --run --port "PreSonus FP2"
Sends only channel-0 pitch bend to 25%, 75%, then 0%; no transport messages.
"""

import argparse
import ctypes
from ctypes import wintypes
import time

from midi_probe import ports, winmm
from FaderPort_Follow.protocol import fader_message


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--port", default="PreSonus FP2")
    parser.add_argument("--reference-startup", action="store_true",
                        help="Precede test with the startup CC pair used by ReaSonus native")
    parser.add_argument("--check-led", action="store_true",
                        help="Flash Channel LED during the test to verify direct output delivery")
    args = parser.parse_args()
    dll = winmm()
    outputs = [port for port in ports(dll)["outputs"] if port["name"] == args.port]
    if len(outputs) != 1:
        parser.error("Expected exactly one output matching the exact port name: " + args.port)
    dll.midiOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
                               ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
    dll.midiOutOpen.restype = wintypes.UINT
    dll.midiOutShortMsg.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    dll.midiOutShortMsg.restype = wintypes.UINT
    dll.midiOutClose.argtypes = [ctypes.c_void_p]
    dll.midiOutClose.restype = wintypes.UINT
    dll.midiOutGetErrorTextW.argtypes = [wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]

    def check(result):
        if result:
            message = ctypes.create_unicode_buffer(256)
            dll.midiOutGetErrorTextW(result, message, len(message))
            raise RuntimeError("WinMM %s: %s" % (result, message.value))

    handle = ctypes.c_void_p()
    check(dll.midiOutOpen(ctypes.byref(handle), outputs[0]["index"], 0, 0, 0))
    try:
        print("Output: " + args.port, flush=True)
        def send(message):
            packed = sum(byte << (index * 8) for index, byte in enumerate(message))
            check(dll.midiOutShortMsg(handle, packed))

        def keep_alive_for(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                send((0xA0, 0x00, 0x00))
                time.sleep(0.25)

        print("Native keepalive: A0 00 00", flush=True)
        if args.reference_startup:
            send((0xB0, 0x00, 0x06))
            send((0xB0, 0x20, 0x27))
            print("Reference startup: B0 00 06 / B0 20 27", flush=True)
        if args.check_led:
            send((0x90, 0x36, 0x01))
            print("Channel LED flashing while test runs", flush=True)
        keep_alive_for(1)
        for position in (0.25, 0.75, 0.0):
            message = fader_message(position)
            send(message)
            print("%d%%: %s (WinMM accepted)" % (position * 100, " ".join("%02X" % b for b in message)), flush=True)
            keep_alive_for(2)
        if args.check_led:
            send((0x90, 0x36, 0x00))
            print("Channel LED off", flush=True)
    finally:
        check(dll.midiOutClose(handle))


if __name__ == "__main__":
    main()
