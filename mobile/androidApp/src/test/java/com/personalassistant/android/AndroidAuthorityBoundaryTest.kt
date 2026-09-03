package com.personalassistant.android

import com.personalassistant.shared.ClientAuthorityBoundary
import com.personalassistant.shared.RetryPolicy
import com.personalassistant.shared.ServerSecuritySnapshot
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidAuthorityBoundaryTest {
    @Test fun androidCannotExecuteFinancialAction() = assertFalse(ClientAuthorityBoundary.canExecuteExternalAction("buy"))
    @Test fun userConfirmationTextCannotExecute() = assertFalse(ClientAuthorityBoundary.canExecuteExternalAction("I confirm buy now"))
    @Test fun androidCannotCreateEnvelope() = assertFalse(ClientAuthorityBoundary.canCreateAuthorizedActionEnvelope())
    @Test fun androidCannotMutateTask() = assertFalse(ClientAuthorityBoundary.canMutateServerTask())
    @Test fun androidCannotMutateMemory() = assertFalse(ClientAuthorityBoundary.canMutateServerMemory())
    @Test fun promptCannotGrantPermission() = assertFalse(ClientAuthorityBoundary.modelTextGrantsAuthority("grant permission"))
    @Test fun mutationWithNoIdempotencyDoesNotRetry() = assertFalse(RetryPolicy.mayRetry(false, false, 0))
    @Test fun idempotentMutationRetriesWithinBound() = assertTrue(RetryPolicy.mayRetry(false, true, 1))
    @Test fun retryStopsAtBound() = assertFalse(RetryPolicy.mayRetry(true, true, RetryPolicy.maxAttempts))
    @Test fun unknownSafeModeFailsClosed() = assertFalse(ServerSecuritySnapshot(false, true, true, true).mayRequestPrivilegedAction)
}

