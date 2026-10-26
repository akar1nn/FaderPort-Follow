"""Dependency-free Windows MIDI input inventory and raw capture (no MIDI output).

Usage: python tools/midi_probe.py --list
       python tools/midi_probe.py --capture 0 --seconds 45 --output tmp/native.jsonl
Close Live before capture so it does not hold the Windows input port open.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from FaderPort_Follow.protocol import describe


class MidiCaps(ctypes.Structure):
    _fields_ = [("manufacturer", wintypes.WORD), ("product", wintypes.WORD),
                ("version", wintypes.DWORD), ("name", wintypes.WCHAR * 32),
                ("support", wintypes.DWORD)]


class MidiOutCaps(ctypes.Structure):
    _fields_ = [("manufacturer", wintypes.WORD), ("product", wintypes.WORD),
                ("version", wintypes.DWORD), ("name", wintypes.WCHAR * 32),
                ("technology", wintypes.WORD), ("voices", wintypes.WORD),
                ("notes", wintypes.WORD), ("channels", wintypes.WORD),
                ("support", wintypes.DWORD)]


def winmm():
    if sys.platform != "win32":
        raise RuntimeError("This probe uses Windows WinMM. On macOS use DEBUG_MIDI in Live.")
    dll = ctypes.WinDLL("winmm")
    for direction, caps in (("In", MidiCaps), ("Out", MidiOutCaps)):
        get_caps = getattr(dll, "midi%sGetDevCapsW" % direction)
        get_caps.argtypes = [ctypes.c_size_t, ctypes.POINTER(caps), wintypes.UINT]
        get_caps.restype = wintypes.UINT
        getattr(dll, "midi%sGetNumDevs" % direction).restype = wintypes.UINT
    dll.midiInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
                              ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
    dll.midiInOpen.restype = wintypes.UINT
    for name in ("midiInStart", "midiInStop", "midiInReset", "midiInClose"):
        function = getattr(dll, name)
        function.argtypes = [ctypes.c_void_p]
        function.restype = wintypes.UINT
    dll.midiInGetErrorTextW.argtypes = [wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    return dll


def check(dll, result):
    if result:
        message = ctypes.create_unicode_buffer(256)
        dll.midiInGetErrorTextW(result, message, len(message))
        raise RuntimeError("WinMM %s: %s" % (result, message.value))


def ports(dll):
    result = {"inputs": [], "outputs": []}
    for direction, key, caps_type in (("In", "inputs", MidiCaps), ("Out", "outputs", MidiOutCaps)):
        for index in range(getattr(dll, "midi%sGetNumDevs" % direction)()):
            caps = caps_type()
            check(dll, getattr(dll, "midi%sGetDevCapsW" % direction)(index, ctypes.byref(caps), ctypes.sizeof(caps)))
            result[key].append({"index": index, "name": caps.name})
    return result


def capture(dll, index, seconds, output):
    events = queue.Queue()
    callback_type = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, wintypes.UINT,
                                      ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t)

    def on_midi(handle, message, instance, packed, timestamp):
        if message in (0x3C3, 0x3CC):  # MIM_DATA / MIM_MOREDATA
            raw = [(packed >> (8 * byte)) & 0xFF for byte in range(3)]
            events.put({"milliseconds": timestamp, "bytes": raw})

    callback = callback_type(on_midi)  # Keep it alive until midiInClose completes.
    handle = ctypes.c_void_p()
    check(dll, dll.midiInOpen(ctypes.byref(handle), index,
                            ctypes.cast(callback, ctypes.c_void_p).value, 0, 0x30000))
    destination = Path(output)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": "metadata", "port": index, "ports": ports(dll),
                                     "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
            stream.flush()
            check(dll, dll.midiInStart(handle))
            deadline = time.monotonic() + seconds
            print("Capturing input only for %ss. Press buttons, turn both ways, touch/move/release fader." % seconds, flush=True)
            try:
                while time.monotonic() < deadline:
                    try:
                        event = events.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    stream.write(json.dumps(event) + "\n")
                    stream.flush()
                    print(describe(event["bytes"]), flush=True)
            except KeyboardInterrupt:
                pass
    finally:
        dll.midiInStop(handle)
        dll.midiInReset(handle)
        dll.midiInClose(handle)
    print("Saved " + str(destination.resolve()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--capture", type=int)
    parser.add_argument("--seconds", type=float, default=45)
    parser.add_argument("--output", default="tmp/native-capture-%s.jsonl" % time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    dll = winmm()
    inventory = ports(dll)
    print(json.dumps(inventory, indent=2, ensure_ascii=False), flush=True)
    if args.capture is not None:
        if not 0 <= args.capture < len(inventory["inputs"]):
            parser.error("Input index does not exist")
        if not 0 < args.seconds <= 600:
            parser.error("seconds must be between 0 and 600")
        capture(dll, args.capture, args.seconds, args.output)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
