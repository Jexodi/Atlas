import asyncio
import base64
import json

import numpy as np

from openai import AsyncOpenAI
from atlas.ai.access import create_client


MAX_TOOL_OUTPUT_CHARS = 24000
MAX_TOOL_LIST_ITEMS = 20
MAX_TOOL_DICT_ITEMS = 40
MAX_TOOL_STRING_CHARS = 2500
MAX_TOOL_COMPACT_DEPTH = 5


class RealtimeManager:

    def __init__(
        self,
        logger,
        event_bus,
        audio_output,
    ) -> None:

        self.logger = logger
        self.event_bus = event_bus
        self.audio_output = audio_output
        self.tool_router = None

        self._response_audio_started = False

        self._current_audio_item_id: (
            str | None
        ) = None

        self._interrupted_item_ids: set[str] = set()

        self._response_active = False

        # Indique si la réponse Realtime courante a réellement
        # produit de l'audio. Cela permet de détecter une réponse
        # "silencieuse" et de demander une unique tentative de reprise.
        self._current_response_had_audio = False

        # Une seule relance automatique est autorisée afin d'éviter
        # toute boucle si le serveur renvoie plusieurs réponses vides.
        self._silent_response_retry_count = 0

        self.client: AsyncOpenAI | None = None
        self.connection = None

        self.barge_in_enabled = False
        self._discarding_input = False

        self._response_idle = asyncio.Event()
        self._response_idle.set()

        self._response_create_lock = asyncio.Lock()
        self._response_create_pending = False

        self._input_audio_samples = 0

        self._interrupt_lock = asyncio.Lock()
        self._interrupting = False

        self.model = "gpt-realtime-2"

        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def initialize(
        self,
        config,
    ) -> None:

        self.model = config.get(
            "openai.realtime.model",
            "gpt-realtime-2",
        )

        self.barge_in_enabled = config.get(
            "audio.barge_in.enabled",
            False,
        )

        self.client = create_client()

    async def run(self) -> None:

        if self.client is None:
            raise RuntimeError(
                "RealtimeManager non initialisé."
            )

        self.logger.info(
            "Connexion OpenAI Realtime..."
        )

        try:

            async with self.client.realtime.connect(
                model=self.model,
            ) as connection:

                self.connection = connection
                self._connected = True

                await self._configure_session()

                self.event_bus.publish(
                    "ai.realtime.connected"
                )

                self.logger.info(
                    "Connexion OpenAI Realtime établie."
                )

                async for event in connection:

                    await self._handle_event(
                        event
                    )

        except asyncio.CancelledError:

            self.logger.info(
                "Connexion OpenAI Realtime arrêtée."
            )

            raise

        except Exception:

            self.logger.exception(
                "Erreur OpenAI Realtime."
            )

        finally:

            self.connection = None
            self._connected = False

            self.event_bus.publish(
                "ai.realtime.disconnected"
            )

    async def _configure_session(
        self,
    ) -> None:

        if self.connection is None:
            return

        tools = []

        if self.tool_router is not None:

            tools = (
                self.tool_router.build_tools()
            )

        self.logger.info(
            "%d outil(s) exposé(s) à Realtime.",
            len(tools),
        )

        await self.connection.session.update(
            session={
                "type": "realtime",

                "output_modalities": [
                    "audio"
                ],

                "instructions": (
                    "Tu es Atlas, un assistant personnel "
                    "vocal pour Windows. "
                    "Réponds exclusivement en français. "
                    "Sois calme, précis, concis et "
                    "légèrement formel. "

                    "Lorsque l'utilisateur demande une action "
                    "disponible via un outil, utilise cet outil. "

                    "Si l'utilisateur demande le mode vocal, le mode "
                    "Discord ou une écoute uniquement après le mot Atlas, "
                    "utilise audio.set_listening_mode avec mode='wake_word'. "
                    "S'il demande le mode normal ou l'écoute continue, "
                    "utilise audio.set_listening_mode avec mode='continuous'. "

                    "Si le résultat d'un outil indique "
                    "confirmation_required=true, n'affirme pas "
                    "que l'action a été effectuée. Demande "
                    "explicitement à l'utilisateur s'il souhaite "
                    "confirmer l'action. "

                    "Si une action attend une confirmation et "
                    "que l'utilisateur répond clairement oui, "
                    "confirme, d'accord, vas-y ou donne un accord "
                    "équivalent, utilise atlas_confirm_action. "

                    "Si l'utilisateur refuse, dit non, annule, "
                    "laisse tomber ou exprime un refus équivalent, "
                    "utilise atlas_cancel_action. "

                    "N'utilise jamais atlas_confirm_action sans "
                    "accord explicite de l'utilisateur. "

                    "Après l'exécution d'un outil, réponds toujours "
                    "oralement à l'utilisateur avec le résultat utile, "
                    "même si l'outil a réussi sans commentaire supplémentaire. "

                    "Ne termine jamais silencieusement le traitement d'une "
                    "demande utilisateur. Si aucun outil supplémentaire "
                    "n'est nécessaire, fournis une réponse audio claire et concise. "
                ),

                "tools": tools,
                "tool_choice": "auto",

                "audio": {
                    "input": {
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000,
                        },

                        "turn_detection": None,
                    },

                    "output": {
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000,
                        },
                    },
                },
            }
        )

    async def _handle_event(
        self,
        event,
    ) -> None:

        event_type = event.type

        if event_type == "error":

            self.logger.error(
                "Erreur Realtime : %s",
                event,
            )

            # Une erreur peut arriver entre response.create et
            # response.created. Sans ce garde-fou, Atlas peut rester
            # bloqué en pensant qu'une création de réponse est encore
            # en attente.
            if (
                self._response_create_pending
                and not self._response_active
            ):

                self._response_create_pending = False
                self._response_idle.set()

                self.logger.warning(
                    "État Realtime réinitialisé après une erreur "
                    "pendant la création d'une réponse."
                )

            return

        if event_type == "response.output_audio.delta":

            self._current_response_had_audio = True

            item_id = event.item_id

            if item_id in self._interrupted_item_ids:
                return

            if (
                item_id
                != self._current_audio_item_id
            ):

                self._current_audio_item_id = (
                    item_id
                )

                self.audio_output.start_response(
                    item_id
                )

            if not self._response_audio_started:

                self._response_audio_started = True
                self._response_active = True

                self.event_bus.publish(
                    "ai.speech_started"
                )

            audio_data = base64.b64decode(
                event.delta
            )

            self.audio_output.enqueue(
                audio_data
            )

            return

        if event_type == "response.created":

            self._response_create_pending = False
            self._response_active = True
            self._response_idle.clear()

            self._current_response_had_audio = False

            response_id = getattr(
                event.response,
                "id",
                None,
            )

            self.logger.debug(
                "Réponse Realtime créée : %s",
                response_id,
            )

            return

        if event_type == "response.done":

            self._response_active = False
            self._response_create_pending = False
            self._response_idle.set()

            response_status = getattr(
                event.response,
                "status",
                None,
            )

            response_id = getattr(
                event.response,
                "id",
                None,
            )

            output_items = list(
                getattr(
                    event.response,
                    "output",
                    [],
                )
                or []
            )

            output_types = [
                getattr(
                    item,
                    "type",
                    "unknown",
                )
                for item in output_items
            ]

            self.logger.debug(
                "Réponse Realtime terminée : id=%s | status=%s | "
                "outputs=%s | audio=%s",
                response_id,
                response_status,
                output_types,
                self._current_response_had_audio,
            )

            tool_calls = []

            for item in output_items:

                if getattr(
                    item,
                    "type",
                    None,
                ) == "function_call":

                    tool_calls.append(
                        item
                    )

            if tool_calls:

                # Le prochain response.create sera la réponse qui suit
                # le résultat de l'outil : elle mérite sa propre
                # tentative de reprise si elle reste silencieuse.
                self._silent_response_retry_count = 0

                for tool_call in tool_calls:

                    await self._handle_function_call(
                        tool_call
                    )

                return

            finished_item_id = (
                self._current_audio_item_id
            )

            self.audio_output.mark_response_done()

            # Il arrive qu'une réponse Realtime se termine sans aucun
            # audio ni appel d'outil. Dans ce cas Atlas semblait ignorer
            # l'utilisateur. On effectue une seule relance automatique.
            if not self._current_response_had_audio:

                if (
                    self._silent_response_retry_count
                    < 1
                    and response_status
                    not in {
                        "cancelled",
                        "failed",
                    }
                ):

                    self._silent_response_retry_count += 1

                    self.logger.warning(
                        "Réponse Realtime silencieuse : "
                        "relance automatique (%d/1).",
                        self._silent_response_retry_count,
                    )

                    created = await self._request_response(
                        reason="silent-recovery",
                    )

                    if created:
                        return

                else:

                    self.logger.warning(
                        "Réponse Realtime silencieuse sans relance "
                        "supplémentaire (status=%s).",
                        response_status,
                    )

            else:

                self._silent_response_retry_count = 0

            asyncio.create_task(
                self._finish_response(
                    event,
                    finished_item_id,
                )
            )

            return

    def _encode_audio_chunk(
        self,
        chunk,
    ) -> str:

        samples = np.clip(
            chunk.samples,
            -1.0,
            1.0,
        )

        pcm16 = (
            samples * 32767
        ).astype(
            "<i2"
        )

        return base64.b64encode(
            pcm16.tobytes()
        ).decode(
            "ascii"
        )

    async def send_audio(
        self,
        audio_queue,
    ) -> None:

        self.logger.info(
            "Envoi audio Realtime prêt."
        )

        try:

            while True:

                chunk = await audio_queue.get()

                try:

                    # Fin de l'utterance
                    if chunk is None:

                        if self._discarding_input:

                            self._discarding_input = False

                            if (
                                self.connected
                                and self.connection is not None
                            ):

                                try:

                                    await (
                                        self.connection
                                        .input_audio_buffer
                                        .clear()
                                    )

                                    self._input_audio_samples = 0

                                except Exception:

                                    self.logger.debug(
                                        "Impossible de vider "
                                        "l'audio ignoré.",
                                        exc_info=True,
                                    )

                            continue

                        await self._commit_audio()

                        continue

                    if (
                        not self.connected
                        or self.connection is None
                    ):
                        continue

                    # Si le barge-in est désactivé,
                    # on ignore le micro pendant la réponse.
                    if (
                        not self.barge_in_enabled
                        and (
                            self._response_active
                            or self.audio_output.speaking
                        )
                    ):

                        self._discarding_input = True

                        continue


                    encoded = self._encode_audio_chunk(
                        chunk
                    )

                    await (
                        self.connection
                        .input_audio_buffer
                        .append(
                            audio=encoded
                        )
                    )

                    self._input_audio_samples += len(
                        chunk.samples
                    )

                finally:

                    audio_queue.task_done()

        except asyncio.CancelledError:

            self.logger.info(
                "Envoi audio Realtime arrêté."
            )

            raise

    async def _commit_audio(
        self,
    ) -> None:

        if (
            not self.connected
            or self.connection is None
        ):
            return

        minimum_samples = int(
            0.100 * 24000
        )

        if (
            self._input_audio_samples
            < minimum_samples
        ):

            self.logger.debug(
                "Commit audio ignoré : "
                "%d samples seulement.",
                self._input_audio_samples,
            )

            try:

                await (
                    self.connection
                    .input_audio_buffer
                    .clear()
                )

            except Exception:

                self.logger.debug(
                    "Impossible de vider "
                    "le petit buffer audio.",
                    exc_info=True,
                )

            self._input_audio_samples = 0

            return

        if (
            self._response_active
            or self._response_create_pending
        ):

            self.logger.debug(
                "Commit différé : une réponse "
                "Realtime est encore active."
            )

            try:

                await asyncio.wait_for(
                    self._response_idle.wait(),
                    timeout=2.0,
                )

            except asyncio.TimeoutError:

                self.logger.warning(
                    "Realtime n'est pas redevenu "
                    "disponible à temps."
                )

                return

        self.logger.debug(
            "Fin de phrase envoyée à Realtime "
            "(%d samples).",
            self._input_audio_samples,
        )

        await (
            self.connection
            .input_audio_buffer
            .commit()
        )

        self._input_audio_samples = 0

        # Nouvelle demande utilisateur : nouvelle possibilité
        # de récupération silencieuse.
        self._silent_response_retry_count = 0

        await self._request_response(
            reason="user-audio",
        )

    async def _request_response(
        self,
        reason: str = "unspecified",
    ) -> bool:

        if self.connection is None:
            return False

        async with self._response_create_lock:

            if (
                self._response_active
                or self._response_create_pending
            ):

                self.logger.debug(
                    "response.create ignoré (%s) : "
                    "une réponse est déjà active "
                    "ou en cours de création.",
                    reason,
                )

                return False

            self._response_create_pending = True
            self._response_idle.clear()

            self.logger.debug(
                "Demande response.create (%s).",
                reason,
            )

            try:

                await (
                    self.connection
                    .response
                    .create()
                )

            except Exception:

                self._response_create_pending = False
                self._response_idle.set()

                raise

            return True

    async def _handle_function_call(
        self,
        tool_call,
    ) -> None:

        if self.connection is None:
            return

        if self.tool_router is None:

            self.logger.error(
                "Tool call reçu mais aucun "
                "RealtimeToolRouter n'est configuré."
            )

            return

        tool_name = tool_call.name
        call_id = tool_call.call_id
        arguments = tool_call.arguments

        self.logger.info(
            "Appel outil demandé : %s | call_id=%s",
            tool_name,
            call_id,
        )

        try:

            result = await asyncio.to_thread(
                self.tool_router.execute,
                tool_name,
                arguments,
            )

        except Exception as exc:

            self.logger.exception(
                "Erreur pendant l'exécution "
                "de l'outil '%s'.",
                tool_name,
            )

            result = {
                "success": False,
                "skill": tool_name,
                "message": str(exc),
                "data": None,
                "confirmation_required": False,
                "denied": False,
            }

        await self._send_tool_result(
            call_id=call_id,
            result=result,
        )

    async def _send_tool_result(
        self,
        call_id: str,
        result: dict,
    ) -> None:

        if self.connection is None:
            return

        realtime_result = (
            self._prepare_tool_result_for_realtime(
                result
            )
        )

        output = json.dumps(
            realtime_result,
            ensure_ascii=False,
            default=str,
        )

        self.logger.debug(
            "Retour outil à Realtime (%d caractères) : %s",
            len(output),
            output,
        )

        await (
            self.connection
            .conversation
            .item
            .create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                }
            )
        )

        # La prochaine réponse doit toujours commenter le résultat
        # de l'outil. Elle dispose d'une relance silencieuse dédiée.
        self._silent_response_retry_count = 0

        await self._request_response(
            reason="tool-result",
        )

    def _prepare_tool_result_for_realtime(
        self,
        result: dict,
    ) -> dict:

        full_output = json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

        if len(
            full_output
        ) <= MAX_TOOL_OUTPUT_CHARS:

            return result

        compacted = {
            "success": result.get(
                "success"
            ),
            "skill": result.get(
                "skill"
            ),
            "message": result.get(
                "message"
            ),
            "data": self._compact_tool_value(
                result.get(
                    "data"
                ),
                depth=0,
            ),
            "confirmation_required": result.get(
                "confirmation_required",
                False,
            ),
            "denied": result.get(
                "denied",
                False,
            ),
            "realtime_truncated": True,
            "realtime_note": (
                "Le résultat complet était trop volumineux pour être "
                "envoyé intégralement au modèle vocal. Les compteurs et "
                "un échantillon représentatif ont été conservés."
            ),
        }

        compact_output = json.dumps(
            compacted,
            ensure_ascii=False,
            default=str,
        )

        self.logger.info(
            "Résultat outil compacté pour Realtime : "
            "%d -> %d caractères.",
            len(
                full_output
            ),
            len(
                compact_output
            ),
        )

        return compacted

    def _compact_tool_value(
        self,
        value,
        depth: int,
    ):

        if depth >= MAX_TOOL_COMPACT_DEPTH:

            if isinstance(
                value,
                (dict, list, tuple),
            ):

                return (
                    f"<contenu imbriqué omis : "
                    f"{len(value)} élément(s)>"
                )

            return value

        if isinstance(
            value,
            str,
        ):

            if len(
                value
            ) <= MAX_TOOL_STRING_CHARS:

                return value

            return (
                value[
                    :MAX_TOOL_STRING_CHARS
                ]
                + "… <texte tronqué>"
            )

        if isinstance(
            value,
            dict,
        ):

            result = {}

            items = list(
                value.items()
            )

            for key, item_value in items[
                :MAX_TOOL_DICT_ITEMS
            ]:

                result[
                    str(key)
                ] = self._compact_tool_value(
                    item_value,
                    depth=(
                        depth + 1
                    ),
                )

            if len(
                items
            ) > MAX_TOOL_DICT_ITEMS:

                result[
                    "_omitted_keys"
                ] = (
                    len(items)
                    - MAX_TOOL_DICT_ITEMS
                )

            return result

        if isinstance(
            value,
            (list, tuple),
        ):

            compacted = [
                self._compact_tool_value(
                    item,
                    depth=(
                        depth + 1
                    ),
                )
                for item in value[
                    :MAX_TOOL_LIST_ITEMS
                ]
            ]

            if len(
                value
            ) > MAX_TOOL_LIST_ITEMS:

                compacted.append(
                    {
                        "_omitted_items": (
                            len(value)
                            - MAX_TOOL_LIST_ITEMS
                        ),
                        "_total_items": len(
                            value
                        ),
                    }
                )

            return compacted

        return value

    async def interrupt(
        self,
    ) -> None:

        async with self._interrupt_lock:

            if self._interrupting:
                return

            generation_active = (
                self._response_active
            )

            playback_active = (
                self.audio_output.speaking
            )

            if (
                not generation_active
                and not playback_active
            ):
                return

            self._interrupting = True

            try:

                item_id = (
                    self._current_audio_item_id
                )

                played_ms = (
                    self.audio_output
                    .get_played_duration_ms()
                )

                self.logger.info(
                    "Interruption Atlas "
                    "(item=%s, joué=%d ms, "
                    "generation=%s, lecture=%s).",
                    item_id,
                    played_ms,
                    generation_active,
                    playback_active,
                )

                # Stop local immédiat.
                self.audio_output.clear()

                # Empêche les derniers fragments réseau
                # de refaire parler Atlas.
                if item_id is not None:
                    self._interrupted_item_ids.add(
                        item_id
                    )

                # Annulation serveur uniquement
                # si la génération était encore active.
                if generation_active:

                    try:

                        await (
                            self.connection
                            .response
                            .cancel()
                        )

                    except Exception:

                        self.logger.debug(
                            "La réponse Realtime "
                            "était déjà terminée.",
                            exc_info=True,
                        )

                # Synchronise ce qui a réellement
                # été entendu.
                if (
                    item_id is not None
                    and played_ms > 0
                ):

                    try:

                        await (
                            self.connection
                            .conversation
                            .item
                            .truncate(
                                item_id=item_id,
                                content_index=0,
                                audio_end_ms=played_ms,
                            )
                        )

                        self.logger.debug(
                            "Réponse tronquée à %d ms.",
                            played_ms,
                        )

                    except Exception:

                        self.logger.exception(
                            "Échec de la troncature Realtime."
                        )

                if self._response_audio_started:

                    self._response_audio_started = False

                    self.event_bus.publish(
                        "ai.speech_ended"
                    )

                self._current_audio_item_id = None

            finally:

                self._interrupting = False

    async def _finish_response(
        self,
        event,
        item_id: str | None,
    ) -> None:

        await (
            self.audio_output
            .wait_until_drained()
        )

        if (
            self._current_audio_item_id
            == item_id
        ):

            if self._response_audio_started:

                self._response_audio_started = False

                self.event_bus.publish(
                    "ai.speech_ended"
                )

            self._current_audio_item_id = None

        self.event_bus.publish(
            "ai.response.done",
            event,
        )

    def set_tool_router(
        self,
        tool_router,
    ) -> None:

        self.tool_router = tool_router




