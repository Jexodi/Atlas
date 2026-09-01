from __future__ import annotations

from atlas.core.event_bus import EventBus
from atlas.memory import MemoryManager
from atlas.security.permissions import PermissionMode
from atlas.security.policy import PermissionEngine
from atlas.skills.manager import SkillManager
from atlas.skills.memory import (
    DeleteMemorySkill,
    ListMemoriesSkill,
    SearchMemorySkill,
    StoreMemorySkill,
)
from atlas.skills.registry import SkillRegistry


class _Logger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


def _memory(tmp_path):
    manager = MemoryManager(tmp_path / "Memory" / "sideron-memory.db")
    manager.initialize()
    return manager


def test_memory_store_search_list_delete(tmp_path):
    memory = _memory(tmp_path)

    first = memory.store(
        content="Le volume préféré est 35 %.",
        category="preference",
        key="audio.volume.default",
        tags=["audio", "volume"],
    )

    assert first.id > 0
    assert first.category == "preference"
    assert first.tags == ("audio", "volume")

    results = memory.search("volume")
    assert [item.id for item in results] == [first.id]

    listed = memory.list(category="preference")
    assert [item.id for item in listed] == [first.id]

    assert memory.delete(first.id) is True
    assert memory.get(first.id) is None
    assert memory.delete(first.id) is False


def test_memory_key_updates_without_duplicate(tmp_path):
    memory = _memory(tmp_path)

    first = memory.store(
        content="Le casque préféré est A.",
        category="preference",
        key="audio.output.headset",
    )
    second = memory.store(
        content="Le casque préféré est B.",
        category="preference",
        key="audio.output.headset",
    )

    assert second.id == first.id
    records = memory.list(category="preference")
    assert len(records) == 1
    assert records[0].content == "Le casque préféré est B."


def test_memory_database_stays_in_memory_directory(tmp_path):
    memory = _memory(tmp_path)

    assert memory.database_path.parent.name == "Memory"
    assert memory.database_path.name == "sideron-memory.db"
    assert memory.database_path.exists()


def test_memory_skills_work_in_restricted_mode(tmp_path):
    memory = _memory(tmp_path)
    registry = SkillRegistry()
    registry.register(StoreMemorySkill(memory))
    registry.register(SearchMemorySkill(memory))
    registry.register(ListMemoriesSkill(memory))
    registry.register(DeleteMemorySkill(memory))

    manager = SkillManager(
        registry=registry,
        permission_engine=PermissionEngine(),
        event_bus=EventBus(),
        permission_mode=PermissionMode.RESTRICTED,
        logger=_Logger(),
    )

    stored = manager.execute(
        "memory.store",
        content="Mon casque est le Creative Live! A3.",
        category="alias",
        key="audio.headset",
        tags=["audio"],
    )
    assert stored.success is True
    memory_id = stored.data["id"]

    found = manager.execute("memory.search", query="Creative")
    assert found.success is True
    assert found.data["memories"][0]["id"] == memory_id

    pending_delete = manager.execute("memory.delete", memory_id=memory_id)
    assert pending_delete.success is False
    assert pending_delete.confirmation_required is True

    deleted = manager.execute(
        "memory.delete",
        memory_id=memory_id,
        confirmed=True,
    )
    assert deleted.success is True


def test_memory_search_handles_natural_language_keywords(tmp_path):
    memory = _memory(tmp_path)

    headset = memory.store(
        content="Mon casque est le Creative Live! A3.",
        category="alias",
        key="audio.headset",
        tags=["audio", "casque"],
    )
    memory.store(
        content="Je préfère le volume à 35 %.",
        category="preference",
        key="audio.volume.default",
        tags=["audio", "volume"],
    )

    results = memory.search("quel est mon casque audio")

    assert results
    assert results[0].id == headset.id


def test_memory_search_is_accent_insensitive(tmp_path):
    memory = _memory(tmp_path)

    preferred = memory.store(
        content="Ma préférence audio utilise les haut-parleurs du bureau.",
        category="preference",
        key="audio.output.office",
        tags=["préférence", "audio"],
    )

    results = memory.search("preference audio")

    assert results
    assert results[0].id == preferred.id


def test_memory_key_aliases_update_existing_preference(tmp_path):
    memory = _memory(tmp_path)

    first = memory.store(
        content="Je préfère le volume à 35 %.",
        category="preference",
        key="audio.volume.default",
        tags=["audio", "volume"],
    )
    second = memory.store(
        content="Finalement, je préfère le volume à 45 %.",
        category="preference",
        key="preferred.volume",
        tags=["audio", "volume"],
    )

    assert second.id == first.id
    records = memory.list(category="preference")
    assert len(records) == 1
    assert records[0].key == "audio.volume.default"
    assert "45 %" in records[0].content


def test_memory_semantic_key_reuses_unique_existing_concept(tmp_path):
    memory = _memory(tmp_path)

    first = memory.store(
        content="Mon casque préféré est le Creative Live! A3.",
        category="preference",
        key="audio.output.headset",
        tags=["audio", "casque"],
    )
    second = memory.store(
        content="Finalement mon casque préféré est le SIDERON Headset X.",
        category="preference",
        key="device.headset.preferred",
        tags=["casque"],
    )

    assert second.id == first.id
    assert len(memory.list(category="preference")) == 1
    assert memory.list(category="preference")[0].key == "audio.output.headset"


def test_memory_does_not_merge_distinct_audio_preferences(tmp_path):
    memory = _memory(tmp_path)

    volume = memory.store(
        content="Je préfère le volume à 35 %.",
        category="preference",
        key="audio.volume.default",
        tags=["audio", "volume"],
    )
    headset = memory.store(
        content="Mon casque préféré est le Creative Live! A3.",
        category="preference",
        key="audio.output.headset",
        tags=["audio", "casque"],
    )

    assert volume.id != headset.id
    assert len(memory.list(category="preference")) == 2
