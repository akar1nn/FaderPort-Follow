"""Live 12 entrypoint. Registered elements let v2 install MIDI forwarding."""

import logging
import traceback

import Live
from ableton.v2.base import liveobj_valid
from ableton.v2.control_surface import ControlSurface, MIDI_CC_TYPE, MIDI_NOTE_TYPE, MIDI_PB_TYPE
from ableton.v2.control_surface.elements import ButtonElement, SliderElement

from . import __version__, protocol, settings
from .controller import FollowController
from .live_api import LiveBridge


logger = logging.getLogger(__name__)


class FaderPortFollow(ControlSurface):
    def __init__(self, c_instance):
        self._follow = None
        self._inputs = []
        self._midi_output_failed = False
        super(FaderPortFollow, self).__init__(c_instance=c_instance)
        with self.component_guard():
            for note in protocol.BUTTONS:
                element = ButtonElement(True, MIDI_NOTE_TYPE, 0, note,
                                        name="FP_" + protocol.NAMES.get(note, str(note)))
                element.add_value_listener(self._forwarded)
                self._inputs.append(element)
            continuous_inputs = [(MIDI_PB_TYPE, 0, "FP_Fader")]
            continuous_inputs.extend((MIDI_CC_TYPE, cc, "FP_Encoder_%02X" % cc)
                                     for cc in protocol.ENCODER_CCS)
            for message_type, identifier, name in continuous_inputs:
                element = SliderElement(message_type, 0, identifier, name=name)
                element.add_value_listener(self._forwarded)
                self._inputs.append(element)
            api = LiveBridge(self.song, self.application, self._log, self.show_message,
                             Live.Application.Application.View.NavDirection, liveobj_valid)
            self._follow = FollowController(api, self._output)
        self._log("Loaded %s; native Studio One mode; touch required=%s" %
                  (__version__, settings.REQUIRE_FADER_TOUCH))
        self.show_message("FaderPort Follow %s: native Studio One mode" % __version__)

    def _forwarded(self, value):
        # A listener requests script forwarding. The raw receive hook below
        # handles the actual event once, including touch and release ordering.
        pass

    def receive_midi(self, midi_bytes):
        if self._follow is not None:
            self._follow.receive_midi(tuple(midi_bytes))
        super(FaderPortFollow, self).receive_midi(midi_bytes)

    def receive_midi_chunk(self, midi_chunk):
        # Live may deliver batches instead of calling receive_midi. Keep the
        # original ordering: merging repeated fader/touch messages first would
        # lose the gesture boundaries and could target a different track.
        messages = tuple(tuple(message) for message in midi_chunk)
        if self._follow is not None:
            for message in messages:
                self._follow.receive_midi(message)
        super(FaderPortFollow, self).receive_midi_chunk(messages)

    def update_display(self):
        super(FaderPortFollow, self).update_display()
        if self._follow is not None:
            self._follow.tick()

    def refresh_state(self):
        super(FaderPortFollow, self).refresh_state()
        if self._follow is not None:
            self._follow.refresh_state()

    def port_settings_changed(self):
        if self._follow is not None:
            self._follow.reset_input_on_port_change()
        # v2 calls refresh_state here, resending all feedback on reconnect.
        super(FaderPortFollow, self).port_settings_changed()

    def _output(self, message):
        if settings.DEBUG_MIDI:
            self._log("TX " + " ".join("%02X" % byte for byte in message))
        self._send_midi(tuple(message))

    def _log(self, message):
        # v2 uses Python logging, which Live routes to Preferences/Log.txt.
        # log_message belongs to the older framework, not v2 ControlSurface.
        logger.info("[FaderPort Follow] %s", message)

    def _do_send_midi(self, midi_event_bytes):
        # Check the actual host send, including messages queued by v2.
        sent = super(FaderPortFollow, self)._do_send_midi(midi_event_bytes)
        if not sent and not self._midi_output_failed:
            self._log("ERROR MIDI output failed; check the selected output port")
            self.show_message("FaderPort Follow: MIDI output failed; check Output port")
        self._midi_output_failed = not sent
        return sent

    def disconnect(self):
        try:
            if self._follow is not None:
                self._follow.disconnect()
                self._follow = None
        except Exception:
            self._log("ERROR disconnect: " + traceback.format_exc())
        finally:
            super(FaderPortFollow, self).disconnect()
