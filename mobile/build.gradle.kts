plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.room) apply false
}

subprojects {
    dependencyLocking { lockAllConfigurations() }
    configurations.configureEach {
        resolutionStrategy {
            force("com.google.guava:guava:${libs.versions.guava.get()}")
            force("com.google.protobuf:protobuf-java:${libs.versions.protobuf.get()}")
            force("commons-io:commons-io:${libs.versions.commonsIo.get()}")
            eachDependency {
                if (requested.group == "io.netty") useVersion(libs.versions.netty.get())
            }
        }
    }
}
