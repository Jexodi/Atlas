from dataclasses import dataclass


@dataclass(slots=True)
class AudioDevice:
    index: int
    name: str

    input_channels: int
    output_channels: int

    default_sample_rate: float

    is_input: bool
    is_output: bool