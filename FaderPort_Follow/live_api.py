"""Small Live-facing boundary. No import of Live is needed in unit tests."""


def read(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except (RuntimeError, ReferenceError):
        return default


class Bindings:
    """Own each listener exactly once and release it even after LOM deletion."""

    def __init__(self, log):
        self._items = []
        self._log = log

    def add(self, obj, event, callback):
        add = read(obj, "add_" + event + "_listener")
        remove = read(obj, "remove_" + event + "_listener")
        if callable(add) and callable(remove):
            try:
                add(callback)
                self._items.append((remove, callback))
                return True
            except (RuntimeError, AttributeError, TypeError):
                self._log("Listener unavailable: " + event)
        return False

    def clear(self):
        items, self._items = self._items, []
        for remove, callback in reversed(items):
            try:
                remove(callback)
            except (RuntimeError, ReferenceError, TypeError):
                pass  # The corresponding Live object has already been deleted.


class LiveBridge:
    def __init__(self, song, application, log, show, directions=None, valid=None):
        self.song = song
        self.application = application
        self.log = log
        self.show = show
        self.directions = directions
        self._valid = valid or bool
        self._document = "Arranger"
        self._playback_intent = None

    def exists(self, obj):
        try:
            return obj is not None and self._valid(obj)
        except (RuntimeError, ReferenceError):
            return False

    @property
    def track(self):
        return read(self.song.view, "selected_track")

    @property
    def volume(self):
        return read(read(self.track, "mixer_device"), "volume")

    @property
    def pan(self):
        mixer = read(self.track, "mixer_device")
        # Split stereo panning has two independent parameters, not this control.
        if read(mixer, "panning_mode", 0) != 0:
            return None
        return read(mixer, "panning")

    @property
    def selected_parameter(self):
        return read(self.song.view, "selected_parameter")

    @property
    def device(self):
        return read(read(self.track, "view"), "selected_device")

    @property
    def device_switch(self):
        parameters = read(self.device, "parameters", ())
        return parameters[0] if parameters else None

    def parameter_enabled(self, parameter):
        return (self.exists(parameter) and bool(read(parameter, "is_enabled", False))
                and read(parameter, "max", 0) > read(parameter, "min", 0))

    def all_tracks(self):
        return list(self.song.tracks) + list(self.song.return_tracks)

    def navigation_tracks(self):
        return (list(self.song.visible_tracks) + list(self.song.return_tracks)
                + [self.song.master_track])

    def neighbor(self, delta):
        tracks = self.navigation_tracks()
        if not tracks:
            return None
        current = self.track
        if current in tracks:
            return tracks[max(0, min(len(tracks) - 1, tracks.index(current) + delta))]
        # A mouse-selected child of a folded group is absent from visible_tracks.
        ordered = self.all_tracks() + [self.song.master_track]
        if current in ordered:
            index = ordered.index(current)
            candidates = [t for t in tracks if t in ordered and
                          (ordered.index(t) - index) * delta > 0]
            if candidates:
                return candidates[0] if delta > 0 else candidates[-1]
        return current

    def navigate(self, delta):
        target = self.neighbor(delta)
        if self.exists(target):
            self.song.view.selected_track = target

    def toggle_track(self, name):
        track = self.track
        if not self.exists(track):
            return
        if name == "arm" and not read(track, "can_be_armed", False):
            self.show("FaderPort: this track cannot be armed")
            return
        if name == "solo" and track == self.song.master_track:
            return
        value = read(track, name)
        if value is None or (name == "mute" and track == self.song.master_track):
            return
        if not value and name in ("arm", "solo") and read(self.song, "exclusive_" + name, False):
            for other in self.all_tracks():
                if other != track and (name != "arm" or read(other, "can_be_armed", False)):
                    if read(other, name, False):
                        setattr(other, name, False)
        setattr(track, name, not value)

    def document(self):
        view = self.application.view
        focused = read(view, "focused_document_view")
        if focused in ("Session", "Arranger"):
            self._document = focused
        else:
            session = view.is_view_visible("Session")
            arranger = view.is_view_visible("Arranger")
            if session != arranger:
                self._document = "Session" if session else "Arranger"
        return self._document

    def toggle_document(self):
        self.show_view("Arranger" if self.document() == "Session" else "Session")

    def show_view(self, name):
        self.application.view.show_view(name)
        self.application.view.focus_view(name)
        if name in ("Session", "Arranger"):
            self._document = name

    def toggle_browser(self):
        view = self.application.view
        if view.is_view_visible("Browser"):
            view.hide_view("Browser")
        else:
            view.show_view("Browser")

    def focus_track(self):
        self.application.view.focus_view(self.document())

    def scroll(self, delta, zoom=False):
        self.show_view("Arranger")
        view = self.application.view
        direction = "right" if delta > 0 else "left"
        if self.directions is not None:
            direction = getattr(self.directions, direction)
        action = view.zoom_view if zoom else view.scroll_view
        # Acceleration is bounded so an invalid encoder packet cannot block Live.
        for _ in range(min(32, abs(delta))):
            action(direction, "Arranger", False)

    def toggle_play(self):
        if self.song.is_playing:
            self.song.stop_playing()
            self._remember_playback_position()
        else:
            # An insertion marker and the paused playback head are distinct in
            # Live. Resume only our own unchanged pause/seek, otherwise honor
            # the user's insert marker via the native start command.
            resume = (self._playback_intent is not None
                      and self._playback_intent == self._playback_position())
            self.forget_playback_position()
            action = read(self.song, "continue_playing") if resume else None
            (action or self.song.start_playing)()

    def _playback_position(self):
        return (read(self.song, "start_time"), read(self.song, "current_song_time"))

    def _remember_playback_position(self):
        self._playback_intent = self._playback_position()

    def forget_playback_position(self):
        self._playback_intent = None

    def stop_playing(self):
        self.forget_playback_position()
        self.song.stop_playing()

    def return_to_start(self):
        self.song.current_song_time = 0
        if not self.song.is_playing:
            self._remember_playback_position()

    def toggle_record(self):
        if self.document() == "Session":
            recording = (bool(read(self.song, "session_record", False)) or
                         bool(read(self.song, "session_record_status", 0)))
            # Toggle the Session overdub switch in place. trigger_session_record
            # is a different action: it can advance to the next empty clip slot.
            self.song.session_record = not recording
        else:
            self.song.record_mode = not self.song.record_mode

    def record_active(self):
        if self.document() == "Session":
            return (bool(read(self.song, "session_record", False)) or
                    bool(read(self.song, "session_record_status", 0)))
        return bool(self.song.record_mode)

    def jump_bar(self, direction):
        denominator = max(1, read(self.song, "signature_denominator", 4))
        beats = read(self.song, "signature_numerator", 4) * 4.0 / denominator
        self.song.current_song_time = max(0, self.song.current_song_time + beats * direction)
        if not self.song.is_playing:
            self._remember_playback_position()

    def cue(self, delta):
        for _ in range(min(32, abs(delta))):
            allowed = read(self.song, "can_jump_to_next_cue" if delta > 0 else "can_jump_to_prev_cue", False)
            if not allowed:
                break
            if delta > 0:
                self.song.jump_to_next_cue()
            else:
                self.song.jump_to_prev_cue()

    def set_parameter(self, parameter, value):
        if self.parameter_enabled(parameter):
            parameter.value = max(parameter.min, min(parameter.max, value))

    def adjust_parameter(self, parameter, delta, steps, fine):
        if not self.parameter_enabled(parameter):
            self.show("FaderPort: no editable parameter in this mode")
            return
        if read(parameter, "is_quantized", False):
            change = delta
        else:
            change = delta * (parameter.max - parameter.min) / steps * fine
        self.parameter_gesture(parameter, parameter.value + change)

    def parameter_gesture(self, parameter, value):
        if not self.parameter_enabled(parameter):
            return
        parameter.begin_gesture()
        try:
            self.set_parameter(parameter, value)
        finally:
            parameter.end_gesture()

