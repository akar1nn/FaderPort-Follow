"""Entrypoint contract tests; these stubs do not constitute a Live smoke test."""

import contextlib
import importlib
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from FaderPort_Follow import create_instance, protocol as p, settings
from .fakes import environment


class Element:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.listeners = []
        self.instances.append(self)

    def add_value_listener(self, callback):
        self.listeners.append(callback)


class SurfaceBase:
    def __init__(self, c_instance):
        self.song = c_instance.song
        self.application = c_instance.application
        self.sent, self.messages = [], []
        self.base_receives = []
        self.base_disconnected = False

    def component_guard(self):
        return contextlib.nullcontext()

    def _send_midi(self, message):
        return self._do_send_midi(message)

    def _do_send_midi(self, message):
        self.sent.append(message)
        return True

    def show_message(self, message):
        self.messages.append(message)

    def receive_midi(self, message):
        self.base_receives.append(message)

    def receive_midi_chunk(self, messages):
        self.base_receives.extend(messages)

    def update_display(self):
        pass

    def refresh_state(self):
        pass

    def port_settings_changed(self):
        self.refresh_state()

    def disconnect(self):
        self.base_disconnected = True


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        fake_live = ModuleType("Live")
        fake_live.Application = SimpleNamespace(Application=SimpleNamespace(View=SimpleNamespace(
            NavDirection=SimpleNamespace(left="left", right="right"))))
        fake_base = ModuleType("ableton.v2.base")
        fake_base.liveobj_valid = bool
        fake_surface = ModuleType("ableton.v2.control_surface")
        fake_surface.ControlSurface = SurfaceBase
        fake_surface.MIDI_CC_TYPE, fake_surface.MIDI_NOTE_TYPE, fake_surface.MIDI_PB_TYPE = 0, 1, 2
        fake_elements = ModuleType("ableton.v2.control_surface.elements")
        fake_elements.ButtonElement = fake_elements.SliderElement = Element
        self.modules = patch.dict(sys.modules, {"Live": fake_live,
            "ableton": ModuleType("ableton"), "ableton.v2": ModuleType("ableton.v2"),
            "ableton.v2.base": fake_base, "ableton.v2.control_surface": fake_surface,
            "ableton.v2.control_surface.elements": fake_elements})
        self.modules.start()
        sys.modules.pop("FaderPort_Follow.surface", None)
        Element.instances = []
        song, app = environment()
        self.surface = create_instance(SimpleNamespace(song=song, application=app))

    def tearDown(self):
        self.surface.disconnect()
        sys.modules.pop("FaderPort_Follow.surface", None)
        self.modules.stop()

    def test_registers_all_forwarded_inputs_including_touch_and_pitchbend(self):
        self.assertEqual(len(Element.instances), len(p.BUTTONS) + 1 + len(p.ENCODER_CCS))
        self.assertTrue(all(len(element.listeners) == 1 for element in Element.instances))
        self.assertIn((True, 1, 0, p.FADER_TOUCH), [element.args for element in Element.instances])
        self.assertIn((2, 0, 0), [element.args for element in Element.instances])
        self.assertIn((0, 0, 0x10), [element.args for element in Element.instances])
        self.assertIn((0, 0, 0x3C), [element.args for element in Element.instances])

    def test_cc10_encoder_can_select_tracks(self):
        second = self.surface.song.tracks[1]
        self.surface.receive_midi((0xB0, 0x10, 1))
        self.assertIs(self.surface.song.view.selected_track, second)
        self.surface.receive_midi((0xB0, 0x10, 0x41))
        self.assertIs(self.surface.song.view.selected_track, self.surface.song.tracks[0])

    def test_actual_midi_send_failure_is_reported_once_until_recovery(self):
        with patch.object(SurfaceBase, '_do_send_midi', return_value=False):
            with self.assertLogs('FaderPort_Follow.surface', level='INFO') as captured:
                self.surface._output((0xE0, 0, 0))
                self.surface._output((0xE0, 0, 64))
            self.assertEqual(sum('ERROR MIDI output failed' in line for line in captured.output), 1)
        self.surface._output((0xE0, 0, 64))
        self.assertFalse(self.surface._midi_output_failed)

    def test_batched_midi_keeps_touch_fader_release_order(self):
        volume = self.surface.song.view.selected_track.mixer_device.volume
        messages = ((0x90, p.FADER_TOUCH, 127), p.fader_message(0.75), (0x90, p.FADER_TOUCH, 0))
        self.surface.receive_midi_chunk(iter(messages))
        self.assertAlmostEqual(volume.value, 0.75, delta=1 / 16383)
        self.assertEqual(volume.gestures, ["begin", "end"])
        self.assertEqual(self.surface.base_receives, list(messages))

    def test_single_midi_refresh_and_disconnect(self):
        self.surface.receive_midi((0x90, p.PLAY, 127))
        self.surface.receive_midi((0x90, p.PLAY, 0))
        self.assertTrue(self.surface.song.is_playing)
        self.surface.refresh_state()
        self.surface.update_display()
        self.surface.disconnect()
        self.assertTrue(self.surface.base_disconnected)
        self.assertIsNone(self.surface._follow)

    def test_port_change_resets_stuck_transport_and_resends_feedback(self):
        self.surface.receive_midi((0x90, p.FORWARD, 127))
        self.surface.receive_midi((0x90, p.SHIFT, 127))
        self.surface.sent.clear()
        self.surface.port_settings_changed()
        self.assertFalse(self.surface._follow.pressed)
        self.assertFalse(self.surface._follow._jog_due)
        self.assertFalse(self.surface._follow.shift)
        self.assertTrue(any(message[0] == 0xE0 for message in self.surface.sent))
        self.assertEqual(self.surface.sent[:3], list(p.NATIVE_STARTUP) + [p.NATIVE_KEEPALIVE])

    def test_diagnostic_startup_uses_python_logging_without_legacy_method(self):
        self.assertFalse(hasattr(SurfaceBase, 'log_message'))
        self.surface.disconnect()
        song, app = environment()
        with patch.object(settings, 'DEBUG_MIDI', True):
            with self.assertLogs('FaderPort_Follow.surface', level='INFO') as captured:
                self.surface = create_instance(SimpleNamespace(song=song, application=app))
                self.surface.receive_midi((0x90, p.PLAY, 127))
                self.surface.receive_midi((0x90, p.PLAY, 0))
            output = '\n'.join(captured.output)
            self.assertIn('[FaderPort Follow] Loaded', output)
            self.assertIn('[FaderPort Follow] TX ', output)
            self.assertIn('[FaderPort Follow] RX ', output)
            self.assertTrue(song.is_playing)

