package com.personalassistant.shared

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RetryAndFailClosedTest {
    @Test fun readMayRetryWithinBound() = assertTrue(RetryPolicy.mayRetry(true, false, 1))
    @Test fun mutationMayRetryWithStableIdentity() = assertTrue(RetryPolicy.mayRetry(false, true, 1))
    @Test fun mutationNeverBlindRetries() = assertFalse(RetryPolicy.mayRetry(false, false, 1))
    @Test fun retryStopsAtBound() = assertFalse(RetryPolicy.mayRetry(true, true, RetryPolicy.maxAttempts))
    @Test fun unknownSafeModeFailsClosed() = assertFalse(ServerSecuritySnapshot(false, true, true, true).mayRequestPrivilegedAction)
    @Test fun cachedNormalDoesNotReplaceUnknownServerMode() = assertFalse(ServerSecuritySnapshot(false, false, true, true).mayRequestPrivilegedAction)
    @Test fun unknownPermissionFailsClosed() = assertFalse(ServerSecuritySnapshot(true, true, false, true).mayRequestPrivilegedAction)
    @Test fun deniedPermissionFailsClosed() = assertFalse(ServerSecuritySnapshot(true, true, true, false).mayRequestPrivilegedAction)
    @Test fun allServerConditionsAreRequired() = assertTrue(ServerSecuritySnapshot(true, true, true, true).mayRequestPrivilegedAction)
    @Test fun safeModeBlocksAction() = assertFalse(ServerSecuritySnapshot(true, false, true, true).mayRequestPrivilegedAction)
}

