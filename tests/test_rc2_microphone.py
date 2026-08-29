"""Hardware-free regressions for microphone selection and rollback."""
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("sounddevice", MagicMock())
from atlas.audio.devices import AudioDeviceManager
from atlas.audio.capture import MicrophoneCapture


class MicrophoneTests(unittest.TestCase):
    def setUp(self):
        self.raw = [dict(name=name, hostapi=0, max_input_channels=inputs,
                         max_output_channels=0, default_samplerate=48000)
                    for name, inputs in [("A", 1), ("B", 1), ("Output", 0)]]
        self.sd = patch("atlas.audio.devices.sd").start()
        self.addCleanup(patch.stopall)
        self.sd.query_devices.return_value = self.raw
        self.sd.query_hostapis.return_value = [{"name": "WASAPI"}]
        self.sd.default.device = (1, -1)
        self.devices = AudioDeviceManager()

    def test_initial_default(self):
        self.assertEqual(self.devices.resolve_input().name, "B")
        self.assertEqual(self.devices.resolve_input("").name, "B")

    def test_stable_name_survives_index_change(self):
        self.raw.reverse()
        self.assertEqual(self.devices.resolve_input("WASAPI::A").index, 2)

    def test_outputs_excluded_and_missing_rejected(self):
        self.assertEqual(len(self.devices.input_choices()), 2)
        with self.assertRaises(ValueError):
            self.devices.resolve_input("WASAPI::Missing")

    def test_no_default(self):
        self.sd.default.device = (-1, -1)
        self.assertIsNone(self.devices.resolve_input())

    def test_switch_success(self):
        mic = MicrophoneCapture(MagicMock(), device_index=0)
        mic._running = True
        with patch("atlas.audio.capture.sd.InputStream") as stream:
            mic.switch_device(1)
            self.assertEqual(mic.device_index, 1)
            self.assertTrue(mic.running)
            stream.return_value.start.assert_called_once()

    def test_switch_failure_restores_old_device(self):
        mic = MicrophoneCapture(MagicMock(), device_index=0)
        mic._running = True
        with patch("atlas.audio.capture.sd.InputStream", side_effect=[OSError("busy"), MagicMock()]):
            with self.assertRaisesRegex(RuntimeError, "restauré"):
                mic.switch_device(1)
        self.assertEqual(mic.device_index, 0)
        self.assertTrue(mic.running)

    def test_inactive_capture_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "inactive"):
            MicrophoneCapture(MagicMock()).switch_device(1)


if __name__ == "__main__":
    unittest.main()
