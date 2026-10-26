import unittest
from types import SimpleNamespace

from FaderPort_Follow import protocol as p, settings
from FaderPort_Follow.controller import FollowController
from FaderPort_Follow.live_api import LiveBridge
from .fakes import Clock, Device, Parameter, Track, environment


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.song, self.app = environment()
        self.sent, self.logs, self.messages = [], [], []
        self.clock = Clock()
        self.bridge = LiveBridge(self.song, self.app, self.logs.append, self.messages.append)
        self.control = FollowController(self.bridge, self.sent.append, self.clock)
        self.sent.clear()

    def tearDown(self):
        self.control.disconnect()
        self.assertFalse([line for line in self.logs if line.startswith("ERROR")], self.logs)

    def down(self, note):
        self.control.receive_midi((0x90, note, 127))

    def up(self, note):
        self.control.receive_midi((0x90, note, 0))

    def tap(self, note, shift=False):
        if shift:
            self.down(p.SHIFT)
        self.down(note)
        self.up(note)
        if shift:
            self.up(p.SHIFT)

    def encoder(self, delta):
        raw = delta if delta >= 0 else 0x40 + abs(delta)
        self.control.receive_midi((0xB0, p.ENCODER_CC, raw))

    def motors(self):
        return [message for message in self.sent if message[0] == 0xE0]

    def last_led(self, note):
        return self.control._leds[note]

    def test_tracks_1_8_9_12_33_follow_without_banking(self):
        for number in (1, 8, 9, 12, 33):
            with self.subTest(track=number):
                track = self.song.tracks[number - 1]
                track.mixer_device.volume.value = number / 40.0
                self.song.view.selected_track = track
                self.sent.clear()
                self.control.refresh_state()
                self.assertEqual(self.motors()[-1], p.fader_message(number / 40.0))
                self.down(p.FADER_TOUCH)
                self.control.receive_midi(p.fader_message(0.75))
                self.up(p.FADER_TOUCH)
                self.assertAlmostEqual(track.mixer_device.volume.value, 0.75, delta=1 / 16383)
                self.tap(p.MUTE)
                self.assertTrue(track.mute)

    def test_touch_begins_and_ends_gesture_and_suppresses_motor(self):
        volume = self.bridge.volume
        self.down(p.FADER_TOUCH)
        self.control.receive_midi(p.fader_message(0.8))
        self.clock.advance(1)
        self.control.tick()
        self.assertEqual(self.motors(), [])
        self.assertEqual(volume.gestures, ["begin"])
        self.up(p.FADER_TOUCH)
        self.assertEqual(volume.gestures, ["begin", "end"])
        self.assertEqual(len(self.motors()), 1)

    def test_switch_during_touch_does_not_write_old_or_new_track(self):
        old = self.bridge.volume
        self.down(p.FADER_TOUCH)
        self.control.receive_midi(p.fader_message(0.6))
        old_value = old.value
        self.song.view.selected_track = self.song.tracks[32]
        new = self.bridge.volume
        new_value = new.value
        self.assertEqual(old.gestures, ["begin", "end"])
        self.control.receive_midi(p.fader_message(0.99))
        self.assertEqual(old.value, old_value)
        self.assertEqual(new.value, new_value)
        self.assertEqual(self.motors(), [])
        self.up(p.FADER_TOUCH)
        self.assertEqual(self.motors()[-1], p.fader_message(new_value))
        self.down(p.FADER_TOUCH)
        self.control.receive_midi(p.fader_message(0.9))
        self.up(p.FADER_TOUCH)
        self.assertGreater(new.value, 0.89)

    def test_motor_echo_without_touch_cannot_write_automation(self):
        volume = self.bridge.volume
        self.control.receive_midi(p.fader_message(1))
        self.assertEqual(volume.value, 0.5)
        self.assertEqual(volume.gestures, [])

    def test_mouse_and_automation_feedback_is_throttled_then_flushed(self):
        volume = self.bridge.volume
        volume.value = 0.2
        self.assertEqual(self.motors(), [])  # Initial feedback at time zero.
        self.clock.advance()
        self.control.tick()
        self.assertEqual(self.motors()[-1], p.fader_message(0.2))
        self.sent.clear()
        volume.value = 0.6
        volume.value = 0.7
        self.assertEqual(self.motors(), [])
        self.clock.advance()
        self.control.tick()
        self.assertEqual(self.motors(), [p.fader_message(0.7)])

    def test_old_track_has_no_remaining_listeners_or_feedback(self):
        old = self.song.view.selected_track
        self.song.view.selected_track = self.song.tracks[11]
        self.assertEqual(old.listener_count(), 0)
        self.assertEqual(old.mixer_device.volume.listener_count(), 0)
        self.sent.clear()
        self.clock.advance()
        old.mixer_device.volume.value = 0.9
        old.mute = True
        self.assertEqual(self.sent, [])

    def test_unarmable_group_return_and_master(self):
        group = Track("Group", False)
        self.song.tracks = [group] + self.song.tracks
        for track in (group, self.song.return_tracks[0], self.song.master_track):
            self.song.view.selected_track = track
            self.tap(p.ARM)
            self.assertFalse(track.arm)
            self.assertEqual(self.last_led(p.ARM), 0)
            self.down(p.FADER_TOUCH)
            self.control.receive_midi(p.fader_message(0.9))
            self.up(p.FADER_TOUCH)
            self.assertGreater(track.mixer_device.volume.value, 0.89)
        self.tap(p.MUTE)
        self.tap(p.SOLO)
        self.assertFalse(self.song.master_track.mute)
        self.assertFalse(self.song.master_track.solo)

    def test_arm_and_solo_respect_exclusive_preferences(self):
        first, second = self.song.tracks[:2]
        for button, attribute in ((p.ARM, "arm"), (p.SOLO, "solo")):
            self.song.view.selected_track = first
            self.tap(button)
            self.song.view.selected_track = second
            self.tap(button)
            self.assertFalse(getattr(first, attribute))
            self.assertTrue(getattr(second, attribute))
            setattr(self.song, "exclusive_" + attribute, False)
            self.song.view.selected_track = first
            self.tap(button)
            self.assertTrue(getattr(first, attribute))
            self.assertTrue(getattr(second, attribute))

    def test_leds_follow_mouse_changes_and_record_view(self):
        self.song.view.selected_track.mute = True
        self.assertEqual(self.last_led(p.MUTE), 1)
        self.song.record_mode = True
        self.assertEqual(self.last_led(p.RECORD), 1)
        self.app.view.focused_document_view = "Session"
        self.assertEqual(self.last_led(p.RECORD), 0)
        self.song.session_record_status = 1
        self.assertEqual(self.last_led(p.RECORD), 1)

    def test_navigation_order_boundaries_and_reordering(self):
        self.tap(p.PREV)
        self.assertIs(self.bridge.track, self.song.tracks[0])
        self.song.view.selected_track = self.song.tracks[-1]
        self.tap(p.NEXT)
        self.assertIs(self.bridge.track, self.song.return_tracks[0])
        self.tap(p.NEXT)
        self.assertIs(self.bridge.track, self.song.master_track)
        self.tap(p.NEXT)
        self.assertIs(self.bridge.track, self.song.master_track)
        reordered = list(reversed(self.song.tracks))
        self.song.tracks = reordered
        self.song.visible_tracks = reordered
        self.song.view.selected_track = reordered[0]
        self.encoder(1)
        self.assertIs(self.bridge.track, reordered[1])

    def test_mouse_selected_folded_child_remains_controllable(self):
        child = self.song.tracks[1]
        self.song.visible_tracks = [t for t in self.song.tracks if t != child]
        self.song.view.selected_track = child
        self.tap(p.MUTE)
        self.assertTrue(child.mute)
        self.tap(p.NEXT)
        self.assertIs(self.bridge.track, self.song.tracks[2])

    def test_master_returns_to_previous_track_and_handles_deletion(self):
        previous = self.song.tracks[32]
        self.song.view.selected_track = previous
        self.tap(p.MASTER)
        self.assertIs(self.bridge.track, self.song.master_track)
        self.tap(p.MASTER)
        self.assertIs(self.bridge.track, previous)
        self.tap(p.MASTER)
        self.song.tracks = [track for track in self.song.tracks if track != previous]
        self.song.visible_tracks = list(self.song.tracks)
        self.tap(p.MASTER)
        self.assertIs(self.bridge.track, self.song.tracks[0])

    def test_pan_mode_fine_adjust_reset_and_split_stereo_guard(self):
        self.tap(p.PAN)
        self.encoder(1)
        pan = self.bridge.pan
        normal = pan.value
        self.down(p.SHIFT)
        self.encoder(1)
        self.up(p.SHIFT)
        self.assertAlmostEqual(pan.value - normal, normal / 10)
        self.tap(p.ENCODER_PUSH)
        self.assertEqual(pan.value, 0)
        self.bridge.track.mixer_device.panning_mode = 1
        self.encoder(1)
        self.assertEqual(pan.value, 0)
        self.assertIn("no editable parameter", self.messages[-1])

    def test_link_locks_only_encoder_and_handles_deleted_parameter(self):
        first, second = Parameter(), Parameter(0.3)
        self.song.view.selected_parameter = first
        self.tap(p.LINK)
        self.tap(p.LINK, shift=True)
        self.assertEqual(self.last_led(p.LINK), 2)
        self.song.view.selected_parameter = second
        self.song.view.selected_track = self.song.tracks[32]
        self.encoder(1)
        self.assertGreater(first.value, 0.5)
        self.assertEqual(second.value, 0.3)
        self.assertIs(self.control._volume, self.song.tracks[32].mixer_device.volume)
        first.valid = False
        self.control.tick()
        self.assertIsNone(self.control._locked)
        self.encoder(1)
        self.assertGreater(second.value, 0.3)
        self.assertEqual(first.listener_count(), 0)

    def test_link_quantized_parameter_and_reset(self):
        parameter = Parameter(3, 0, 4, 2, True)
        self.song.view.selected_parameter = parameter
        self.tap(p.LINK)
        self.down(p.SHIFT)
        self.encoder(3)
        self.up(p.SHIFT)
        self.assertEqual(parameter.value, 4)
        self.tap(p.ENCODER_PUSH)
        self.assertEqual(parameter.value, 2)
        self.assertEqual(parameter.gestures, ["begin", "end", "begin", "end"])

    def test_play_stop_footswitch_and_noteoff_do_not_double_trigger(self):
        self.down(p.PLAY)
        self.down(p.PLAY)
        self.assertTrue(self.song.is_playing)
        self.control.receive_midi((0x80, p.PLAY, 64))
        self.assertTrue(self.song.is_playing)
        self.tap(p.FOOTSWITCH)
        self.assertFalse(self.song.is_playing)
        self.tap(p.PLAY)
        self.tap(p.STOP)
        self.assertFalse(self.song.is_playing)
        self.assertEqual(self.song.current_song_time, 16)
        self.tap(p.STOP, shift=True)
        self.assertEqual(self.song.current_song_time, 0)

    def test_play_honors_insert_marker_then_resumes_unchanged_pause(self):
        self.song.current_song_time = 0
        self.song.start_time = 32  # Bar 9, while the old playhead is at bar 1.
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 32)
        self.assertEqual(self.song.calls[-1], "start_playing")
        self.song.current_song_time = 35
        self.tap(p.PLAY)
        self.assertFalse(self.song.is_playing)
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 35)
        self.assertEqual(self.song.calls[-1], "continue_playing")

    def test_new_marker_after_pause_overrides_resume_even_if_moved_back(self):
        self.tap(p.PLAY)
        self.song.current_song_time = 20
        self.tap(p.PLAY)
        self.song.start_time = 32
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 32)
        self.song.current_song_time = 36
        self.tap(p.PLAY)
        self.song.start_time = 48
        self.song.start_time = 32
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 32)
        self.assertEqual(self.song.calls[-1], "start_playing")

    def test_stop_clears_pause_and_shift_stop_then_play_starts_at_zero(self):
        self.tap(p.PLAY)
        self.song.current_song_time = 20
        self.tap(p.PLAY)
        self.tap(p.STOP)
        self.song.start_time = 32
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 32)
        self.tap(p.PLAY)
        self.tap(p.STOP, shift=True)
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 0)

    def test_stopped_seek_then_play_and_port_reset_do_not_use_stale_pause(self):
        self.tap(p.FORWARD)
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 20)
        self.assertEqual(self.song.calls[-1], "continue_playing")
        self.tap(p.PLAY)
        self.control.reset_input_on_port_change()
        self.song.start_time = 32
        self.tap(p.PLAY)
        self.assertEqual(self.song.current_song_time, 32)
        self.assertEqual(self.song.calls[-1], "start_playing")

    def test_record_dispatches_by_active_view(self):
        self.tap(p.RECORD)
        self.assertTrue(self.song.record_mode)
        self.app.view.focused_document_view = "Session"
        self.tap(p.RECORD)
        self.assertTrue(self.song.session_record)
        self.assertTrue(self.song.record_mode)
        self.tap(p.RECORD)
        self.assertFalse(self.song.session_record)

    def test_record_fallback_retains_last_view_when_both_are_visible(self):
        self.app.view.focused_document_view = "Session"
        self.assertEqual(self.bridge.document(), "Session")
        self.app.view.visible = {"Session", "Arranger"}
        self.app.view.focused_document_view = ""
        self.assertEqual(self.bridge.document(), "Session")
        self.app.view.visible = {"Arranger"}
        self.assertEqual(self.bridge.document(), "Arranger")

    def test_session_record_overdubs_in_place_without_triggering_new_slot(self):
        self.app.view.focused_document_view = "Session"
        self.song.is_playing = True
        slot = SimpleNamespace(clip=object())
        self.song.view.highlighted_clip_slot = slot
        calls = []

        def new_slot_action():
            calls.append("trigger_session_record")
            self.song.view.highlighted_clip_slot = SimpleNamespace(clip=object())

        self.song.trigger_session_record = new_slot_action
        self.down(p.RECORD)
        self.down(p.RECORD)  # Repeated down must not toggle twice.
        self.up(p.RECORD)
        self.assertTrue(self.song.session_record)
        self.assertEqual(self.last_led(p.RECORD), 1)
        self.assertIs(self.song.view.highlighted_clip_slot, slot)
        self.assertTrue(self.song.is_playing)
        self.assertFalse(self.song.record_mode)
        self.tap(p.RECORD)
        self.assertFalse(self.song.session_record)
        self.assertEqual(self.last_led(p.RECORD), 0)
        self.assertIs(self.song.view.highlighted_clip_slot, slot)
        self.assertTrue(self.song.is_playing)
        self.assertEqual(calls, [])

    def test_session_record_cancels_pending_state_without_starting_another_slot(self):
        self.app.view.focused_document_view = "Session"
        self.song.session_record_status = 1  # Quantized/pending recording.
        self.song.session_record = False
        self.tap(p.RECORD)
        self.assertFalse(self.song.session_record)
        self.assertNotIn("session_record", self.song.calls)
        self.song.session_record_status = 0  # Live confirms cancellation later.
        self.assertEqual(self.last_led(p.RECORD), 0)

    def test_record_state_and_led_switch_between_views_without_cross_toggling(self):
        self.song.record_mode = False
        self.song.session_record = True
        self.app.view.focused_document_view = "Session"
        self.assertEqual(self.last_led(p.RECORD), 1)
        self.app.view.focused_document_view = "Arranger"
        self.assertEqual(self.last_led(p.RECORD), 0)
        self.tap(p.RECORD)
        self.assertTrue(self.song.record_mode)
        self.assertTrue(self.song.session_record)
        self.app.view.focused_document_view = "Session"
        self.tap(p.RECORD)
        self.assertFalse(self.song.session_record)
        self.assertTrue(self.song.record_mode)

    def test_loop_metronome_automation_and_drawing(self):
        for note, attribute in ((p.LOOP, "loop"), (p.CLICK, "metronome"), (p.WRITE, "session_automation_record")):
            self.tap(note)
            self.assertTrue(getattr(self.song, attribute))
            self.assertEqual(self.last_led(note), 1)
        self.song.re_enable_automation_enabled = True
        self.tap(p.READ)
        self.assertFalse(self.song.re_enable_automation_enabled)
        self.assertEqual(self.last_led(p.READ), 0)
        self.tap(p.TOUCH)
        self.assertTrue(self.song.view.draw_mode)

    def test_jog_hold_release_meter_and_rtz_chord(self):
        self.song.signature_numerator = 7
        self.song.signature_denominator = 8
        self.down(p.FORWARD)
        self.assertEqual(self.song.current_song_time, 19.5)
        self.clock.advance(0.5)
        self.control.tick()
        self.assertEqual(self.song.current_song_time, 23)
        self.up(p.FORWARD)
        self.clock.advance(1)
        self.control.tick()
        self.assertEqual(self.song.current_song_time, 23)
        self.down(p.FORWARD)
        self.down(p.REWIND)
        self.assertEqual(self.song.current_song_time, 0)
        self.up(p.REWIND)
        self.clock.advance(1)
        self.control.tick()
        self.assertEqual(self.song.current_song_time, 0)
        self.up(p.FORWARD)
        self.tap(p.REWIND)
        self.assertEqual(self.song.current_song_time, 0)

    def test_scroll_zoom_cues_and_view_shortcuts(self):
        self.tap(p.SCROLL)
        self.encoder(-1)
        self.assertIn(("scroll", "left", "Arranger", False), self.app.view.calls)
        self.tap(p.SCROLL, shift=True)
        self.encoder(1)
        self.assertIn(("zoom", "right", "Arranger", False), self.app.view.calls)
        self.tap(p.SECTION)
        self.encoder(-1)
        self.encoder(1)
        self.assertEqual(self.song.calls[-2:], ["prev_cue", "next_cue"])
        self.tap(p.MARKER)
        self.assertEqual(self.song.calls[-1], "cue")
        for note, view in ((p.CLICK, "Detail/Clip"), (p.SECTION, "Detail/DeviceChain")):
            self.tap(note, shift=True)
            self.assertIn(("show", view), self.app.view.calls)
        self.tap(p.MARKER, shift=True)
        self.assertIn("Browser", self.app.view.visible)
        self.tap(p.MARKER, shift=True)
        self.assertNotIn("Browser", self.app.view.visible)
        self.tap(p.MASTER, shift=True)
        self.assertEqual(self.bridge.document(), "Session")

    def test_device_bypass_follows_selected_device(self):
        old = self.bridge.device_switch
        self.tap(p.BYPASS)
        self.assertEqual(old.value, 0)
        self.assertEqual(self.last_led(p.BYPASS), 1)
        new = Parameter(1, 0, 1, 1, True)
        self.bridge.track.view.selected_device = Device(parameters=[new])
        self.tap(p.BYPASS)
        self.assertEqual(new.value, 0)
        self.assertEqual(old.listener_count(), 0)

    def test_unassigned_shift_combinations_are_noops(self):
        for note in (p.ARM, p.MUTE, p.SOLO, p.PLAY, p.RECORD, p.PAN, p.WRITE):
            self.tap(note, shift=True)
        self.assertFalse(self.bridge.track.arm or self.bridge.track.mute or self.bridge.track.solo)
        self.assertFalse(self.song.is_playing or self.song.record_mode or self.song.session_automation_record)
        self.assertEqual(self.control.mode, "channel")

    def test_shift_undo_redo_and_disabled_history(self):
        self.tap(p.PREV, shift=True)
        self.tap(p.NEXT, shift=True)
        self.assertEqual(self.song.calls, ["undo", "redo"])
        self.song.can_undo = False
        self.tap(p.PREV, shift=True)
        self.assertEqual(self.song.calls, ["undo", "redo"])

    def test_reconnect_resends_state_and_no_idle_midi_flood(self):
        self.control.refresh_state()
        self.assertTrue(self.motors())
        self.assertIn((0x91, p.CHANNEL, 0), self.sent)
        self.sent.clear()
        for _ in range(20):
            self.clock.advance()
            self.control.tick()
        self.assertTrue(all(message == p.NATIVE_KEEPALIVE for message in self.sent))
        self.assertLessEqual(len(self.sent), 3)

    def test_native_keepalive_precedes_feedback_and_repeats_while_touched(self):
        self.control.refresh_state()
        self.assertEqual(self.sent[:3], list(p.NATIVE_STARTUP) + [p.NATIVE_KEEPALIVE])
        self.sent.clear()
        self.down(p.FADER_TOUCH)
        self.clock.advance(0.9)
        self.control.tick()
        self.assertIn(p.NATIVE_KEEPALIVE, self.sent)
        self.assertEqual(self.motors(), [])
        self.up(p.FADER_TOUCH)
        self.sent.clear()
        self.control.disconnect()
        self.sent.clear()
        self.clock.advance(1)
        self.control.tick()
        self.assertEqual(self.sent, [])

    def test_constructor_and_reconnect_initialize_before_motor_feedback(self):
        self.control.disconnect()
        self.sent.clear()
        self.control = FollowController(self.bridge, self.sent.append, self.clock)
        self.assertEqual(self.sent[:3], list(p.NATIVE_STARTUP) + [p.NATIVE_KEEPALIVE])
        self.assertTrue(self.motors())
        self.sent.clear()
        self.control.reset_input_on_port_change()
        self.control.refresh_state()
        self.assertEqual(self.sent[:3], list(p.NATIVE_STARTUP) + [p.NATIVE_KEEPALIVE])
        self.assertTrue(self.motors())

    def test_disconnect_ends_gesture_cleans_listeners_stops_tasks(self):
        volume = self.bridge.volume
        self.down(p.FADER_TOUCH)
        self.down(p.FORWARD)
        self.control.disconnect()
        self.assertEqual(volume.gestures, ["begin", "end"])
        self.assertEqual(self.song.listener_count(), 0)
        self.assertEqual(self.song.view.listener_count(), 0)
        self.assertEqual(volume.listener_count(), 0)
        self.assertEqual(self.app.view.listener_count(), 0)
        self.sent.clear()
        position = self.song.current_song_time
        self.clock.advance(5)
        self.control.tick()
        self.tap(p.PLAY)
        self.control.refresh_state()
        self.assertEqual(position, self.song.current_song_time)
        self.assertEqual(self.sent, [])

    def test_port_change_ends_gesture_and_waits_for_release_before_motor_or_write(self):
        volume = self.bridge.volume
        self.down(p.FADER_TOUCH)
        self.down(p.FORWARD)
        self.control.reset_input_on_port_change()
        self.assertEqual(volume.gestures, ["begin", "end"])
        self.assertFalse(self.control._jog_due)
        self.sent.clear()
        self.control.refresh_state()
        self.control.receive_midi(p.fader_message(1))
        self.assertEqual(volume.value, 0.5)
        self.assertEqual(self.motors(), [])
        self.up(p.FADER_TOUCH)
        self.assertEqual(self.motors(), [p.fader_message(0.5)])


if __name__ == "__main__":
    unittest.main()
