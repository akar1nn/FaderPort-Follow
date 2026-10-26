import unittest

from FaderPort_Follow.live_api import Bindings


class ListenerTarget:
    def __init__(self, invalid_on_remove=False):
        self.invalid_on_remove = invalid_on_remove
        self.callbacks = []

    def add_value_listener(self, callback):
        self.callbacks.append(callback)

    def remove_value_listener(self, callback):
        if self.invalid_on_remove:
            # Boost.Python.ArgumentError derives from TypeError; deleted LOM
            # handles may fail signature conversion before calling C++.
            raise TypeError('invalid native handle')
        self.callbacks.remove(callback)


class BindingsTests(unittest.TestCase):
    def test_invalid_native_handle_does_not_skip_remaining_listener_cleanup(self):
        bindings = Bindings(lambda message: None)
        valid, deleted = ListenerTarget(), ListenerTarget(True)
        callback = lambda: None
        bindings.add(valid, 'value', callback)
        bindings.add(deleted, 'value', callback)
        bindings.clear()
        self.assertEqual(valid.callbacks, [])
        self.assertEqual(bindings._items, [])
        bindings.clear()  # Repeated cleanup is harmless.
