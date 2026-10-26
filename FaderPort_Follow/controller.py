"""Controller behavior, exercised against a fake Live object model in tests."""

import time
import traceback

from . import protocol as p
from . import settings
from .live_api import Bindings, read
from .volume_curve import VolumeCurve


class FollowController:
    def __init__(self, bridge, send, clock=None, config=settings):
        self.api = bridge
        self.send = send
        self.clock = clock or time.monotonic
        self.config = config
        self.mode = "channel"
        self.shift = False
        self.touched = False
        self.block_fader = False
        self.closed = False
        self._initializing = True
        self.pressed = set()
        self._track = None
        self._volume = None
        self._volume_curve = VolumeCurve()
        self._device = None
        self._device_switch = None
        self._gesture = None
        self._link = None
        self._locked = None
        self._previous_track = None
        self._leds = {}
        self._last_motor = None
        self._motor_time = float("-inf")
        self._keepalive_time = float("-inf")
        self._jog_due = {}
        self._jog_chord = False
        self._global = Bindings(bridge.log)
        self._track_bindings = Bindings(bridge.log)
        self._device_bindings = Bindings(bridge.log)
        self._link_bindings = Bindings(bridge.log)
        self._listen()
        self._bind_track()
        self._bind_link()
        self._initializing = False
        self.refresh_state()

    def _listen(self):
        song = self.api.song
        self._global.add(song.view, "selected_track", self._selection_changed)
        self._global.add(song.view, "selected_parameter", self._bind_link)
        self._global.add(song.view, "draw_mode", self.refresh)
        self._global.add(song, "start_time", self.api.forget_playback_position)
        for event in ("tracks", "visible_tracks", "return_tracks"):
            self._global.add(song, event, self._structure_changed)
        for event in ("is_playing", "record_mode", "session_record", "session_record_status",
                      "loop", "metronome", "session_automation_record", "re_enable_automation_enabled",
                      "can_undo", "can_redo", "can_jump_to_next_cue", "can_jump_to_prev_cue"):
            self._global.add(song, event, self.refresh)
        self._global.add(self.api.application.view, "focused_document_view", self.refresh)

    def _bind_track(self):
        self._track_bindings.clear()
        self._track = self.api.track
        self._volume = self.api.volume
        self._volume_curve = VolumeCurve()
        marks = getattr(self.config, "FADER_CALIBRATION", ())
        if marks and self.api.parameter_enabled(self._volume):
            try:
                self._volume_curve = VolumeCurve.from_marks(
                    self._volume, marks, getattr(self.config, "FADER_PANEL_UPPER_MARK", None),
                    smooth=getattr(self.config, "FADER_SMOOTH_CURVE", False))
                if self.config.DEBUG_MIDI:
                    self.api.log("Volume calibration active: " + "; ".join(
                        "%.1f dB@%d -> native %.6f" % (mark[1], round(mark[0] * 16383), point[1])
                        for mark, point in zip(marks, self._volume_curve.points[1:-1])))
                    self.api.log("Volume maximum motor position: %d / 16383" %
                                 round(self._volume_curve.to_physical(1.0) * 16383))
            except (AttributeError, TypeError, ValueError, RuntimeError, ReferenceError) as error:
                self.api.log("Volume calibration unavailable; using original mapping: " + str(error))
        for event in ("mute", "solo", "arm", "can_be_armed"):
            self._track_bindings.add(self._track, event, self.refresh)
        self._track_bindings.add(self._track, "devices", self._bind_device)
        self._track_bindings.add(read(self._track, "view"), "selected_device", self._bind_device)
        for parameter in (self._volume, self.api.pan):
            for event in ("value", "is_enabled", "automation_state"):
                self._track_bindings.add(parameter, event, self.refresh)
        # Live 12.4.7's MixerDevice.remove_panning_mode_listener can raise a
        # Boost.Python signature error. Pan mode is checked on every operation,
        # so avoid owning this unremovable optional listener.
        self._bind_device()

    def _bind_device(self):
        self._device_bindings.clear()
        self._device = self.api.device
        self._device_switch = self.api.device_switch
        self._device_bindings.add(self._device_switch, "value", self.refresh)
        self._device_bindings.add(self._device, "parameters", self._bind_device)
        self.refresh()

    def _bind_link(self):
        if self.closed:
            return
        if self._locked is not None and not self.api.exists(self._locked):
            self._locked = None
            self.api.show("FaderPort: deleted parameter unlocked")
        target = self._locked if self._locked is not None else self.api.selected_parameter
        if target != self._link:
            self._link_bindings.clear()
            self._link = target
            for event in ("value", "is_enabled"):
                self._link_bindings.add(target, event, self.refresh)
        self.refresh()

    def _selection_changed(self):
        if self.closed:
            return
        if self.api.track != self._track:
            if self.touched:
                self._end_gesture()
                self.block_fader = True
            self._bind_track()
            self._bind_link()
            self._motor(force=True)
            self.refresh()

    def _structure_changed(self):
        if self.closed:
            return
        # A deleted track can invalidate the old handle before selected_track fires.
        if self.api.track != self._track or self.api.volume != self._volume:
            self._selection_changed()
            if self.api.volume != self._volume:
                self._end_gesture()
                self.block_fader = self.touched
                self._bind_track()
        else:
            self._bind_device()
        self._bind_link()
        self.refresh()

    def _end_gesture(self):
        parameter, self._gesture = self._gesture, None
        if parameter is not None:
            try:
                parameter.end_gesture()
            except (RuntimeError, ReferenceError):
                pass

    def _touch(self, pressed):
        if pressed == self.touched:
            return
        self.touched = pressed
        if pressed:
            if not self.block_fader and self.api.parameter_enabled(self._volume):
                self._volume.begin_gesture()
                self._gesture = self._volume
        else:
            self._end_gesture()
            self.block_fader = False
            self._motor(force=True)

    def reset_input_on_port_change(self):
        """Drop stuck transport/modifier input when Live reconnects the ports.

        If a fader was held, require a release (or a fresh touch/release cycle)
        before re-enabling its motor and writes. A lost USB touch-up must not
        leave transport seeking or rebind an active editing gesture.
        """
        self._end_gesture()
        self.pressed.clear()
        self._jog_due.clear()
        self._jog_chord = False
        self.shift = False
        self.block_fader = self.touched
        self.api.forget_playback_position()

    def receive_midi(self, message):
        if self.closed:
            return
        if self.config.DEBUG_MIDI:
            self.api.log("RX " + p.describe(message))
        try:
            event = p.decode(message, self.config.ENCODER_FORMAT, self.config.ENCODER_INVERT)
            if event is None:
                return
            # Recheck before every input as well as listening to Live selection changes.
            self._selection_changed()
            kind, identifier, value = event
            if kind == "fader":
                self._fader(value)
            elif kind == "encoder" and value:
                self._encoder(value)
            elif kind == "button":
                self._button(identifier, value)
            self.refresh()
        except Exception:
            self.api.log("ERROR processing MIDI: " + traceback.format_exc())
            self.api.show("FaderPort Follow: operation failed; see Log.txt")

    def _fader(self, raw):
        if self.block_fader or (self.config.REQUIRE_FADER_TOUCH and not self.touched):
            return
        parameter = self._volume
        if self.api.parameter_enabled(parameter):
            normalized = self._volume_curve.to_parameter(raw / 16383.0)
            value = parameter.min + normalized * (parameter.max - parameter.min)
            if self._gesture is parameter:
                self.api.set_parameter(parameter, value)
            else:
                self.api.parameter_gesture(parameter, value)

    def _encoder(self, delta):
        fine = self.config.FINE_FACTOR if self.shift else 1.0
        if self.mode == "channel":
            self.api.navigate(delta)
        elif self.mode == "pan":
            self.api.adjust_parameter(self.api.pan, delta, self.config.PAN_STEPS, fine)
        elif self.mode == "link":
            self._bind_link()
            self.api.adjust_parameter(self._link, delta, self.config.LINK_STEPS, fine)
        elif self.mode in ("scroll", "zoom"):
            self.api.scroll(delta, zoom=self.mode == "zoom")
        elif self.mode == "section":
            self.api.cue(delta)

    def _button(self, note, pressed):
        if note == p.FADER_TOUCH:
            self._touch(pressed)
            return
        if note == p.SHIFT:
            self.shift = pressed
            return
        if not pressed:
            self.pressed.discard(note)
            self._jog_due.pop(note, None)
            if not self.pressed.intersection((p.REWIND, p.FORWARD)):
                self._jog_chord = False
            return
        if note in self.pressed:
            return
        self.pressed.add(note)
        if self.shift:
            self._shift_button(note)
            return
        if note in (p.ARM, p.MUTE, p.SOLO):
            self.api.toggle_track({p.ARM: "arm", p.MUTE: "mute", p.SOLO: "solo"}[note])
        elif note == p.CHANNEL:
            self._mode("channel")
        elif note == p.PAN:
            self._mode("pan")
        elif note == p.LINK:
            self._mode("link")
        elif note == p.SCROLL:
            self._mode("scroll")
        elif note == p.SECTION:
            self._mode("section")
        elif note in (p.PREV, p.NEXT):
            self.api.navigate(-1 if note == p.PREV else 1)
        elif note == p.MASTER:
            self._master()
        elif note in (p.PLAY, p.FOOTSWITCH):
            self.api.toggle_play()
        elif note == p.STOP:
            self.api.stop_playing()
        elif note == p.RECORD:
            self.api.toggle_record()
        elif note in (p.LOOP, p.CLICK, p.WRITE):
            attr = {p.LOOP: "loop", p.CLICK: "metronome", p.WRITE: "session_automation_record"}[note]
            setattr(self.api.song, attr, not getattr(self.api.song, attr))
        elif note == p.READ:
            self.api.song.re_enable_automation()
        elif note == p.TOUCH:
            self.api.song.view.draw_mode = not self.api.song.view.draw_mode
        elif note == p.BYPASS:
            parameter = self.api.device_switch
            if self.api.parameter_enabled(parameter):
                self.api.parameter_gesture(parameter, parameter.min if parameter.value > parameter.min else parameter.max)
        elif note == p.MARKER:
            self.api.song.set_or_delete_cue()
        elif note == p.ENCODER_PUSH:
            if self.mode in ("pan", "link"):
                parameter = self.api.pan if self.mode == "pan" else self._link
                if self.api.parameter_enabled(parameter):
                    self.api.parameter_gesture(parameter, parameter.default_value)
            else:
                self.api.focus_track()
        elif note in (p.REWIND, p.FORWARD):
            if {p.REWIND, p.FORWARD}.issubset(self.pressed):
                self._rtz()
                self._jog_chord = True
                self._jog_due.clear()
            elif not self._jog_chord:
                self.api.jump_bar(-1 if note == p.REWIND else 1)
                self._jog_due[note] = self.clock() + self.config.JOG_DELAY

    def _shift_button(self, note):
        if note == p.PREV and read(self.api.song, "can_undo", False):
            self.api.song.undo()
        elif note == p.NEXT and read(self.api.song, "can_redo", False):
            self.api.song.redo()
        elif note == p.STOP:
            self._rtz()
        elif note == p.SCROLL:
            self._mode("zoom" if self.mode != "zoom" else "scroll")
        elif note == p.LINK:
            if self._locked is not None:
                self._locked = None
            elif self.api.parameter_enabled(self.api.selected_parameter):
                self._locked = self.api.selected_parameter
            self._bind_link()
            self.api.show("FaderPort: Link " + ("locked" if self._locked is not None else "unlocked"))
        elif note == p.MASTER:
            self.api.toggle_document()
        elif note == p.CLICK:
            self.api.show_view("Detail/Clip")
        elif note == p.SECTION:
            self.api.show_view("Detail/DeviceChain")
        elif note == p.MARKER:
            self.api.toggle_browser()

    def _mode(self, mode):
        self.mode = mode
        self.api.show("FaderPort: " + mode.title())

    def _master(self):
        if self.api.track == self.api.song.master_track:
            tracks = self.api.all_tracks()
            target = self._previous_track if self._previous_track in tracks else (tracks[0] if tracks else None)
            if target is not None:
                self.api.song.view.selected_track = target
        else:
            self._previous_track = self.api.track
            self.api.song.view.selected_track = self.api.song.master_track

    def _rtz(self):
        self.api.return_to_start()

    def tick(self):
        if self.closed:
            return
        try:
            self._keepalive()
            self._structure_changed_if_needed()
            self._bind_link()
            now = self.clock()
            if not self._jog_chord and not self.shift:
                for note, due in tuple(self._jog_due.items()):
                    if now >= due and note in self.pressed:
                        self.api.jump_bar(-1 if note == p.REWIND else 1)
                        self._jog_due[note] = now + self.config.JOG_INTERVAL
            self.refresh()
        except Exception:
            self.api.log("ERROR tick: " + traceback.format_exc())

    def _structure_changed_if_needed(self):
        if self.api.track != self._track or self.api.volume != self._volume:
            self._structure_changed()
        elif self.api.device != self._device or self.api.device_switch != self._device_switch:
            self._bind_device()

    def refresh_state(self):
        if self.closed:
            return
        # Called on port reconnection, not a factory reset or fader calibration.
        for message in p.NATIVE_STARTUP:
            self.send(message)
        self._keepalive(force=True)
        for note, color in p.RGB.items():
            for message in p.color_messages(note, color):
                self.send(message)
        self._leds.clear()
        self._motor(force=True)
        self.refresh()

    def _keepalive(self, force=False):
        now = self.clock()
        if force or now - self._keepalive_time >= self.config.KEEPALIVE_INTERVAL:
            self.send(p.NATIVE_KEEPALIVE)
            self._keepalive_time = now

    def refresh(self):
        if self.closed or self._initializing:
            return
        song, track = self.api.song, self.api.track
        regular = self.api.exists(track) and track != song.master_track
        device_switch = self.api.device_switch
        states = {
            p.ARM: regular and read(track, "can_be_armed", False) and read(track, "arm", False),
            p.MUTE: regular and read(track, "mute", False),
            p.SOLO: regular and read(track, "solo", False),
            p.BYPASS: self.api.parameter_enabled(device_switch) and device_switch.value <= device_switch.min,
            p.CHANNEL: self.mode == "channel", p.PAN: self.mode == "pan",
            p.LINK: 2 if self.mode == "link" and self._locked is not None else self.mode == "link",
            p.SCROLL: 2 if self.mode == "zoom" else self.mode == "scroll",
            p.SECTION: self.mode == "section", p.MARKER: False,
            p.MASTER: track == song.master_track, p.CLICK: read(song, "metronome", False),
            p.PLAY: read(song, "is_playing", False), p.STOP: not read(song, "is_playing", False),
            p.RECORD: self.api.record_active(), p.LOOP: read(song, "loop", False),
            p.WRITE: read(song, "session_automation_record", False),
            p.READ: read(song, "re_enable_automation_enabled", False),
            p.TOUCH: read(song.view, "draw_mode", False), p.SHIFT: self.shift,
            p.PREV: self.api.neighbor(-1) != track, p.NEXT: self.api.neighbor(1) != track,
            p.REWIND: p.REWIND in self._jog_due, p.FORWARD: p.FORWARD in self._jog_due,
        }
        for note in p.LEDS:
            value = int(states.get(note, False))
            if self._leds.get(note) != value:
                self.send(p.led_message(note, value))
                self._leds[note] = value
        self._motor()

    def _motor(self, force=False):
        parameter = self._volume
        if self.touched or self.block_fader or not self.api.parameter_enabled(parameter):
            return
        now = self.clock()
        if not force and now - self._motor_time < self.config.MOTOR_INTERVAL:
            return
        normalized = (parameter.value - parameter.min) / (parameter.max - parameter.min)
        message = p.fader_message(self._volume_curve.to_physical(normalized))
        if force or message != self._last_motor:
            self.send(message)
            self._last_motor = message
            self._motor_time = now

    def disconnect(self):
        if self.closed:
            return
        self.closed = True
        self._end_gesture()
        self.pressed.clear()
        self._jog_due.clear()
        for bindings in (self._global, self._track_bindings, self._device_bindings, self._link_bindings):
            bindings.clear()
        for note in p.LEDS:
            self.send(p.led_message(note, 0))

