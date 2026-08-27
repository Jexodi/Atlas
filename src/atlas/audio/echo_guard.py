import threading
import time
from collections import deque

import numpy as np


class EchoGuard:

    def __init__(
        self,
        sample_rate: int = 24000,
        history_ms: int = 500,
        correlation_threshold: float = 0.65,
        min_reference_level: float = 0.01,
    ) -> None:

        self.sample_rate = sample_rate

        self.correlation_threshold = (
            correlation_threshold
        )

        self.min_reference_level = (
            min_reference_level
        )

        max_samples = int(
            sample_rate
            * history_ms
            / 1000
        )

        self._reference = deque(
            maxlen=max_samples
        )

        self._lock = threading.Lock()

        self._last_reference_time = 0.0

    def feed_output(
        self,
        pcm16: bytes,
    ) -> None:

        if not pcm16:
            return

        samples = np.frombuffer(
            pcm16,
            dtype="<i2",
        ).astype(
            np.float32
        )

        samples /= 32768.0

        with self._lock:

            self._reference.extend(
                samples.tolist()
            )

            self._last_reference_time = (
                time.monotonic()
            )

    def clear(
        self,
    ) -> None:

        with self._lock:
            self._reference.clear()

        self._last_reference_time = 0.0

    def is_likely_echo(
        self,
        microphone_samples: np.ndarray,
    ) -> bool:

        # Pas de sortie Atlas récente.
        if (
            time.monotonic()
            - self._last_reference_time
            > 0.30
        ):
            return False

        mic = np.asarray(
            microphone_samples,
            dtype=np.float32,
        ).reshape(-1)

        if len(mic) == 0:
            return False

        mic = mic - np.mean(mic)

        mic_energy = float(
            np.sqrt(
                np.mean(
                    np.square(mic)
                )
            )
        )

        if mic_energy < 0.001:
            return False

        with self._lock:

            reference = np.asarray(
                self._reference,
                dtype=np.float32,
            )

        if len(reference) < len(mic):
            return False

        reference = (
            reference
            - np.mean(reference)
        )

        reference_energy = float(
            np.sqrt(
                np.mean(
                    np.square(reference)
                )
            )
        )

        if (
            reference_energy
            < self.min_reference_level
        ):
            return False

        frame_length = len(mic)

        best_correlation = 0.0

        # On teste plusieurs positions dans
        # l'historique pour tolérer le délai
        # haut-parleurs → air → microphone.
        step = max(
            1,
            frame_length // 8,
        )

        start_min = max(
            0,
            len(reference)
            - int(
                self.sample_rate * 0.30
            ),
        )

        for start in range(
            start_min,
            len(reference) - frame_length + 1,
            step,
        ):

            candidate = reference[
                start:
                start + frame_length
            ]

            candidate_energy = float(
                np.sqrt(
                    np.mean(
                        np.square(candidate)
                    )
                )
            )

            if candidate_energy < 0.001:
                continue

            correlation = float(
                np.dot(
                    mic,
                    candidate,
                )
                / (
                    np.linalg.norm(mic)
                    * np.linalg.norm(candidate)
                    + 1e-8
                )
            )

            best_correlation = max(
                best_correlation,
                abs(correlation),
            )

        return (
            best_correlation
            >= self.correlation_threshold
        )