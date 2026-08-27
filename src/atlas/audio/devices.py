import sounddevice as sd

from atlas.audio.models import AudioDevice


class AudioDeviceManager:

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