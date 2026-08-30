import threading
import time

import sounddevice as sd

from atlas.audio.models import AudioDevice


class AudioDeviceManager:

    def __init__(self, cache_seconds=5.0):
        self._cache_seconds = float(cache_seconds)
        self._choices_cache = None
        self._choices_cached_at = 0.0
        self._choices_lock = threading.Lock()

    @staticmethod
    def _copy_choices(choices):
        return {
            "inputs": [item.copy() for item in choices["inputs"]],
            "outputs": [item.copy() for item in choices["outputs"]],
        }

    def device_choices(self, refresh=False):
        """Return both directions while avoiding consecutive PortAudio scans."""
        now = time.monotonic()
        with self._choices_lock:
            if (
                not refresh
                and self._choices_cache is not None
                and now - self._choices_cached_at < self._cache_seconds
            ):
                return self._copy_choices(self._choices_cache)

            apis = sd.query_hostapis()
            raw_devices = list(sd.query_devices())
            choices = self._build_choices(raw_devices, apis)
            self._choices_cache = choices
            self._choices_cached_at = time.monotonic()
            return self._copy_choices(choices)

    @staticmethod
    def _build_choices(raw_devices, apis):
        inputs = []
        outputs = []
        seen_inputs = set()
        seen_outputs = set()

        def host_api_name(device):
            return str(apis[device["hostapi"]]["name"])

        def api_priority(name):
            normalized = name.casefold()
            if "wasapi" in normalized:
                return 0
            if "directsound" in normalized:
                return 1
            if normalized == "mme" or " mme" in normalized:
                return 2
            if "wdm-ks" in normalized or "wdm ks" in normalized:
                return 3
            return 4

        def preferred_api(channel_name, default_position):
            try:
                default_index = int(sd.default.device[default_position])
            except (TypeError, ValueError, IndexError):
                default_index = -1

            if 0 <= default_index < len(raw_devices):
                default_device = raw_devices[default_index]
                if int(default_device[channel_name]) > 0:
                    # Reuse the host API selected by Windows/PortAudio for the
                    # default endpoint. This is generally the most compatible
                    # backend for the current drivers (MME on some systems,
                    # WASAPI or DirectSound on others).
                    return host_api_name(default_device)

            candidates = {
                host_api_name(device)
                for device in raw_devices
                if int(device[channel_name]) > 0
            }
            return min(candidates, key=api_priority) if candidates else None

        preferred_input_api = preferred_api("max_input_channels", 0)
        preferred_output_api = preferred_api("max_output_channels", 1)

        for index, device in enumerate(raw_devices):
            host_api = host_api_name(device)
            device_name = str(device["name"]).strip()
            # PortAudio expose les mêmes périphériques via plusieurs API. Les
            # noms MME peuvent être tronqués et ne permettent pas une
            # déduplication fiable. Une seule API est donc exposée par sens :
            # celle du périphérique Windows/PortAudio par défaut. Les autres
            # API ne servent que de repli si aucun défaut n'est exploitable.
            deduplication_key = " ".join(device_name.casefold().split())
            choice = {
                "id": f"{host_api}::{device_name}",
                "label": f"{device_name} ({host_api})",
                "index": index,
            }
            if (
                int(device["max_input_channels"]) > 0
                and host_api == preferred_input_api
                and deduplication_key not in seen_inputs
            ):
                inputs.append(choice.copy())
                seen_inputs.add(deduplication_key)
            if (
                int(device["max_output_channels"]) > 0
                and host_api == preferred_output_api
                and deduplication_key not in seen_outputs
            ):
                outputs.append(choice.copy())
                seen_outputs.add(deduplication_key)
        return {"inputs": inputs, "outputs": outputs}

    def output_choices(self):
        return self.device_choices()["outputs"]

    def resolve_output(self, selection=None):
        if selection is None or selection == "":
            index = sd.default.device[1]
            return next((d for d in self.list_output_devices() if d.index == index), None)
        choices = self.output_choices()
        match = next((d for d in choices if d['id'] == selection), None)
        if isinstance(selection, int) and not isinstance(selection, bool):
            match = next((d for d in choices if d['index'] == selection), None)
        if match is None:
            raise ValueError("La sortie audio choisie est indisponible.")
        return next(d for d in self.list_output_devices() if d.index == match['index'])

    def input_choices(self):
        """Persist a name + host API, never a transient PortAudio index."""
        return self.device_choices()["inputs"]

    def resolve_input(self, selection=None):
        if selection is None or selection == "":
            return self.get_default_input()
        choices = self.input_choices()
        match = next((d for d in choices if d['id'] == selection), None)
        # Migration of an old numeric configuration, if any.
        if isinstance(selection, int) and not isinstance(selection, bool):
            match = next((d for d in choices if d['index'] == selection), None)
        if match is None:
            raise ValueError("Le microphone choisi est indisponible.")
        return next(d for d in self.list_input_devices() if d.index == match['index'])

    def list_devices(
        self,
    ) -> list[AudioDevice]:

        devices = []

        for index, raw_device in enumerate(
            sd.query_devices()
        ):

            input_channels = int(
                raw_device["max_input_channels"]
            )

            output_channels = int(
                raw_device["max_output_channels"]
            )

            devices.append(
                AudioDevice(
                    index=index,
                    name=str(
                        raw_device["name"]
                    ),
                    input_channels=input_channels,
                    output_channels=output_channels,
                    default_sample_rate=float(
                        raw_device[
                            "default_samplerate"
                        ]
                    ),
                    is_input=(
                        input_channels > 0
                    ),
                    is_output=(
                        output_channels > 0
                    ),
                )
            )

        return devices

    def list_input_devices(
        self,
    ) -> list[AudioDevice]:

        return [
            device
            for device in self.list_devices()
            if device.is_input
        ]

    def list_output_devices(
        self,
    ) -> list[AudioDevice]:

        return [
            device
            for device in self.list_devices()
            if device.is_output
        ]

    def get_default_input(
        self,
    ) -> AudioDevice | None:

        default_input = sd.default.device[0]

        if default_input is None:
            return None

        if default_input < 0:
            return None

        devices = self.list_devices()

        for device in devices:

            if device.index == default_input:
                return device

        return None
