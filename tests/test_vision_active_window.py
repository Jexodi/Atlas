from __future__ import annotations

from pathlib import Path

from atlas.skills.vision import AnalyzeActiveWindowSkill
from atlas.vision import VisionPolicy
from atlas.vision.capture import ActiveWindowCapture, ActiveWindowCapturer


class _Storage:
    def __init__(self, root: Path):
        self.root = root

    def workspace_path(self, relative: str) -> Path:
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path


class _Analyzer:
    def analyze_image(self, image_path, prompt):
        assert Path(image_path).is_file()
        assert "Demande utilisateur" in prompt
        return "Une boîte de dialogue d'erreur est visible."


class _Capturer:
    def capture(self, output_dir):
        path = Path(output_dir) / "capture.png"
        path.write_bytes(b"fake-png")
        return ActiveWindowCapture(
            path=path,
            title="Erreur de test",
            process_id=1234,
            width=800,
            height=600,
        )


def test_png_writer_produces_png(tmp_path):
    path = tmp_path / "sample.png"
    # 1 pixel BGRA : rouge opaque.
    ActiveWindowCapturer._write_png(path, 1, 1, bytes([0, 0, 255, 255]))
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in data
    assert data.endswith(b"IEND\xaeB`\x82")


def test_vision_skill_requires_confirmation(tmp_path):
    skill = AnalyzeActiveWindowSkill(
        storage=_Storage(tmp_path),
        analyzer=_Analyzer(),
        policy=VisionPolicy(),
        privacy_mode_provider=lambda: False,
        logger=type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None})(),
    )
    assert skill.always_requires_confirmation is True
    assert "envoyer cette image à OpenAI" in skill.get_confirmation_message(prompt="Regarde cette erreur")


def test_vision_skill_analyzes_and_deletes_temporary_capture(tmp_path):
    skill = AnalyzeActiveWindowSkill(
        storage=_Storage(tmp_path),
        analyzer=_Analyzer(),
        policy=VisionPolicy(),
        privacy_mode_provider=lambda: False,
        logger=type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None})(),
    )
    skill.capturer = _Capturer()
    result = skill.execute(prompt="Explique cette erreur")
    assert result.success is True
    assert result.data["analysis"].startswith("Une boîte")
    assert result.data["capture_persisted"] is False
    assert not (tmp_path / "Temp/Vision/capture.png").exists()


def test_vision_skill_blocked_in_privacy_mode(tmp_path):
    skill = AnalyzeActiveWindowSkill(
        storage=_Storage(tmp_path),
        analyzer=_Analyzer(),
        policy=VisionPolicy(),
        privacy_mode_provider=lambda: True,
        logger=type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None})(),
    )
    skill.capturer = _Capturer()
    result = skill.execute(prompt="Regarde")
    assert result.success is False
    assert "Confidentialité" in result.message
