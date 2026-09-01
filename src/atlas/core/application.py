import asyncio
import time

from dotenv import load_dotenv

from atlas.core.config import ConfigManager
from atlas.core.event_bus import EventBus
from atlas.core.logger import setup_logger
from atlas.core.state import SideronState

from atlas.security.permissions import PermissionMode
from atlas.security.policy import PermissionEngine

from atlas.skills.registry import SkillRegistry
from atlas.skills.manager import SkillManager

from atlas.service import (
    SideronServiceClient,
)

from atlas.skills.catalog import (
    register_default_skills,
)

from atlas.storage import SideronStorage
from atlas.memory import MemoryManager
from atlas.automation import AutomationManager
from atlas.system_events import SystemEventManager
from atlas.system_events.provider import SystemEventSnapshotProvider
from atlas.proactivity import ProactivityManager
from atlas.vision import VisionPolicy
from atlas.vision.analyzer import VisionAnalyzer
from atlas.skills.vision import AnalyzeActiveWindowSkill

from atlas.context.manager import ContextManager
from atlas.core.lifecycle import LifecycleManager
from atlas.audio.manager import AudioManager
from atlas.audio.mode import ListeningMode
from atlas.ai.realtime import RealtimeManager

from atlas.skills.audio.set_listening_mode import (
    SetListeningModeSkill,
)
from atlas.ai.tool_router import RealtimeToolRouter

from atlas.ipc import SideronTelemetryPublisher, SideronUiBridge


class SideronApplication:

    def __init__(
        self,
    ):

        self.logger = setup_logger()

        self.config = ConfigManager()

        self.events = EventBus()

        self.state = SideronState()

        self.permissions = (
            PermissionEngine()
        )

        self.skills = (
            SkillRegistry()
        )

        self.skill_manager = None
        self.storage = None
        self.memory = None
        self.automation = None
        self.system_events = None
        self.proactivity = None
        self.vision_analyzer = None
        self.vision_policy = None

        self.service_client = (
            SideronServiceClient(
                logger=self.logger,
            )
        )

        self.context = ContextManager(
            event_bus=self.events,
            logger=self.logger,
        )

        self.lifecycle = LifecycleManager(
            logger=self.logger,
        )

        self.audio = AudioManager(
            event_bus=self.events,
            logger=self.logger,
        )

        self.realtime = RealtimeManager(
            logger=self.logger,
            event_bus=self.events,
            audio_output=self.audio.output,
        )

        self.ui_bridge = SideronUiBridge(
            event_bus=self.events,
            logger=self.logger,
            state_provider=(
                lambda: self.state
            ),
        )

        self.telemetry = SideronTelemetryPublisher(
            ui_bridge=self.ui_bridge,
            logger=self.logger,
            storage_root_provider=(
                lambda: self.storage.get_root()
            ),
        )

    async def initialize(
        self,
    ) -> None:

        self.logger.info(
            "Initialisation d'Sideron V2..."
        )

        load_dotenv()

        self.config.load()

        self.logger.info(
            "Configuration chargée."
        )

        storage_root = self.config.get(
            "storage.root",
            r"C:\SIDERON",
        )

        self.storage = SideronStorage(
            storage_root
        )

        self.storage.initialize()

        self.logger.info(
            "Zone Sideron initialisée : %s",
            self.storage.get_root(),
        )

        memory_database = self.storage.workspace_path(
            "Memory/sideron-memory.db"
        )

        self.memory = MemoryManager(
            memory_database
        )
        self.memory.initialize()

        self.logger.info(
            "Mémoire persistante SIDERON initialisée : %s",
            self.memory.database_path,
        )

        automation_database = self.storage.workspace_path(
            "System/sideron-automation.db"
        )

        self.automation = AutomationManager(
            automation_database,
            event_bus=self.events,
            logger=self.logger,
        )
        self.automation.initialize()

        self.logger.info(
            "Scheduler persistant SIDERON initialisé : %s",
            self.automation.database_path,
        )

        system_event_provider = SystemEventSnapshotProvider(
            storage_root=self.storage.get_root(),
            audio_devices=self.audio.devices,
        )
        self.system_events = SystemEventManager(
            provider=system_event_provider,
            event_bus=self.events,
            logger=self.logger,
            disk_low_threshold_percent=self.config.get(
                "system.events.disk_low_threshold_percent",
                10.0,
            ),
        )

        self.proactivity = ProactivityManager(
            event_bus=self.events,
            logger=self.logger,
            level=self.config.get(
                "proactivity.level",
                "normal",
            ),
            cooldown_seconds=self.config.get(
                "proactivity.cooldown_seconds",
                120.0,
            ),
        )

        self.logger.info(
            "Proactivité locale SIDERON initialisée : niveau=%s",
            self.proactivity.level,
        )

        self.vision_policy = VisionPolicy()
        self.vision_analyzer = VisionAnalyzer(
            model=self.config.get(
                "openai.vision.model",
                "gpt-5.6-luna",
            ),
            logger=self.logger,
        )

        self.logger.info(
            "Vision SIDERON préparée : modèle=%s",
            self.vision_analyzer.model,
        )

        self.ui_bridge.start()
        self.telemetry.start()

        self.events.subscribe(
            "audio.level",
            self._on_audio_level,
        )

        self.events.subscribe(
            "audio.speech_started",
            self._on_speech_started,
        )

        self.events.subscribe(
            "audio.speech_ended",
            self._on_speech_ended,
        )

        self.events.subscribe(
            "audio.wake_word_detected",
            self._on_wake_word_detected,
        )

        self.events.subscribe(
            "audio.utterance_ready",
            self._on_utterance_ready,
        )

        self.events.subscribe(
            "ai.realtime.connected",
            self._on_realtime_connected,
        )

        self.events.subscribe(
            "ai.realtime.disconnected",
            self._on_realtime_disconnected,
        )

        self.events.subscribe(
            "ai.speech_started",
            self._on_ai_speech_started,
        )

        self.events.subscribe(
            "ai.speech_ended",
            self._on_ai_speech_ended,
        )

        self.events.subscribe(
            "audio.voice_session_closed",
            self._on_voice_session_closed,
        )

        self.events.subscribe(
            "audio.listening_mode_changed",
            self._on_listening_mode_changed,
        )

        self.events.subscribe(
            "context.active_window_changed",
            self._on_active_window_changed,
        )

        self.events.subscribe(
            "automation.reminder_due",
            self._on_automation_reminder_due,
        )

        self.events.subscribe(
            "system.event",
            self._on_system_event,
        )

        self.events.subscribe(
            "proactivity.suggestion",
            self._on_proactivity_suggestion,
        )

        self.events.subscribe(
            "ui.native.command",
            self._on_native_ui_command,
        )

        permission_mode_value = (
            self.config.get(
                "security.permission_mode",
                "normal",
            )
        )

        try:

            permission_mode = PermissionMode(
                permission_mode_value
            )

        except ValueError:

            self.logger.warning(
                "Mode de permission '%s' invalide. "
                "Utilisation du mode normal.",
                permission_mode_value,
            )

            permission_mode = (
                PermissionMode.NORMAL
            )

        self.state.mode = (
            permission_mode.value
        )

        register_default_skills(
            registry=self.skills,
            storage=self.storage,
            service_client=self.service_client,
            event_bus=self.events,
            memory=self.memory,
            automation=self.automation,
        )

        self.skills.register(
            SetListeningModeSkill(
                audio_manager=self.audio,
                config=self.config,
            )
        )

        self.skills.register(
            AnalyzeActiveWindowSkill(
                storage=self.storage,
                analyzer=self.vision_analyzer,
                policy=self.vision_policy,
                privacy_mode_provider=(
                    lambda: bool(
                        self.config.get(
                            "privacy.enabled",
                            False,
                        )
                    )
                ),
                logger=self.logger,
            )
        )

        self.logger.info(
            "%d Skill(s) enregistré(s).",
            len(
                self.skills.list_skills()
            ),
        )

        self.skill_manager = SkillManager(
            registry=self.skills,
            permission_engine=self.permissions,
            event_bus=self.events,
            permission_mode=permission_mode,
            logger=self.logger,
        )

        self._send_permission_state()

        self.tool_router = RealtimeToolRouter(
            registry=self.skills,
            skill_manager=self.skill_manager,
            logger=self.logger,
        )

        self.realtime.set_tool_router(
            self.tool_router
        )

        await self.lifecycle.start()

        self.lifecycle.create_task(
            "automation.scheduler",
            self.automation.run(),
        )

        self.lifecycle.create_task(
            "system.events",
            self.system_events.run(
                interval=self.config.get(
                    "system.events.poll_interval_seconds",
                    5.0,
                )
            ),
        )

        self.lifecycle.create_task(
            "context.monitor",
            self.context.run(
                interval=1.0
            ),
        )

        audio_enabled = self.config.get(
            "audio.enabled",
            False,
        )

        if audio_enabled:

            event_loop = (
                asyncio.get_running_loop()
            )

            self.audio.set_event_loop(
                event_loop
            )

            self.audio.output.set_event_loop(
                event_loop
            )

            self.audio.initialize(
                self.config
            )

            self.lifecycle.create_task(
                "audio.output",
                self.audio.output.run(),
            )

            if self.audio.pipeline is not None:

                self.state.voice_session_active = (
                    self.audio.pipeline.voice_session_active
                )

                self.state.listening = (
                    self.audio.pipeline.voice_session_active
                )

                self._send_listening_state()

                self.lifecycle.create_task(
                    "audio.pipeline",
                    self.audio.pipeline.run(),
                )

            if self.audio.microphone is not None:

                self.lifecycle.create_task(
                    "audio.microphone",
                    self.audio.microphone.run(),
                )

                self.state.microphone_active = (
                    True
                )

        realtime_enabled = self.config.get(
            "openai.realtime.enabled",
            False,
        )

        if realtime_enabled:

            self.realtime.initialize(
                self.config
            )

            self.lifecycle.create_task(
                "ai.realtime",
                self.realtime.run(),
            )

            if self.audio.pipeline is not None:

                self.lifecycle.create_task(
                    "ai.realtime.audio_sender",
                    self.realtime.send_audio(
                        self.audio.pipeline.realtime_queue
                    ),
                )

        self.state.running = True
        self.state.status = "ready"

        self.events.publish(
            "atlas.ready",
            self.state,
        )

        self.logger.info(
            "Sideron V2 prêt."
        )

    async def shutdown(
        self,
    ) -> None:

        self.logger.info(
            "Arrêt d'Sideron..."
        )

        self.state.status = (
            "stopping"
        )

        self.events.publish(
            "atlas.stopping",
            {
                "status": "stopping",
            },
        )

        self.telemetry.stop()
        self.ui_bridge.stop()

        await self.lifecycle.stop()

        self.state.running = False

        self.logger.info(
            "Sideron arrêté."
        )

    def _send_listening_state(
        self,
    ) -> None:

        pipeline = self.audio.pipeline

        if pipeline is None:
            mode = None
            voice_session_active = False
        else:
            mode = pipeline.listening_mode.value
            voice_session_active = (
                pipeline.voice_session_active
            )

        self.ui_bridge.send_event(
            "audio.listening_mode_state",
            {
                "mode": mode,
                "voice_session_active": (
                    voice_session_active
                ),
                "wake_word": "SIDERON",
            },
        )

    def _send_permission_state(
        self,
    ) -> None:

        mode = self.state.mode or "normal"

        self.ui_bridge.send_event(
            "security.permission_state",
            {
                "mode": mode,
            },
        )

    def _send_permission_error(
        self,
        reason: str,
    ) -> None:

        self.ui_bridge.send_event(
            "security.permission_error",
            {
                "reason": reason,
                "mode": self.state.mode,
            },
        )

    def _on_automation_reminder_due(
        self,
        payload=None,
    ) -> None:

        if not isinstance(payload, dict):
            return

        self.ui_bridge.send_event(
            "automation.reminder_due",
            payload,
        )

    def _on_native_ui_command(
        self,
        payload=None,
    ) -> None:

        if not isinstance(
            payload,
            dict,
        ):
            return

        name = payload.get(
            "name"
        )

        command_payload = (
            payload.get(
                "payload"
            )
            or {}
        )

        if name == "audio.get_devices":
            try:
                devices = self.audio.devices
                choices = devices.device_choices()
                current_input = self.audio.microphone
                self.ui_bridge.send_event("audio.input_devices", {
                    "devices": choices["inputs"],
                    "selected": self.config.get("audio.input_device", None),
                    "active_index": current_input.device_index if current_input else None,
                    "warning": getattr(self.audio, "input_warning", ""),
                })
                self.ui_bridge.send_event("audio.output_devices", {
                    "devices": choices["outputs"],
                    "selected": self.config.get("audio.output_device", None),
                    "active_index": (
                        self.audio.output.device_index
                        if self.audio.output._running
                        else None
                    ),
                    "warning": getattr(self.audio, "output_warning", ""),
                })
            except Exception as exc:
                self.logger.exception("Audio device inventory failed")
                self.ui_bridge.send_event(
                    "audio.device_inventory_error",
                    {"reason": str(exc)},
                )
            return

        if name in ("audio.get_output_devices", "audio.set_output_device"):
            error = ""
            try:
                if name == "audio.set_output_device":
                    self.config.load()
                    selection = command_payload.get("device") or None
                    device = self.audio.devices.resolve_output(selection)
                    if device is None:
                        raise RuntimeError("Aucune sortie audio disponible.")
                    previous = self.audio.output.device_index
                    self.audio.output.switch_device(device.index)
                    old_value = self.config.get("audio.output_device", None)
                    try:
                        self.config.set("audio.output_device", selection)
                        self.config.save()
                    except Exception:
                        self.config.set("audio.output_device", old_value)
                        self.audio.output.switch_device(previous)
                        raise
                    self.audio.output_selection = selection
                    self.audio.output_warning = ""
            except Exception as exc:
                self.logger.exception("Audio output selection failed")
                error = str(exc)
            try:
                self.logger.debug("Début de l'inventaire des sorties audio.")
                output_choices = self.audio.devices.output_choices()
                sent = self.ui_bridge.send_event("audio.output_devices", {
                    "devices": output_choices,
                    "selected": self.config.get("audio.output_device", None),
                    "active_index": (
                        self.audio.output.device_index
                        if getattr(self.audio.output, "_running", False)
                        else None
                    ),
                    "warning": error or getattr(self.audio, "output_warning", ""),
                })
                self.logger.debug(
                    "Inventaire des sorties audio terminé : %d périphérique(s), envoyé=%s.",
                    len(output_choices),
                    sent,
                )
            except Exception as exc:
                self.logger.exception("Impossible d'envoyer l'inventaire des sorties audio")
                error = error or str(exc)
            if error:
                self.ui_bridge.send_event("audio.output_device_error", {"reason": error})
            return

        if name in ("audio.get_input_devices", "audio.set_input_device"):
            try:
                if name == "audio.set_input_device":
                    # The UI may have changed the update channel since Core started.
                    self.config.load()
                    selection = command_payload.get("device") or None
                    device = self.audio.devices.resolve_input(selection)
                    if device is None or self.audio.microphone is None:
                        raise RuntimeError("Aucun microphone actif. Branchez un micro et redémarrez le Core.")
                    previous = self.audio.microphone.device_index
                    self.audio.microphone.switch_device(device.index)
                    old_value = self.config.get("audio.input_device", None)
                    try:
                        self.config.set("audio.input_device", selection)
                        self.config.save()
                    except Exception:
                        self.config.set("audio.input_device", old_value)
                        self.audio.microphone.switch_device(previous)
                        raise
                    self.audio.input_selection = selection
                    self.audio.input_warning = ""
                    if self.audio.pipeline is not None:
                        self.audio.pipeline._reset_capture_state()
                current = self.audio.microphone
                self.ui_bridge.send_event("audio.input_devices", {
                    "devices": self.audio.devices.input_choices(),
                    "selected": self.config.get("audio.input_device", None),
                    "active_index": current.device_index if current else None,
                    "warning": getattr(self.audio, "input_warning", ""),
                })
            except Exception as exc:
                self.logger.exception("Microphone selection failed")
                if name == "audio.set_input_device":
                    try:
                        current = self.audio.microphone
                        self.ui_bridge.send_event("audio.input_devices", {
                            "devices": self.audio.devices.input_choices(),
                            "selected": self.config.get("audio.input_device", None),
                            "active_index": current.device_index if current else None,
                            "warning": str(exc),
                        })
                    except Exception:
                        self.logger.exception("Cannot refresh microphone choices")
                self.ui_bridge.send_event("audio.input_device_error", {"reason": str(exc)})
            return

        if name == "audio.get_listening_mode":

            self._send_listening_state()

            return

        if name == "audio.set_listening_mode":

            requested_mode = command_payload.get(
                "mode"
            )

            try:
                mode = self.audio.set_listening_mode(
                    requested_mode
                )
            except (
                TypeError,
                ValueError,
                RuntimeError,
            ) as exc:
                self.ui_bridge.send_event(
                    "audio.listening_mode_error",
                    {
                        "reason": str(
                            exc
                        ),
                    },
                )
                return

            self.config.set(
                "audio.listening_mode",
                mode.value,
            )

            self.config.set(
                "audio.continuous_listening",
                mode == ListeningMode.CONTINUOUS,
            )

            self.config.save()
            self._send_listening_state()

            return

        if name in ("memory.list", "memory.search", "memory.delete"):
            if self.memory is None:
                self.ui_bridge.send_event(
                    "memory.error",
                    {"reason": "La mémoire SIDERON n'est pas initialisée."},
                )
                return

            try:
                raw_category = command_payload.get("category")
                category = (
                    raw_category.strip()
                    if isinstance(raw_category, str) and raw_category.strip()
                    else None
                )

                if name == "memory.delete":
                    memory_id = command_payload.get("id")
                    if isinstance(memory_id, bool):
                        raise ValueError("Identifiant mémoire invalide.")
                    try:
                        memory_id = int(memory_id)
                    except (TypeError, ValueError) as exc:
                        raise ValueError("Identifiant mémoire invalide.") from exc

                    deleted = self.memory.delete(memory_id)
                    self.ui_bridge.send_event(
                        "memory.deleted",
                        {
                            "id": memory_id,
                            "deleted": deleted,
                        },
                    )
                    return

                if name == "memory.search":
                    query = str(command_payload.get("query") or "").strip()
                    if query:
                        records = self.memory.search(
                            query,
                            category=category,
                            limit=100,
                        )
                    else:
                        records = self.memory.list(
                            category=category,
                            limit=200,
                        )
                else:
                    records = self.memory.list(
                        category=category,
                        limit=200,
                    )

                self.ui_bridge.send_event(
                    "memory.items",
                    {
                        "items": [
                            record.to_dict()
                            for record in records
                        ],
                        "query": (
                            str(command_payload.get("query") or "").strip()
                            if name == "memory.search"
                            else ""
                        ),
                        "category": category or "",
                    },
                )
            except Exception as exc:
                self.logger.exception(
                    "Impossible de traiter la commande mémoire de l'UI"
                )
                self.ui_bridge.send_event(
                    "memory.error",
                    {"reason": str(exc)},
                )
            return

        if name == "security.get_permission_state":

            self._send_permission_state()

            return

        if name != "security.set_permission_mode":

            return

        if not isinstance(
            command_payload,
            dict,
        ):

            self._send_permission_error(
                "Paramètres de permissions invalides."
            )

            return

        requested_value = command_payload.get(
            "mode"
        )

        try:

            requested_mode = PermissionMode(
                requested_value
            )

        except (
            TypeError,
            ValueError,
        ):

            self.logger.warning(
                "Mode de permission demandé par l'UI invalide : %s",
                requested_value,
            )

            self._send_permission_error(
                "Mode de permissions invalide."
            )

            return

        elevated_mode = requested_mode in (
            PermissionMode.ADMINISTRATOR,
            PermissionMode.JARVIS,
        )

        confirmed = bool(
            command_payload.get(
                "confirmed",
                False,
            )
        )

        if (
            elevated_mode
            and not confirmed
        ):

            self.logger.warning(
                "Élévation de permissions refusée : confirmation absente."
            )

            self._send_permission_error(
                "Une confirmation explicite est requise pour ce mode."
            )

            return

        if self.skill_manager is None:

            self._send_permission_error(
                "Le gestionnaire de Skills n'est pas encore prêt."
            )

            return

        self.skill_manager.permission_mode = (
            requested_mode
        )

        self.state.mode = (
            requested_mode.value
        )

        self.config.set(
            "security.permission_mode",
            requested_mode.value,
        )

        self.config.save()

        self.logger.info(
            "Mode de permissions Sideron modifié depuis l'UI : %s",
            requested_mode.value,
        )

        self.ui_bridge.send_event(
            "security.permission_mode_changed",
            {
                "mode":
                    requested_mode.value,
            },
        )

    def _on_proactivity_suggestion(
        self,
        payload=None,
    ) -> None:

        if not isinstance(payload, dict):
            return

        self.ui_bridge.send_event(
            "proactivity.suggestion",
            payload,
        )

    def _on_system_event(
        self,
        payload,
    ) -> None:

        if not isinstance(payload, dict):
            return

        event_type = str(payload.get("type") or "system.event")
        self.logger.info(
            "Événement système : %s | %s",
            event_type,
            {key: value for key, value in payload.items() if key != "type"},
        )

        self.ui_bridge.send_event(
            "system.event",
            payload,
        )

    def _on_active_window_changed(
        self,
        payload,
    ) -> None:

        self.logger.debug(
            "Fenêtre active : %s → %s (%s)",
            payload.get(
                "previous"
            ),
            payload.get(
                "current"
            ),
            payload.get(
                "process"
            ),
        )

    def _on_audio_level(
        self,
        payload,
    ) -> None:

        self.state.audio_level_db = (
            payload.get(
                "level_db",
                -100.0,
            )
        )

    def _on_speech_started(
        self,
        payload=None,
    ) -> None:

        self.state.speech_active = (
            True
        )

        self.logger.debug(
            "Speech started : speaking=%s | barge_in=%s",
            self.state.speaking,
            self.config.get(
                "audio.barge_in.enabled",
                False,
            ),
        )

        if not self.state.speaking:
            return

        if not self.config.get(
            "audio.barge_in.enabled",
            True,
        ):
            return

        self.logger.debug(
            "Parole détectée pendant la réponse : "
            "déclenchement du barge-in."
        )

        self.lifecycle.create_task(
            f"ai.interrupt.{time.monotonic_ns()}",
            self.realtime.interrupt(),
        )

    def _on_speech_ended(
        self,
        payload=None,
    ) -> None:

        self.state.speech_active = (
            False
        )

    def _on_wake_word_detected(
        self,
        payload=None,
    ) -> None:

        self.state.wake_word_detected = (
            True
        )

        self.state.voice_session_active = (
            True
        )

        self.state.listening = True
        self._send_listening_state()

        self.logger.info(
            "Session vocale Sideron activée."
        )

    def _on_voice_session_closed(
        self,
        payload=None,
    ) -> None:

        self.state.wake_word_detected = (
            False
        )

        self.state.voice_session_active = (
            False
        )

        self.state.listening = False
        self._send_listening_state()

        self.logger.info(
            "Session vocale Sideron fermée."
        )

    def _on_listening_mode_changed(
        self,
        payload=None,
    ) -> None:

        pipeline = self.audio.pipeline

        if pipeline is None:
            return

        self.state.voice_session_active = (
            pipeline.voice_session_active
        )

        self.state.listening = (
            pipeline.voice_session_active
        )

        self._send_listening_state()

    def _on_utterance_ready(
        self,
        utterance,
    ) -> None:

        self.logger.debug(
            "Phrase audio capturée : %.2f s",
            utterance.duration_seconds,
        )

    def _on_realtime_connected(
        self,
        payload=None,
    ) -> None:

        self.state.openai_connected = (
            True
        )

    def _on_realtime_disconnected(
        self,
        payload=None,
    ) -> None:

        self.state.openai_connected = (
            False
        )

    def _on_ai_speech_started(
        self,
        payload=None,
    ) -> None:

        self.state.speaking = (
            True
        )

    def _on_ai_speech_ended(
        self,
        payload=None,
    ) -> None:

        self.state.speaking = (
            False
        )

        pipeline = self.audio.pipeline

        if pipeline is None:
            return

        if (
            pipeline.listening_mode
            != ListeningMode.WAKE_WORD
        ):
            return

        if not self.config.get(
            "audio.wake_word.auto_close_after_response",
            True,
        ):
            return

        pipeline.close_voice_session()
