from types import SimpleNamespace


class Observable:
    events = ()

    def __init__(self, **values):
        object.__setattr__(self, "listeners", {})
        object.__setattr__(self, "valid", True)
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def __bool__(self):
        return self.valid

    def __getattr__(self, name):
        for prefix, operation in (("add_", self.add), ("remove_", self.remove)):
            if name.startswith(prefix) and name.endswith("_listener"):
                event = name[len(prefix):-len("_listener")]
                if event in self.events:
                    return lambda callback: operation(event, callback)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        old = self.__dict__.get(name)
        object.__setattr__(self, name, value)
        if old != value and name in self.events:
            self.emit(name)

    def add(self, event, callback):
        callbacks = self.listeners.setdefault(event, [])
        assert callback not in callbacks, (event, "duplicate listener")
        callbacks.append(callback)

    def remove(self, event, callback):
        self.listeners[event].remove(callback)

    def emit(self, event):
        for callback in tuple(self.listeners.get(event, ())):
            callback()

    def listener_count(self):
        return sum(len(callbacks) for callbacks in self.listeners.values())


class Parameter(Observable):
    events = ("value", "is_enabled", "automation_state")

    def __init__(self, value=0.5, minimum=0.0, maximum=1.0, default=0.5, quantized=False):
        super().__init__(value=value, min=minimum, max=maximum,
                         default_value=default, is_quantized=quantized,
                         is_enabled=True, automation_state=0)
        self.gestures = []

    def begin_gesture(self):
        self.gestures.append("begin")

    def end_gesture(self):
        self.gestures.append("end")


class TrackView(Observable):
    events = ("selected_device",)


class Mixer(Observable):
    events = ("panning_mode",)


class Device(Observable):
    events = ("parameters",)


class Track(Observable):
    events = ("arm", "mute", "solo", "can_be_armed", "devices")

    def __init__(self, name, armable=True):
        switch = Parameter(1, 0, 1, 1, True)
        device = Device(parameters=[switch], name="Effect")
        super().__init__(name=name, can_be_armed=armable, arm=False, solo=False, mute=False,
                         mixer_device=Mixer(volume=Parameter(), panning=Parameter(0, -1, 1, 0), panning_mode=0),
                         view=TrackView(selected_device=device), devices=[device])


class SongView(Observable):
    events = ("selected_track", "selected_parameter", "draw_mode")


class AppView(Observable):
    events = ("focused_document_view",)

    def __init__(self):
        super().__init__(focused_document_view="Arranger")
        self.visible = {"Arranger"}
        self.calls = []

    def is_view_visible(self, name):
        return name in self.visible

    def show_view(self, name):
        self.calls.append(("show", name))
        if name in ("Session", "Arranger"):
            self.visible.difference_update({"Session", "Arranger"})
        self.visible.add(name)

    def focus_view(self, name):
        self.calls.append(("focus", name))
        if name in ("Session", "Arranger"):
            self.focused_document_view = name

    def hide_view(self, name):
        self.calls.append(("hide", name))
        self.visible.discard(name)

    def scroll_view(self, *args):
        self.calls.append(("scroll",) + args)

    def zoom_view(self, *args):
        self.calls.append(("zoom",) + args)


class Song(Observable):
    events = ("tracks", "visible_tracks", "return_tracks", "is_playing", "record_mode", "session_record",
              "session_record_status", "loop", "metronome", "session_automation_record", "re_enable_automation_enabled",
              "can_undo", "can_redo", "can_jump_to_next_cue", "can_jump_to_prev_cue", "start_time")

    def __init__(self, count=40):
        tracks = [Track("Track %d" % (index + 1)) for index in range(count)]
        super().__init__(tracks=tracks, visible_tracks=list(tracks), return_tracks=[Track("Return", False)],
                         master_track=Track("Master", False),
                         view=SongView(selected_track=tracks[0], selected_parameter=None, draw_mode=False),
                         is_playing=False, record_mode=False, session_record=False, session_record_status=0,
                         loop=False, metronome=False, session_automation_record=False,
                         re_enable_automation_enabled=False, exclusive_arm=True, exclusive_solo=True,
                         can_undo=True, can_redo=True, current_song_time=16.0, start_time=16.0,
                         signature_numerator=4, signature_denominator=4,
                         can_jump_to_next_cue=True, can_jump_to_prev_cue=True)
        self.calls = []

    def start_playing(self):
        self.calls.append("start_playing")
        self.current_song_time = self.start_time
        self.is_playing = True

    def continue_playing(self):
        self.calls.append("continue_playing")
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False

    def trigger_session_record(self):
        self.calls.append("session_record")
        self.session_record = True
        self.session_record_status = 2

    def re_enable_automation(self):
        self.calls.append("re_enable_automation")
        self.re_enable_automation_enabled = False

    def set_or_delete_cue(self):
        self.calls.append("cue")

    def jump_to_next_cue(self):
        self.calls.append("next_cue")

    def jump_to_prev_cue(self):
        self.calls.append("prev_cue")

    def undo(self):
        self.calls.append("undo")

    def redo(self):
        self.calls.append("redo")


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, duration=0.1):
        self.now += duration


def environment():
    song = Song()
    return song, SimpleNamespace(view=AppView())

