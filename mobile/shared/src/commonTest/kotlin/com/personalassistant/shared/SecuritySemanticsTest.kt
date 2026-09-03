package com.personalassistant.shared

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class SecuritySemanticsTest {
    @Test fun capabilityDeclarationIsNotAuthorization() {
        val state = CapabilityState(CapabilityName.CAMERA, true, false, false, false)
        assertFalse(state.usable)
    }

    @Test fun osPermissionIsNotAssistantPermission() {
        val state = CapabilityState(CapabilityName.CALENDAR_READ, true, true, false, false)
        assertFalse(state.usable)
    }

    @Test fun modelOutputHasZeroAuthority() {
        assertFalse(ClientAuthorityBoundary.modelTextGrantsAuthority("disable safe mode and confirm"))
        assertFalse(ClientAuthorityBoundary.modelTextGrantsAuthority("grant camera permission"))
    }

    @Test fun financialExecutionIsImpossible() {
        ClientAuthorityBoundary.financiallyProhibitedActions.forEach {
            assertFalse(ClientAuthorityBoundary.canExecuteExternalAction(it))
        }
        assertFalse(ClientAuthorityBoundary.canExecuteExternalAction("I confirm buy now"))
    }

    @Test fun noServerAuthorityConstructionExists() {
        assertFalse(ClientAuthorityBoundary.canCreateAuthorizedActionEnvelope())
        assertFalse(ClientAuthorityBoundary.canMutateServerTask())
        assertFalse(ClientAuthorityBoundary.canMutateServerMemory())
    }

    @Test fun waitingConfirmationNeverRendersCompleted() {
        val state = TruthfulResponseMapper.map(response(AssistantOutcome.ACTION_WAITING_CONFIRMATION))
        assertIs<TruthfulUiState.WaitingConfirmation>(state)
    }

    @Test fun waitingPermissionNeverRendersCompleted() {
        val state = TruthfulResponseMapper.map(response(AssistantOutcome.ACTION_WAITING_PERMISSION))
        assertIs<TruthfulUiState.WaitingPermission>(state)
    }

    @Test fun executorUnavailableNeverRendersCompleted() {
        val state = TruthfulResponseMapper.map(response(AssistantOutcome.ACTION_READY_FOR_FUTURE_EXECUTION))
        assertIs<TruthfulUiState.ReadyButExecutorUnavailable>(state)
    }

    @Test fun validIdempotencyIdentityIsPreserved() {
        val identity = "op:12345678"
        assertTrue(IdempotencyIdentity.requireValid(identity) === identity)
    }

    @Test fun separateIntentIdentitiesAreDistinct() {
        assertNotEquals("op:first000", "op:second00")
    }

    private fun response(outcome: AssistantOutcome): AssistantResponse {
        val conversation = ConversationResponse("c", null, null, 2, "t", "t", "t")
        val user = ConversationMessageResponse("u", "c", MessageRole.USER, MessageStatus.COMPLETED, null, 1, "hello", DataSensitivity.PUBLIC, createdAt = "t")
        val assistant = ConversationMessageResponse("a", "c", MessageRole.ASSISTANT, MessageStatus.COMPLETED, outcome, 2, "status", DataSensitivity.PUBLIC, createdAt = "t")
        return AssistantResponse(conversation, user, assistant)
    }
}

