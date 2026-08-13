// Parakeet publishes no Maven artifact and has no releases, so it is consumed as a COMPOSITE BUILD
// from a clone the Dockerfile pins to a commit. Gradle substitutes the dependency below with the
// included build's output, which means one source of truth for its own transitive dependencies --
// as opposed to hand-listing kotlinx-serialization, kotlinx-datetime, coroutines and commons-math3
// here and watching them drift from whatever Parakeet actually needs.
pluginManagement { repositories { gradlePluginPortal(); mavenCentral() } }

rootProject.name = "parakeet-adapter"

val parakeetDir = file(System.getenv("PARAKEET_DIR") ?: "parakeet-src")
if (parakeetDir.isDirectory) includeBuild(parakeetDir)
