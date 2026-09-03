import org.gradle.api.tasks.compile.JavaCompile

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.room)
}

fun secureUrl(property: String, fallback: String): String {
    val value = providers.gradleProperty(property).orElse(fallback).get()
    require(value.startsWith("https://")) { "$property must use HTTPS" }
    return value
}

android {
    namespace = "com.personalassistant.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.personalassistant.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 130000
        versionName = "0.13.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    flavorDimensions += "environment"
    productFlavors {
        create("local") {
            dimension = "environment"
            applicationIdSuffix = ".local"
            buildConfigField("String", "BACKEND_BASE_URL", "\"http://10.0.2.2:8000/\"")
            buildConfigField("String", "SUPABASE_URL", "\"\"")
            buildConfigField("String", "SUPABASE_ANON_KEY", "\"\"")
            buildConfigField("Boolean", "ALLOW_LOCAL_CLEARTEXT", "true")
        }
        create("staging") {
            dimension = "environment"
            applicationIdSuffix = ".staging"
            buildConfigField("String", "BACKEND_BASE_URL", "\"${secureUrl("stagingBackendUrl", "https://staging.invalid/")}\"")
            buildConfigField("String", "SUPABASE_URL", "\"${secureUrl("stagingSupabaseUrl", "https://staging.invalid/")}\"")
            buildConfigField("String", "SUPABASE_ANON_KEY", "\"${providers.gradleProperty("stagingSupabaseAnonKey").orElse("").get()}\"")
            buildConfigField("Boolean", "ALLOW_LOCAL_CLEARTEXT", "false")
        }
        create("production") {
            dimension = "environment"
            buildConfigField("String", "BACKEND_BASE_URL", "\"${secureUrl("productionBackendUrl", "https://production.invalid/")}\"")
            buildConfigField("String", "SUPABASE_URL", "\"${secureUrl("productionSupabaseUrl", "https://production.invalid/")}\"")
            buildConfigField("String", "SUPABASE_ANON_KEY", "\"${providers.gradleProperty("productionSupabaseAnonKey").orElse("").get()}\"")
            buildConfigField("Boolean", "ALLOW_LOCAL_CLEARTEXT", "false")
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging.resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}")
    testOptions.unitTests.isIncludeAndroidResources = true
    lint {
        // AGP 8.7.3 is intentionally pinned to the validated Gradle 8/JDK 17 toolchain.
        disable += "AndroidGradlePluginVersion"
        warningsAsErrors = true
        checkReleaseBuilds = true
    }
}

room { schemaDirectory("$projectDir/schemas") }

// KSP 1.0.29 uses shared incremental compiler state across Android variants. Keep only KSP tasks
// ordered while allowing the rest of the build to use all configured workers.
afterEvaluate {
    tasks
        .filter { it.name.startsWith("ksp") && it.name.endsWith("Kotlin") }
        .sortedBy { it.name }
        .zipWithNext()
        .forEach { (previous, current) -> current.mustRunAfter(previous) }
}

// KSP's byRounds directory is transient shadow state. It can survive KSP 1.0.29 cleanup and must
// never be treated as a second Java source root beside the canonical generated output.
tasks.withType<JavaCompile>().configureEach { exclude("**/byRounds/**") }

androidComponents {
    beforeVariants(selector().withBuildType("release")) { variant ->
        if (variant.productFlavors.any { it.second == "local" }) variant.enable = false
    }
}

dependencies {
    implementation(project(":shared"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.okhttp)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)
    implementation(libs.androidx.work.runtime)
    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
}
