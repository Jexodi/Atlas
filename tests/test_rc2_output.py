import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault('sounddevice', MagicMock())
from atlas.audio.devices import AudioDeviceManager
from atlas.audio.output import AudioOutput


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.raw = [dict(name=name, hostapi=0, max_input_channels=inputs,
                        max_output_channels=outputs, default_samplerate=48000)
                    for name, inputs, outputs in [('Mic', 1, 0), ('Speakers', 0, 2), ('Headset', 1, 2)]]
        self.sd = patch('atlas.audio.devices.sd').start()
        self.addCleanup(patch.stopall)
        self.sd.query_devices.return_value = self.raw
        self.sd.query_hostapis.return_value = [{'name': 'WASAPI'}]
        self.sd.default.device = (0, 1)
        self.devices = AudioDeviceManager()

    def test_default_input_and_output_are_independent(self):
        self.assertEqual(self.devices.resolve_input().name, 'Mic')
        self.assertEqual(self.devices.resolve_output().name, 'Speakers')

    def test_lists_filter_by_direction(self):
        self.assertEqual([d['index'] for d in self.devices.input_choices()], [0, 2])
        self.assertEqual([d['index'] for d in self.devices.output_choices()], [1, 2])
        self.sd.query_devices.assert_called_once()

    def test_combined_inventory_uses_one_snapshot(self):
        choices = self.devices.device_choices()
        self.assertEqual([d['index'] for d in choices['inputs']], [0, 2])
        self.assertEqual([d['index'] for d in choices['outputs']], [1, 2])
        self.sd.query_devices.assert_called_once()

    def test_expired_inventory_is_refreshed(self):
        devices = AudioDeviceManager(cache_seconds=0)
        devices.input_choices()
        devices.output_choices()
        self.assertEqual(self.sd.query_devices.call_count, 2)

    def test_saved_output_survives_reordering(self):
        self.raw.reverse()
        self.assertEqual(self.devices.resolve_output('WASAPI::Headset').index, 0)

    def test_missing_output_rejected(self):
        with self.assertRaises(ValueError):
            self.devices.resolve_output('WASAPI::Missing')

    def test_no_windows_default(self):
        self.sd.default.device = (0, -1)
        self.assertIsNone(self.devices.resolve_output())

    def test_output_switch_preserves_audio_and_task(self):
        output = AudioOutput(MagicMock(), device_index=1)
        output._running = output.speaking = True
        output._buffer.extend(b'1234')
        with patch('atlas.audio.output.sd.RawOutputStream') as stream:
            output.switch_device(2)
            self.assertEqual(output.device_index, 2)
            self.assertTrue(output._running)
            self.assertTrue(output.speaking)
            self.assertEqual(output._buffer, b'1234')
            stream.return_value.start.assert_called_once()

    def test_failed_output_restores_previous(self):
        output = AudioOutput(MagicMock(), device_index=1)
        output._running = True
        with patch('atlas.audio.output.sd.RawOutputStream', side_effect=[OSError('busy'), MagicMock()]):
            with self.assertRaisesRegex(RuntimeError, 'restaurée'):
                output.switch_device(2)
        self.assertEqual(output.device_index, 1)
        self.assertTrue(output._running)

    def test_inactive_output_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'inactive'):
            AudioOutput(MagicMock()).switch_device(2)


if __name__ == '__main__':
    unittest.main()
