"""Transactional Text Assistant coordinating certified services without new authority."""

import hashlib
import logging
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai_router.enums import ModelCapability
from backend.app.ai_router.schemas import ProviderRequest, RoutingRequest
from backend.app.ai_router.service import AIRouter
from backend.app.core.errors import (
    AIProviderExecutionError,
    AIRoutingDeniedError,
    ConversationConcurrentModificationError,
    ConversationNotFoundError,
    MessageIdempotencyConflictError,
)
from backend.app.identity.context import IdentityContext
from backend.app.identity.models import utc_now
from backend.app.memory.enums import MemoryClass
from backend.app.memory.schemas import MemoryCreateRequest
from backend.app.memory.service import MemoryService
from backend.app.orchestrator.enums import (
    IntentCategory,
    OrchestrationReason,
    OrchestrationState,
)
from backend.app.orchestrator.schemas import IntentMetadata, OrchestrationRequest
from backend.app.orchestrator.service import OrchestratorService
from backend.app.permissions.enums import AuthorizationDecisionType
from backend.app.research.enums import ResearchErrorCode
from backend.app.research.errors import ResearchError
from backend.app.research.schemas import ResearchCitation
from backend.app.security.classification import (
    DataSensitivity,
    classify_text_sensitivity,
    highest_sensitivity,
)
from backend.app.text_assistant.context import build_context, memory_items
from backend.app.text_assistant.enums import (
    AssistantFailureReason,
    AssistantIntent,
    AssistantOutcome,
    MessageRole,
    MessageStatus,
)
from backend.app.text_assistant.intent import ClassifiedIntent, classify_intent
from backend.app.text_assistant.models import Conversation, ConversationMessage
from backend.app.text_assistant.observability import (
    NullTextAssistantObserver,
    TextAssistantMetricEvent,
    TextAssistantObserver,
)
from backend.app.text_assistant.schemas import (
    AssistantRequest,
    AssistantResponse,
    ConversationCreateRequest,
    ConversationMessageResponse,
    ConversationResponse,
)
from backend.app.text_assistant.task_profile import MemoryDependency, profile_chat_task

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _AssistantMaterial:
    content: str
    status: MessageStatus
    outcome: AssistantOutcome
    sensitivity: DataSensitivity
    reason_code: str | None = None
    routing_decision_id: UUID | None = None
    orchestration_id: UUID | None = None
    confirmation_request_id: UUID | None = None
    memory_id: UUID | None = None
    citations: tuple[ResearchCitation, ...] = ()


class TextAssistantService:
    """Conversation interface. Certified domains retain every authority decision."""

    def __init__(
        self,
        session: AsyncSession,
        memory: MemoryService,
        ai_router: AIRouter,
        orchestrator: OrchestratorService,
        *,
        observer: TextAssistantObserver | None = None,
    ) -> None:
        self.session = session
        self.memory = memory
        self.ai_router = ai_router
        self.orchestrator = orchestrator
        self.observer = observer or NullTextAssistantObserver()

    async def create_conversation(
        self, identity: IdentityContext, request: ConversationCreateRequest
    ) -> Conversation:
        now = utc_now()
        conversation = Conversation(
            user_id=identity.user_id,
            device_id=identity.device_id,
            title=request.title,
            version=1,
            next_sequence=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(conversation)
        await self.session.flush()
        logger.info(
            "Conversation created",
            extra={"conversation_id": str(conversation.id), "user_id": str(identity.user_id)},
        )
        return conversation

    async def list_owned(
        self, identity: IdentityContext, *, limit: int, offset: int
    ) -> list[Conversation]:
        statement: Select[tuple[Conversation]] = (
            select(Conversation)
            .where(Conversation.user_id == identity.user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(await self.session.scalars(statement))

    async def get_owned(self, identity: IdentityContext, conversation_id: UUID) -> Conversation:
        conversation = await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == identity.user_id,
            )
        )
        if conversation is None:
            raise ConversationNotFoundError
        return conversation

    async def list_messages(
        self,
        identity: IdentityContext,
        conversation_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[ConversationMessage]:
        await self.get_owned(identity, conversation_id)
        return list(
            await self.session.scalars(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.user_id == identity.user_id,
                )
                .order_by(ConversationMessage.sequence)
                .limit(limit)
                .offset(offset)
            )
        )

    async def submit(
        self,
        identity: IdentityContext,
        conversation_id: UUID,
        request: AssistantRequest,
    ) -> AssistantResponse:
        fingerprint = request.fingerprint(conversation_id)
        existing = await self._idempotent_existing(identity.user_id, request.idempotency_key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise MessageIdempotencyConflictError
            return await self._existing_response(identity, existing)

        conversation = await self.get_owned(identity, conversation_id)
        if conversation.version != request.expected_version:
            raise ConversationConcurrentModificationError
        history = list(
            await self.session.scalars(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation.id,
                    ConversationMessage.user_id == identity.user_id,
                    ConversationMessage.status == MessageStatus.COMPLETED,
                )
                .order_by(ConversationMessage.sequence)
            )
        )
        try:
            sequence = await self._reserve_message_pair(conversation, request.expected_version)
        except ConversationConcurrentModificationError:
            concurrent = await self._idempotent_existing(identity.user_id, request.idempotency_key)
            if concurrent is None:
                raise
            if concurrent.request_fingerprint != fingerprint:
                raise MessageIdempotencyConflictError from None
            return await self._existing_response(identity, concurrent)
        message_sensitivity = classify_text_sensitivity(request.content)
        user_message = ConversationMessage(
            conversation_id=conversation.id,
            user_id=identity.user_id,
            role=MessageRole.USER,
            status=MessageStatus.COMPLETED,
            sequence=sequence,
            content=request.content,
            sensitivity=message_sensitivity,
            idempotency_key=request.idempotency_key,
            request_fingerprint=fingerprint,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(user_message)
                await self.session.flush()
        except IntegrityError:
            existing = await self._idempotent_existing(identity.user_id, request.idempotency_key)
            if existing is None:
                raise ConversationConcurrentModificationError from None
            if existing.request_fingerprint != fingerprint:
                raise MessageIdempotencyConflictError from None
            return await self._existing_response(identity, existing)

        intent = classify_intent(request.content)
        material = await self._dispatch(identity, request, intent, history, message_sensitivity)
        assistant_message = ConversationMessage(
            conversation_id=conversation.id,
            user_id=identity.user_id,
            role=MessageRole.ASSISTANT,
            status=material.status,
            outcome=material.outcome,
            sequence=sequence + 1,
            content=material.content,
            sensitivity=material.sensitivity,
            reply_to_message_id=user_message.id,
            routing_decision_id=material.routing_decision_id,
            orchestration_id=material.orchestration_id,
            confirmation_request_id=material.confirmation_request_id,
            memory_id=material.memory_id,
            reason_code=material.reason_code,
            research_citations=[item.model_dump(mode="json") for item in material.citations],
        )
        now = utc_now()
        self.session.add(assistant_message)
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id, Conversation.user_id == identity.user_id)
            .values(last_message_at=now, updated_at=now)
        )
        await self.session.flush()
        await self.session.refresh(conversation)
        self.observer.emit(
            TextAssistantMetricEvent(
                name="text_assistant.message.completed",
                attributes={
                    "conversation_id": str(conversation.id),
                    "message_id": str(assistant_message.id),
                    "intent": intent.kind.value,
                    "outcome": material.outcome.value,
                },
            )
        )
        logger.info(
            "Text Assistant message completed",
            extra={
                "conversation_id": str(conversation.id),
                "message_id": str(assistant_message.id),
                "user_id": str(identity.user_id),
                "outcome": material.outcome.value,
            },
        )
        return self._response(conversation, user_message, assistant_message)

    async def _dispatch(
        self,
        identity: IdentityContext,
        request: AssistantRequest,
        intent: ClassifiedIntent,
        history: list[ConversationMessage],
        current_sensitivity: DataSensitivity,
    ) -> _AssistantMaterial:
        if intent.kind is AssistantIntent.MEMORY_SAVE:
            return await self._save_memory(identity, intent, current_sensitivity)
        if intent.kind is AssistantIntent.MEMORY_RECALL:
            return await self._recall_memory(identity, intent, request.memory_items_per_category)
        if intent.kind is AssistantIntent.MEMORY_DELETE:
            return await self._delete_memory(identity, request)
        if intent.kind is AssistantIntent.ACTION:
            return await self._coordinate_action(identity, request)
        if intent.kind is AssistantIntent.RESEARCH:
            return await self._research(identity, request, current_sensitivity)
        return await self._chat(identity, request, history, current_sensitivity)

    async def _research(
        self,
        identity: IdentityContext,
        request: AssistantRequest,
        sensitivity: DataSensitivity,
    ) -> _AssistantMaterial:
        try:
            answer = await self.orchestrator.research(
                identity,
                content=request.content,
                sensitivity=sensitivity,
                requested_output_tokens=request.requested_output_tokens,
                confirmation_id=request.research_confirmation_id,
            )
        except ResearchError as exc:
            mapping = {
                ResearchErrorCode.PERMISSION_REQUIRED: (
                    "Necesito permiso para consultar fuentes web.",
                    AssistantOutcome.RESEARCH_PERMISSION_REQUIRED,
                ),
                ResearchErrorCode.CONFIRMATION_REQUIRED: (
                    "Necesito tu confirmación antes de consultar fuentes web.",
                    AssistantOutcome.RESEARCH_CONFIRMATION_REQUIRED,
                ),
                ResearchErrorCode.POLICY_DENIED: (
                    "La política de seguridad no permite investigar esa solicitud en la web.",
                    AssistantOutcome.RESEARCH_POLICY_DENIED,
                ),
                ResearchErrorCode.INSUFFICIENT_EVIDENCE: (
                    "No encontré evidencia suficiente para responder con citas verificables.",
                    AssistantOutcome.RESEARCH_INSUFFICIENT_EVIDENCE,
                ),
                ResearchErrorCode.CITATION_INTEGRITY: (
                    "La evidencia recuperada no superó la validación de integridad.",
                    AssistantOutcome.RESEARCH_INSUFFICIENT_EVIDENCE,
                ),
            }
            message, outcome = mapping.get(
                exc.code,
                (
                    "La investigación web no está disponible de forma segura en este momento.",
                    AssistantOutcome.RESEARCH_UNAVAILABLE,
                ),
            )
            return _AssistantMaterial(
                content=message,
                status=MessageStatus.COMPLETED,
                outcome=outcome,
                sensitivity=sensitivity,
                reason_code=exc.code.value,
                confirmation_request_id=exc.confirmation_id,
            )
        return _AssistantMaterial(
            content=answer.content,
            status=MessageStatus.COMPLETED,
            outcome=AssistantOutcome.RESEARCH_ANSWERED,
            sensitivity=sensitivity,
            routing_decision_id=answer.routing_decision_id,
            citations=answer.citations,
        )

    async def _save_memory(
        self,
        identity: IdentityContext,
        intent: ClassifiedIntent,
        sensitivity: DataSensitivity,
    ) -> _AssistantMaterial:
        if not intent.payload:
            return self._failed(
                "Dime exactamente qué quieres que recuerde.", "MEMORY_CONTENT_REQUIRED"
            )
        result = await self.memory.create_explicit(
            identity,
            MemoryCreateRequest(
                memory_class=MemoryClass.PERSISTENT_PREFERENCE,
                content=intent.payload,
                sensitivity=sensitivity,
            ),
        )
        if result.decision.decision is AuthorizationDecisionType.ALLOW and result.value:
            return _AssistantMaterial(
                content="Lo recordaré.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_SAVED,
                sensitivity=sensitivity,
                memory_id=result.value.id,
            )
        if result.decision.decision is AuthorizationDecisionType.REQUIRE_CONFIRMATION:
            return _AssistantMaterial(
                content="Necesito tu confirmación antes de guardar ese recuerdo.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_CONFIRMATION_REQUIRED,
                sensitivity=sensitivity,
                reason_code="CONFIRMATION_REQUIRED",
                confirmation_request_id=result.decision.confirmation_id,
            )
        return _AssistantMaterial(
            content="No tengo autorización para guardar ese recuerdo.",
            status=MessageStatus.COMPLETED,
            outcome=AssistantOutcome.MEMORY_PERMISSION_REQUIRED,
            sensitivity=sensitivity,
            reason_code="PERMISSION_REQUIRED",
        )

    async def _recall_memory(
        self, identity: IdentityContext, intent: ClassifiedIntent, limit: int
    ) -> _AssistantMaterial:
        result = await self.memory.build_context_pack(identity, per_category_limit=limit)
        if result.value is None:
            return _AssistantMaterial(
                content="No tengo autorización para consultar tus recuerdos.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_PERMISSION_REQUIRED,
                sensitivity=DataSensitivity.PRIVATE,
                reason_code="PERMISSION_REQUIRED",
            )
        items = memory_items(result.value)
        query = (intent.payload or "").casefold()
        matches = [item for item in items if not query or query in item.text.casefold()]
        if not matches:
            return _AssistantMaterial(
                content="No encontré un recuerdo activo sobre eso.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_RECALLED,
                sensitivity=DataSensitivity.PRIVATE,
            )
        selected = matches[:8]
        sensitivity = highest_sensitivity(*(item.sensitivity for item in selected))
        previews = [f"- {item.text[:1000]}" for item in selected]
        return _AssistantMaterial(
            content="Esto es lo que recuerdo:\n" + "\n".join(previews),
            status=MessageStatus.COMPLETED,
            outcome=AssistantOutcome.MEMORY_RECALLED,
            sensitivity=sensitivity,
        )

    async def _delete_memory(
        self, identity: IdentityContext, request: AssistantRequest
    ) -> _AssistantMaterial:
        target = request.memory_target
        if target is None:
            return _AssistantMaterial(
                content="Necesito la referencia exacta del recuerdo que quieres eliminar.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_TARGET_REQUIRED,
                sensitivity=DataSensitivity.PRIVATE,
                reason_code=AssistantFailureReason.MEMORY_TARGET_REQUIRED.value,
            )
        result = await self.memory.delete_owned(
            identity,
            target.memory_id,
            expected_version=target.expected_version,
            confirmation_id=target.confirmation_id,
        )
        if result.decision.decision is AuthorizationDecisionType.REQUIRE_CONFIRMATION:
            return _AssistantMaterial(
                content="Necesito tu confirmación antes de eliminar ese recuerdo.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_CONFIRMATION_REQUIRED,
                sensitivity=DataSensitivity.PRIVATE,
                reason_code="CONFIRMATION_REQUIRED",
                confirmation_request_id=result.decision.confirmation_id,
            )
        if result.decision.decision is not AuthorizationDecisionType.ALLOW:
            return _AssistantMaterial(
                content="No tengo autorización para eliminar ese recuerdo.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_PERMISSION_REQUIRED,
                sensitivity=DataSensitivity.PRIVATE,
                reason_code="PERMISSION_REQUIRED",
            )
        if result.value is None:
            return _AssistantMaterial(
                content="Ese recuerdo no está disponible.",
                status=MessageStatus.COMPLETED,
                outcome=AssistantOutcome.MEMORY_DELETED,
                sensitivity=DataSensitivity.PRIVATE,
                reason_code=AssistantFailureReason.MEMORY_NOT_AVAILABLE.value,
            )
        return _AssistantMaterial(
            content="El recuerdo fue eliminado.",
            status=MessageStatus.COMPLETED,
            outcome=AssistantOutcome.MEMORY_DELETED,
            sensitivity=DataSensitivity.PRIVATE,
            memory_id=result.value.id,
        )

    async def _chat(
        self,
        identity: IdentityContext,
        request: AssistantRequest,
        history: list[ConversationMessage],
        current_sensitivity: DataSensitivity,
    ) -> _AssistantMaterial:
        task_profile = profile_chat_task(
            request.content,
            requested_output_tokens=request.requested_output_tokens,
        )
        pack = None
        memory_was_queried = False
        if (
            request.use_memory_context
            and task_profile.memory_dependency is MemoryDependency.NEEDED
        ):
            memory_result = await self.memory.build_context_pack(
                identity, per_category_limit=request.memory_items_per_category
            )
            pack = memory_result.value
            memory_was_queried = True
        context = build_context(
            history,
            pack,
            current_sensitivity,
            task_profile=task_profile,
        )
        prompt = context.provider_input(request.content)
        estimated_input_tokens = max(1, (len(prompt) + 3) // 4)
        self.observer.emit(
            TextAssistantMetricEvent(
                name="text_assistant.context.selected",
                attributes={
                    "history_messages_available": len(history),
                    "history_messages_included": len(context.history),
                    "history_chars_included": sum(len(item.content) for item in context.history),
                    "memory_context_authorized": request.use_memory_context,
                    "memory_context_queried": memory_was_queried,
                    "memory_items_included": len(context.memory_items),
                    "context_dependency": task_profile.context_dependency.value,
                    "memory_dependency": task_profile.memory_dependency.value,
                    "estimated_input_tokens": estimated_input_tokens,
                },
            )
        )
        routing = RoutingRequest(
            task_type="text_assistant.conversation",
            complexity=task_profile.complexity,
            required_capabilities=frozenset({ModelCapability.TEXT_GENERATION}),
            sensitivity=context.effective_sensitivity,
            context_sensitivities=tuple(item.sensitivity for item in context.memory_items),
            estimated_input_tokens=estimated_input_tokens,
            requested_output_tokens=task_profile.output_token_budget,
        )
        try:
            execution = await self.ai_router.invoke(
                identity,
                routing,
                ProviderRequest(
                    input_text=prompt,
                    output_token_budget=task_profile.output_token_budget,
                ),
            )
        except AIRoutingDeniedError:
            return self._failed(
                "No puedo enviar este contexto a un modelo permitido de forma segura.",
                AssistantFailureReason.AI_ROUTING_DENIED.value,
                context.effective_sensitivity,
            )
        except AIProviderExecutionError:
            return self._failed(
                "No pude generar una respuesta de forma segura en este momento.",
                AssistantFailureReason.PROVIDER_FAILURE.value,
                context.effective_sensitivity,
            )
        output = execution.response.output_text.strip()
        if not output or len(output) > 100_000:
            return self._failed(
                "La respuesta del modelo no fue válida.",
                AssistantFailureReason.PROVIDER_FAILURE.value,
                context.effective_sensitivity,
            )
        return _AssistantMaterial(
            content=output,
            status=MessageStatus.COMPLETED,
            outcome=AssistantOutcome.ANSWERED,
            sensitivity=context.effective_sensitivity,
            routing_decision_id=execution.routing_decision.id,
        )

    async def _coordinate_action(
        self, identity: IdentityContext, request: AssistantRequest
    ) -> _AssistantMaterial:
        normalized = request.content.casefold()
        destructive = any(
            item in normalized
            for item in (
                "delete",
                "elimina",
                "buy",
                "sell",
                "transfer",
                "withdraw",
                "compra",
                "vende",
            )
        )
        orchestration = await self.orchestrator.create(
            identity,
            OrchestrationRequest(
                intent=IntentMetadata(
                    category=(IntentCategory.DESTRUCTIVE if destructive else IntentCategory.ACTION),
                    label="text_assistant.action",
                ),
                input_text=request.content,
                idempotency_key="text:"
                + hashlib.sha256(request.idempotency_key.encode()).hexdigest(),
                use_memory_context=request.use_memory_context,
                memory_items_per_category=request.memory_items_per_category,
                requested_output_tokens=request.requested_output_tokens,
            ),
        )
        workflow = orchestration.workflow
        if workflow.state is OrchestrationState.WAITING_PERMISSION:
            return self._action_material(
                "Necesito permiso antes de poder preparar esa acción.",
                AssistantOutcome.ACTION_WAITING_PERMISSION,
                workflow.id,
                workflow.failure_reason,
            )
        if workflow.state is OrchestrationState.WAITING_CONFIRMATION:
            return self._action_material(
                "Necesito tu confirmación antes de continuar con esa acción.",
                AssistantOutcome.ACTION_WAITING_CONFIRMATION,
                workflow.id,
                OrchestrationReason.CONFIRMATION_REQUIRED.value,
                confirmation_request_id=workflow.confirmation_request_id,
            )
        if workflow.state is OrchestrationState.READY_FOR_EXECUTION:
            return self._action_material(
                "La acción quedó autorizada y preparada, pero todavía no existe un ejecutor; "
                "no se realizó.",
                AssistantOutcome.ACTION_READY_FOR_FUTURE_EXECUTION,
                workflow.id,
                AssistantFailureReason.EXECUTOR_UNAVAILABLE.value,
            )
        if workflow.failure_reason == OrchestrationReason.FINANCIAL_EXECUTION_PROHIBITED.value:
            return self._action_material(
                "No puedo ejecutar operaciones financieras.",
                AssistantOutcome.ACTION_DENIED,
                workflow.id,
                workflow.failure_reason,
            )
        if workflow.state in {OrchestrationState.DENIED, OrchestrationState.FAILED}:
            return self._action_material(
                "No pude autorizar ni ejecutar esa solicitud.",
                AssistantOutcome.ACTION_DENIED,
                workflow.id,
                workflow.failure_reason or AssistantFailureReason.ORCHESTRATION_DENIED.value,
            )
        return self._action_material(
            "La solicitud no produjo ninguna acción externa.",
            AssistantOutcome.ACTION_UNSUPPORTED,
            workflow.id,
            workflow.failure_reason,
        )

    async def _reserve_message_pair(self, conversation: Conversation, expected_version: int) -> int:
        sequence = conversation.next_sequence
        now = utc_now()
        result = await self.session.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation.id,
                Conversation.user_id == conversation.user_id,
                Conversation.version == expected_version,
            )
            .values(
                version=expected_version + 1,
                next_sequence=sequence + 2,
                updated_at=now,
            )
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise ConversationConcurrentModificationError
        await self.session.refresh(conversation)
        return sequence

    async def _idempotent_existing(
        self, user_id: UUID, idempotency_key: str
    ) -> ConversationMessage | None:
        return cast(
            ConversationMessage | None,
            await self.session.scalar(
                select(ConversationMessage).where(
                    ConversationMessage.user_id == user_id,
                    ConversationMessage.role == MessageRole.USER,
                    ConversationMessage.idempotency_key == idempotency_key,
                )
            ),
        )

    async def _existing_response(
        self, identity: IdentityContext, user_message: ConversationMessage
    ) -> AssistantResponse:
        conversation = await self.get_owned(identity, user_message.conversation_id)
        assistant = await self.session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.reply_to_message_id == user_message.id,
                ConversationMessage.user_id == identity.user_id,
                ConversationMessage.role == MessageRole.ASSISTANT,
            )
        )
        if assistant is None:
            raise ConversationConcurrentModificationError
        return self._response(conversation, user_message, assistant)

    @staticmethod
    def _failed(
        content: str,
        reason_code: str,
        sensitivity: DataSensitivity = DataSensitivity.PRIVATE,
    ) -> _AssistantMaterial:
        return _AssistantMaterial(
            content=content,
            status=MessageStatus.FAILED,
            outcome=AssistantOutcome.FAILED,
            sensitivity=sensitivity,
            reason_code=reason_code,
        )

    @staticmethod
    def _action_material(
        content: str,
        outcome: AssistantOutcome,
        workflow_id: UUID,
        reason_code: str | None,
        *,
        confirmation_request_id: UUID | None = None,
    ) -> _AssistantMaterial:
        return _AssistantMaterial(
            content=content,
            status=MessageStatus.COMPLETED,
            outcome=outcome,
            sensitivity=DataSensitivity.PRIVATE,
            orchestration_id=workflow_id,
            confirmation_request_id=confirmation_request_id,
            reason_code=reason_code,
        )

    @staticmethod
    def _response(
        conversation: Conversation,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
    ) -> AssistantResponse:
        return AssistantResponse(
            conversation=ConversationResponse.from_model(conversation),
            user_message=ConversationMessageResponse.from_model(user_message),
            assistant_message=ConversationMessageResponse.from_model(assistant_message),
        )
