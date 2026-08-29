from __future__ import annotations

from abc import ABC, abstractmethod
import atexit
from pathlib import Path
import subprocess
import threading
import time

import numpy as np


class WakeWordDetector(ABC):

    @abstractmethod
    def process(
        self,
        samples: np.ndarray,
        sample_rate: int,
    ) -> bool:
        raise NotImplementedError

    def reset(self) -> None:
        pass

    def close(self) -> None:
        pass


class WindowsSpeechWakeWordDetector(
    WakeWordDetector
):

    def __init__(
        self,
        logger,
        wake_word: str = "SIDERON",
        culture: str = "fr-FR",
        min_confidence: float = 0.55,
        startup_timeout_seconds: float = 8.0,
    ) -> None:

        self.logger = logger
        self.wake_word = str(wake_word).strip()
        self.culture = str(culture).strip()
        self.min_confidence = max(
            0.0,
            min(
                1.0,
                float(min_confidence),
            ),
        )
        self.startup_timeout_seconds = max(
            1.0,
            float(startup_timeout_seconds),
        )

        if not self.wake_word:
            raise ValueError(
                "Le wake word ne peut pas etre vide."
            )

        self._detected = threading.Event()
        self._closed = threading.Event()
        self._ready = threading.Event()

        self._startup_error: RuntimeError | None = None
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None

        self._worker_path = (
            Path(__file__)
            .resolve()
            .with_name("windows_wakeword.ps1")
        )

        if not self._worker_path.is_file():
            raise FileNotFoundError(
                "Worker Windows wake word introuvable : "
                f"{self._worker_path}"
            )

        self._start_worker()
        atexit.register(self.close)

    @property
    def ready(
        self,
    ) -> bool:

        return (
            self._ready.is_set()
            and not self._closed.is_set()
        )

    def process(
        self,
        samples: np.ndarray,
        sample_rate: int,
    ) -> bool:

        # Windows Speech utilise directement le micro par defaut.
        # Les echantillons du pipeline Sideron ne sont pas envoyes
        # au worker et ne quittent pas le PC.
        del samples
        del sample_rate

        if not self.ready:
            return False

        if not self._detected.is_set():
            return False

        self._detected.clear()
        return True

    def reset(
        self,
    ) -> None:

        self._detected.clear()

    def close(
        self,
    ) -> None:

        if self._closed.is_set():
            return

        self._closed.set()
        self._detected.clear()

        process = self._process

        if process is None:
            return

        if process.poll() is not None:
            return

        try:
            process.terminate()
            process.wait(timeout=2.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _start_worker(
        self,
    ) -> None:

        command = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._worker_path),
            "-WakeWord",
            self.wake_word,
            "-Culture",
            self.culture,
            "-MinConfidence",
            str(self.min_confidence),
        ]

        creation_flags = 0

        if hasattr(
            subprocess,
            "CREATE_NO_WINDOW",
        ):
            creation_flags = (
                subprocess.CREATE_NO_WINDOW
            )

        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Windows PowerShell est introuvable."
            ) from exc

        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="SideronWindowsWakeWord",
            daemon=True,
        )
        self._reader_thread.start()

        deadline = (
            time.monotonic()
            + self.startup_timeout_seconds
        )

        while time.monotonic() < deadline:

            if self._ready.wait(timeout=0.05):
                break

            if self._startup_error is not None:
                break

            if (
                self._process is not None
                and self._process.poll() is not None
            ):
                break

        if self._startup_error is not None:

            error = self._startup_error
            self.close()
            raise error

        if not self._ready.is_set():

            exit_code = None

            if self._process is not None:
                exit_code = self._process.poll()

            self.close()

            raise RuntimeError(
                "Le moteur Windows Speech n'a pas demarre "
                f"correctement (code={exit_code})."
            )

        self.logger.info(
            "Wake word Windows Speech initialise : "
            "mot=%s | culture=%s | confiance>=%.2f",
            self.wake_word,
            self.culture,
            self.min_confidence,
        )

    def _reader_loop(
        self,
    ) -> None:

        process = self._process

        if (
            process is None
            or process.stdout is None
        ):
            return

        try:
            for raw_line in process.stdout:

                if self._closed.is_set():
                    return

                line = raw_line.strip()

                if not line:
                    continue

                parts = line.split("|", 2)
                kind = parts[0].upper()

                if kind == "READY":

                    if len(parts) >= 3:
                        self.logger.info(
                            "Windows Speech pret : "
                            "culture=%s | wake_word=%s",
                            parts[1],
                            parts[2],
                        )

                    self._ready.set()
                    continue

                if kind == "WAKE":

                    confidence = None

                    if len(parts) >= 2:
                        try:
                            confidence = float(parts[1])
                        except ValueError:
                            confidence = None

                    self.logger.info(
                        "Wake word Windows detecte%s.",
                        (
                            f" (confiance={confidence:.3f})"
                            if confidence is not None
                            else ""
                        ),
                    )

                    self._detected.set()
                    continue

                if kind == "WARN":
                    self.logger.warning(
                        "Windows Speech : %s",
                        line,
                    )
                    continue

                if kind == "ERROR":

                    message = (
                        parts[2]
                        if len(parts) >= 3
                        else line
                    )

                    self._startup_error = RuntimeError(
                        "Windows Speech indisponible : "
                        f"{message}"
                    )

                    self._ready.set()
                    return

                self.logger.debug(
                    "Windows Speech : %s",
                    line,
                )

        except Exception:

            if not self._closed.is_set():
                self.logger.exception(
                    "Erreur du lecteur Windows wake word."
                )


class DummyWakeWordDetector(
    WakeWordDetector
):

    def process(
        self,
        samples: np.ndarray,
        sample_rate: int,
    ) -> bool:

        return False


def create_wake_word_detector(
    config,
    logger,
) -> WakeWordDetector | None:

    enabled = bool(
        config.get(
            "audio.wake_word.enabled",
            True,
        )
    )

    if not enabled:
        logger.info(
            "Wake word desactive."
        )
        return None

    engine = str(
        config.get(
            "audio.wake_word.engine",
            "windows_speech",
        )
    ).strip().casefold()

    # Migration automatique des anciens essais.
    if engine in {
        "openwakeword",
        "vosk",
    }:
        logger.info(
            "Migration wake word %s -> windows_speech.",
            engine,
        )
        engine = "windows_speech"

    if engine not in {
        "windows",
        "windows_speech",
        "system_speech",
        "sapi",
    }:
        logger.error(
            "Moteur wake word inconnu : %s",
            engine,
        )
        return None

    try:
        return WindowsSpeechWakeWordDetector(
            logger=logger,
            wake_word=config.get(
                "audio.wake_word.word",
                "SIDERON",
            ),
            culture=config.get(
                "audio.wake_word.culture",
                "fr-FR",
            ),
            min_confidence=config.get(
                "audio.wake_word.min_confidence",
                0.55,
            ),
            startup_timeout_seconds=config.get(
                "audio.wake_word.startup_timeout_seconds",
                8.0,
            ),
        )
    except Exception:
        logger.exception(
            "Impossible d'initialiser "
            "le wake word Windows Speech."
        )
        return None
