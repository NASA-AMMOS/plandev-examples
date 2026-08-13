plugins {
    kotlin("jvm") version "2.3.0"
    application
}

repositories { mavenCentral() }

dependencies {
    implementation("gov.nasa.jpl.parakeet:parakeet:1.0-SNAPSHOT")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")
    testImplementation(kotlin("test"))
}

kotlin {
    jvmToolchain(21)
    compilerOptions {
        // Parakeet's scopes ARE context parameters -- `context (scope: TaskScope)` is how a task
        // body gets its capabilities without threading a receiver through every call. Anything
        // built against it inherits the flag; this is not an opt-in we chose.
        freeCompilerArgs.add("-Xcontext-parameters")
        optIn.add("kotlin.time.ExperimentalTime")
    }
}

application {
    mainClass.set("gov.nasa.jpl.parakeet.adapter.MainKt")
    // The child is spawned once per request, so JVM startup is on the critical path of every
    // simulation. Class-data sharing and no bytecode verification of the JDK's own classes take a
    // measurable bite out of it; this is a short-lived process that does not need a warm JIT.
    applicationDefaultJvmArgs = listOf("-XX:TieredStopAtLevel=1", "-Xshare:auto", "-XX:+UseSerialGC")
}

tasks.test { useJUnitPlatform() }
