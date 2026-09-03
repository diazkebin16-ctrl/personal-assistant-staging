package com.personalassistant.android

import com.personalassistant.android.work.DeliveryScheduler
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class DeliveryCorrectionTest {
    @Test fun sameOperationUsesSameUniqueWorkIdentity() {
        assertEquals(
            DeliveryScheduler.uniqueWorkName("operation-1"),
            DeliveryScheduler.uniqueWorkName("operation-1"),
        )
    }

    @Test fun separateOperationsUseSeparateUniqueWorkIdentities() {
        assertNotEquals(
            DeliveryScheduler.uniqueWorkName("operation-1"),
            DeliveryScheduler.uniqueWorkName("operation-2"),
        )
    }

    @Test fun workIdentityPreservesOperationId() {
        assertEquals("message:operation-1", DeliveryScheduler.uniqueWorkName("operation-1"))
    }
}
