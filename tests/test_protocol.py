import unittest

from FaderPort_Follow import protocol as p


class ProtocolTests(unittest.TestCase):
    def test_published_native_ids_are_not_mcu_channel_strip_ids(self):
        self.assertEqual((p.ARM, p.SOLO, p.MUTE, p.CHANNEL, p.MASTER, p.FADER_TOUCH),
                         (0x00, 0x08, 0x10, 0x36, 0x3A, 0x68))
        self.assertEqual(len(p.BUTTONS), len(set(p.BUTTONS)))

    def test_note_release_in_both_forms(self):
        self.assertEqual(p.decode((0x90, p.ARM, 127)), ("button", p.ARM, True))
        for status, velocity in ((0x80, 127), (0x80, 0), (0x90, 0)):
            self.assertEqual(p.decode((status, p.ARM, velocity)), ("button", p.ARM, False))

    def test_other_channels_and_malformed_messages_are_ignored(self):
        for message in ((), (0x90,), (0x90, 0, 127, 0), (0x91, 0, 127),
                        (0x90, 127, 127), (0x90, 0, 128), (0xB0, 17, 1), (0xF8, 0, 0)):
            self.assertIsNone(p.decode(message), message)

    def test_fader_all_14_bits_and_endpoints(self):
        for raw in (0, 1, 127, 128, 8192, 16383):
            message = p.fader_message(raw / 16383.0)
            self.assertEqual(p.decode(message), ("fader", None, raw))
        self.assertEqual(p.fader_message(-1), (0xE0, 0, 0))
        self.assertEqual(p.fader_message(2), (0xE0, 127, 127))

    def test_encoder_direction_count_and_alternative_formats(self):
        for raw, delta in ((0, 0), (1, 1), (3, 3), (0x40, 0), (0x41, -1), (0x43, -3)):
            self.assertEqual(p.decode((0xB0, 0x3C, raw))[2], delta)
            self.assertEqual(p.decode((0xB0, 0x3C, raw), invert=True)[2], -delta)
        self.assertEqual(p.encoder_delta(127, "twos_complement"), -1)
        self.assertEqual(p.encoder_delta(63, "binary_offset"), -1)
        with self.assertRaises(ValueError):
            p.encoder_delta(1, "unknown")

    def test_led_flash_and_rgb_use_separate_output_channels(self):
        self.assertEqual(p.led_message(p.LINK, 2), (0x90, p.LINK, 1))
        self.assertEqual(p.color_messages(p.PAN, (127, 60, 0)),
                         ((0x91, p.PAN, 127), (0x92, p.PAN, 60), (0x93, p.PAN, 0)))

    def test_fp2_cc10_encoder_variant(self):
        self.assertEqual(p.decode((0xB0, 0x10, 1)), ("encoder", None, 1))
        self.assertEqual(p.decode((0xB0, 0x10, 0x41)), ("encoder", None, -1))

