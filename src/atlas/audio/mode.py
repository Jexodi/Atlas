from enum import Enum


class ListeningMode(str, Enum):

    CONTINUOUS = "continuous"
    WAKE_WORD = "wake_word"

    @classmethod
    def from_value(
        cls,
        value,
    ) -> "ListeningMode":

        if isinstance(
            value,
            cls,
        ):
            return value

        normalized = str(
            value or ""
        ).strip().casefold()

        aliases = {
            "continuous": cls.CONTINUOUS,
            "continue": cls.CONTINUOUS,
            "normal": cls.CONTINUOUS,
            "normal_mode": cls.CONTINUOUS,
            "always_on": cls.CONTINUOUS,
            "wake_word": cls.WAKE_WORD,
            "wakeword": cls.WAKE_WORD,
            "discord": cls.WAKE_WORD,
            "vocal": cls.WAKE_WORD,
            "voice": cls.WAKE_WORD,
        }

        try:
            return aliases[normalized]
        except KeyError as exc:
            raise ValueError(
                f"Mode d'écoute Atlas invalide : {value!r}"
            ) from exc
