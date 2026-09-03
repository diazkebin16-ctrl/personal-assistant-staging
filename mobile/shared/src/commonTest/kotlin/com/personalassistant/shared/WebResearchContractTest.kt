package com.personalassistant.shared

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class WebResearchContractTest {
    private val json = Json { ignoreUnknownKeys = false }

    @Test
    fun strictContractDecodesResearchCitations() {
        val payload = """{
          "id":"a","conversation_id":"c","role":"ASSISTANT","status":"COMPLETED",
          "outcome":"RESEARCH_ANSWERED","sequence":2,"content":"Grounded answer",
          "sensitivity":"PRIVATE","orchestration_id":null,"confirmation_request_id":null,
          "memory_id":null,"reason_code":null,"citations":[{
            "citation_id":"cit_0123456789abcdef","evidence_id":"ev_0123456789abcdef",
            "url":"https://example.com/report","title":"Public report",
            "retrieved_at":"2026-09-02T12:00:00Z","locator":"passage-1"
          }],"created_at":"2026-09-02T12:00:00Z"
        }""".trimIndent()
        val decoded = json.decodeFromString<ConversationMessageResponse>(payload)
        assertEquals(AssistantOutcome.RESEARCH_ANSWERED, decoded.outcome)
        assertEquals("Public report", decoded.citations.single().title)
        assertTrue(decoded.citations.single().isSafeWebUrl())
    }

    @Test
    fun legacyMessagesRemainCompatibleWithEmptyCitations() {
        val payload = """{
          "id":"a","conversation_id":"c","role":"ASSISTANT","status":"COMPLETED",
          "outcome":"ANSWERED","sequence":2,"content":"Answer","sensitivity":"PRIVATE",
          "orchestration_id":null,"confirmation_request_id":null,"memory_id":null,
          "reason_code":null,"created_at":"2026-09-02T12:00:00Z"
        }""".trimIndent()
        assertTrue(json.decodeFromString<ConversationMessageResponse>(payload).citations.isEmpty())
    }

    @Test
    fun AndroidNeverTreatsDangerousSchemeAsSafeCitation() {
        val citation = ResearchCitationResponse(
            "cit_0123456789abcdef", "ev_0123456789abcdef", "javascript:alert(1)",
            "Unsafe", "2026-09-02T12:00:00Z", "passage-1",
        )
        assertFalse(citation.isSafeWebUrl())
    }

    @Test
    fun AndroidNeverTreatsPrivateTargetsAsSafeCitations() {
        val blocked = listOf(
            "http://localhost/a", "http://127.0.0.1/a", "http://10.0.0.1/a",
            "http://172.20.0.1/a", "http://192.168.1.1/a", "https://[::1]/a",
            "https://user@example.com/a",
        )
        blocked.forEachIndexed { index, url ->
            val citation = ResearchCitationResponse(
                "cit_0123456789abcde$index", "ev_0123456789abcde$index", url,
                "Unsafe", "2026-09-02T12:00:00Z", "passage-1",
            )
            assertFalse(citation.isSafeWebUrl(), url)
        }
    }

    @Test
    fun researchPermissionStateIsTruthful() {
        assertTrue(TruthfulResponseMapper.map(response(AssistantOutcome.RESEARCH_PERMISSION_REQUIRED)) is TruthfulUiState.WaitingPermission)
    }

    @Test
    fun researchPolicyDenialIsTruthful() {
        assertTrue(TruthfulResponseMapper.map(response(AssistantOutcome.RESEARCH_POLICY_DENIED)) is TruthfulUiState.Denied)
    }

    private fun response(outcome: AssistantOutcome): AssistantResponse {
        val conversation = ConversationResponse("c", version = 2, createdAt = "t", updatedAt = "t")
        val user = ConversationMessageResponse("u", "c", MessageRole.USER, MessageStatus.COMPLETED, null, 1, "query", DataSensitivity.PRIVATE, createdAt = "t")
        val assistant = ConversationMessageResponse("a", "c", MessageRole.ASSISTANT, MessageStatus.COMPLETED, outcome, 2, "status", DataSensitivity.PRIVATE, createdAt = "t")
        return AssistantResponse(conversation, user, assistant)
    }
}
