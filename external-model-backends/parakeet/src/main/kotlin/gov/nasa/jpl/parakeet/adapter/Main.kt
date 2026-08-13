package gov.nasa.jpl.parakeet.adapter

import gov.nasa.jpl.parakeet.foundation.Simulator
import gov.nasa.jpl.parakeet.foundation.plans.ActivityActions.ActivityEvent
import gov.nasa.jpl.parakeet.foundation.plans.ActivityActions.spawn
import gov.nasa.jpl.parakeet.foundation.plans.GroundedActivity
import gov.nasa.jpl.parakeet.foundation.tasks.InitScope.Companion.spawn
import gov.nasa.jpl.parakeet.foundation.resources.discrete.Discrete
import gov.nasa.jpl.parakeet.foundation.tasks.InitScope
import gov.nasa.jpl.parakeet.foundation.tasks.task
import gov.nasa.jpl.parakeet.general.results.MutableSimulationResults
import gov.nasa.jpl.parakeet.general.results.SimulationResultsOperations.reportHandler
import gov.nasa.jpl.parakeet.kernel.Name
import kotlinx.serialization.json.*
import kotlin.system.exitProcess
import kotlin.time.Duration.Companion.microseconds
import kotlin.time.Instant

/**
 * The `ExecBackend` stdio protocol, for a Parakeet model.
 *
 *     parakeet-model describe   -> the declaration, as JSON, on stdout
 *     parakeet-model simulate   <- a normalized request on stdin
 *                               -> {realProfiles, discreteProfiles, spans} on stdout
 *
 * Everything else -- HTTP, `?model=` resolution, defaults, the ValueSchema typechecker, the
 * identity hash, response validation -- belongs to `adapter_core` on the Python side. Nothing in
 * this file knows what an identity hash is, and that is the point: this is the second language to
 * plug in through `ExecBackend`, and the first was Rust.
 *
 * EXIT 2 means "your request was wrong", not "I failed", and the host turns it into a 400 carrying
 * the message below. Any other nonzero exit is a 500.
 */
private const val EXIT_BAD_REQUEST = 2

private const val US_PER_S = 1_000_000L

fun main(args: Array<String>) {
    try {
        when (args.firstOrNull()) {
            "describe" -> println(Json.encodeToString(JsonObject.serializer(), declaration()))
            "simulate" -> println(Json.encodeToString(JsonObject.serializer(), simulate(readRequest())))
            else -> fail("usage: parakeet-model {describe|simulate}", model = true)
        }
    } catch (e: BadRequest) {
        System.err.println(e.message)
        exitProcess(EXIT_BAD_REQUEST)
    }
}

private class BadRequest(message: String) : Exception(message)

private fun fail(message: String, model: Boolean = false): Nothing {
    if (model) {
        System.err.println(message)
        exitProcess(1)
    }
    throw BadRequest(message)
}

private fun readRequest(): JsonObject =
    try {
        Json.parseToJsonElement(System.`in`.readBytes().decodeToString()).jsonObject
    } catch (e: Exception) {
        fail("simulate: stdin was not a JSON object: ${e.message}")
    }

// ---------- declaration -------------------------------------------------------------------------

private fun schema(type: String) = buildJsonObject { put("type", type) }

private fun variant(vararg keys: String) = buildJsonObject {
    put("type", "variant")
    putJsonArray("variants") {
        keys.forEach { add(buildJsonObject { put("key", it); put("label", it) }) }
    }
}

private fun declaration(): JsonObject = buildJsonObject {
    put("key", "recorder")
    put("name", "recorder")
    put("version", "1.0.0")

    putJsonArray("activityTypes") {
        add(buildJsonObject {
            put("name", "Collect")
            putJsonArray("parameters") {
                add(buildJsonObject { put("name", "duration"); put("schema", schema("duration")) })
                add(buildJsonObject {
                    put("name", "rateMbps"); put("schema", schema("real")); put("default", 120.0)
                })
            }
            putJsonArray("requiredParameters") { add("duration") }
            // A closed EMPTY struct, which is the honest declaration: nothing about a Collect is
            // derived that the plan did not already say. Declaring fields the span cannot fill
            // would have merlin's gate reject every span for a missing attribute.
            put("computedAttributesSchema", buildJsonObject {
                put("type", "struct"); putJsonObject("items") { }
            })
        })
        add(buildJsonObject {
            put("name", "Downlink")
            // NO duration parameter. How long this takes is a result of simulating, which is the
            // one thing this backend exists to demonstrate -- every other adapter here is handed a
            // duration and hands the same number back.
            putJsonArray("parameters") {}
            putJsonArray("requiredParameters") {}
            // The one genuinely DERIVED value in the model: how long the drain took. It is not an
            // argument restated -- no directive said it, and no reading of the plan predicts it.
            put("computedAttributesSchema", buildJsonObject {
                put("type", "struct")
                putJsonObject("items") { put("drainSeconds", schema("real")) }
            })
        })
    }

    putJsonArray("resourceTypes") {
        add(buildJsonObject { put("name", "/recorder/levelMb"); put("schema", schema("real")) })
        add(buildJsonObject { put("name", "/recorder/droppedMb"); put("schema", schema("real")) })
        add(buildJsonObject { put("name", "/recorder/collections"); put("schema", schema("int")) })
        add(buildJsonObject {
            put("name", "/recorder/mode")
            put("schema", variant(Recorder.MODE_IDLE, Recorder.MODE_RECORDING, Recorder.MODE_DOWNLINKING))
        })
    }

    putJsonArray("parameters") {
        add(buildJsonObject {
            put("name", "capacityMb"); put("schema", schema("real")); put("default", 8192.0)
        })
        add(buildJsonObject {
            put("name", "downlinkRateMbps"); put("schema", schema("real")); put("default", 40.0)
        })
        add(buildJsonObject {
            put("name", "initialLevelMb"); put("schema", schema("real")); put("default", 0.0)
        })
    }

    // A pure simulator: directives in, profiles and spans out, placing nothing of its own. Declared
    // rather than assumed -- an absent capability means unsupported, so a pure simulator that says
    // nothing gets published as one PlanDev's scheduler must not drive.
    putJsonObject("capabilities") {
        putJsonObject("plandevScheduling") { put("supported", true) }
    }
}

// ---------- simulate ------------------------------------------------------------------------------

private fun JsonObject.long(key: String): Long =
    this[key]?.jsonPrimitive?.longOrNull ?: fail("request is missing an integer `$key`")

private fun JsonObject.double(key: String, fallback: Double): Double =
    this[key]?.jsonPrimitive?.doubleOrNull ?: fallback

private fun simulate(request: JsonObject): JsonObject {
    val durationUs = request.long("duration")
    if (durationUs <= 0) fail("simulation duration must be positive, got ${durationUs}us")

    val planStart = request["planStart"]?.jsonPrimitive?.contentOrNull
        ?.let { runCatching { Instant.parse(it) }.getOrNull() }
        ?: Instant.parse("2000-01-01T00:00:00Z")
    val end = planStart + durationUs.microseconds

    val configuration = request["configuration"]?.jsonObject ?: JsonObject(emptyMap())
    val config = Recorder.Config(
        capacityMb = configuration.double("capacityMb", 8192.0),
        downlinkRateMbps = configuration.double("downlinkRateMbps", 40.0),
        initialLevelMb = configuration.double("initialLevelMb", 0.0),
    )
    if (config.capacityMb <= 0) fail("capacityMb must be > 0, got ${config.capacityMb}")
    if (config.downlinkRateMbps <= 0) fail("downlinkRateMbps must be > 0, got ${config.downlinkRateMbps}")
    if (config.initialLevelMb < 0 || config.initialLevelMb > config.capacityMb) {
        fail("initialLevelMb must be between 0 and capacityMb (${config.capacityMb}), " +
             "got ${config.initialLevelMb}")
    }

    // Directive id -> the Name the activity runs under, so spans can be matched back afterwards.
    // Parakeet reports activities by name; PlanDev needs the directive that produced them.
    val directiveForName = HashMap<String, Long>()
    val argumentsFor = HashMap<Long, JsonObject>()
    val grounded = ArrayList<GroundedActivity<Recorder>>()

    for (element in request["directives"]?.jsonArray ?: JsonArray(emptyList())) {
        val d = element.jsonObject
        val id = d.long("id")
        val type = d["type"]?.jsonPrimitive?.contentOrNull ?: fail("directive $id has no type")
        val startOffset = d.long("startOffset")
        if (startOffset < 0) fail("directive $id starts ${-startOffset}us before the plan")
        val arguments = d["arguments"]?.jsonObject ?: JsonObject(emptyMap())

        val activity = when (type) {
            "Collect" -> {
                val durUs = arguments.long("duration")
                if (durUs <= 0) fail("directive $id (Collect) has duration ${durUs}us; it must be positive")
                Collect(durUs, arguments.double("rateMbps", 120.0))
            }
            "Downlink" -> Downlink()
            else -> fail("directive $id has unknown activity type '$type'")
        }
        val name = Name("d$id")
        directiveForName[name.toString()] = id
        argumentsFor[id] = arguments
        grounded.add(GroundedActivity(planStart + startOffset.microseconds, name, activity))
    }

    val results = MutableSimulationResults(planStart, end)
    // Declared as an EXTENSION lambda rather than written inline: `Simulator` takes its model
    // constructor as `context (InitScope) () -> M`, and an `InitScope.() -> M` adapts to it while
    // also giving the scope a name -- which the Recorder's constructor needs as a value.
    val construct: InitScope.() -> Recorder = {
        val recorder = Recorder(this, config)
        for (activity in grounded) {
            // One task per directive, each spawning its activity at its grounded time. The task's
            // name is what shows up in results.activities, and is how a span finds its directive.
            // No "/" -- Name reserves it as its own hierarchy separator, and a simple
            // name containing one is rejected at construction.
            spawn("plan_${activity.name}", task { spawn(activity, recorder) })
        }
        recorder
    }
    Simulator(reportHandler = results.reportHandler(), startTime = planStart,
              constructModel = construct).runUntil(end)

    return buildJsonObject {
        put("realProfiles", profiles(results, durationUs, real = true))
        put("discreteProfiles", profiles(results, durationUs, real = false))
        put("spans", spans(results, planStart, durationUs, directiveForName, argumentsFor))
    }
}

/** Which channel feeds which resource, and whether PlanDev stores it as real or discrete. */
// Empty on purpose. Every cell in this model is discrete, so nothing evolves continuously and
// nothing belongs in a real profile -- see the note on staircases in Model.kt.
private val REAL_RESOURCES = emptyMap<String, String>()

// Note `levelMb` and `droppedMb`: declared with a `real` SCHEMA, because their values are reals,
// but emitted as DISCRETE, because their shape is a staircase. Those are separate questions and
// PlanDev keeps them separate.
private val DISCRETE_RESOURCES = mapOf(
    "levelMb" to "/recorder/levelMb",
    "droppedMb" to "/recorder/droppedMb",
    "collections" to "/recorder/collections",
    "mode" to "/recorder/mode",
)

/**
 * Resource reports -> `{name: {samples: [[offsetUs, value], ...]}}`.
 *
 * SAMPLES, not segments, on purpose. `adapter_core` owns the sample-to-segment conversion --
 * secant rates, the extended final segment, coalescing -- and it owns it because that conversion
 * is generic and every way of getting it wrong is silent. Emitting segments from here would be a
 * second implementation of it in a second language, which is exactly the duplication `adapter_core`
 * was extracted to end.
 */
private fun profiles(
    results: MutableSimulationResults,
    durationUs: Long,
    real: Boolean,
): JsonObject {
    val wanted = if (real) REAL_RESOURCES else DISCRETE_RESOURCES
    return buildJsonObject {
        for ((channel, resourceName) in wanted) {
            val profile = results.resources[Name(channel)] ?: continue
            putJsonObject(resourceName) {
                putJsonArray("samples") {
                    for (report in profile.data) {
                        val offsetUs = (report.time - results.startTime).inWholeMicroseconds
                        if (offsetUs < 0 || offsetUs > durationUs) continue
                        add(buildJsonArray {
                            add(offsetUs)
                            addValue(report.data)
                        })
                    }
                }
            }
        }
    }
}

/**
 * A reported value -> JSON, unwrapping Parakeet's dynamics first.
 *
 * A registered resource reports its DYNAMICS, not its value: a discrete cell holding 8192.0 arrives
 * as `Discrete(8192.0)`. Serializing that with `toString()` produces the JSON STRING "8192.0", which
 * merlin's gate then rejects against a `real` schema -- and would have rejected identically for an
 * int or a boolean. Unwrap first, then match on the type.
 */
private fun JsonArrayBuilder.addValue(reported: Any?) {
    val value = if (reported is Discrete<*>) reported.value else reported
    when (value) {
        is Int -> add(value)
        is Long -> add(value)
        is Double -> add(value)
        is Boolean -> add(value)
        null -> add(JsonNull)
        else -> add(value.toString())
    }
}

/**
 * Activity events -> spans.
 *
 * An event with no `end` is one the simulation never saw finish, which PlanDev models directly as
 * a span with no duration -- and, because merlin tells finished from unfinished by the presence of
 * BOTH `duration` and `computedAttributes`, with no computed attributes either.
 */
private fun spans(
    results: MutableSimulationResults,
    planStart: Instant,
    durationUs: Long,
    directiveForName: Map<String, Long>,
    argumentsFor: Map<Long, JsonObject>,
): JsonArray = buildJsonArray {
    // Parakeet reports an activity TWICE -- once when it starts (end == null) and once when it
    // finishes (end set). Emitting a span per event would double every activity in the plan, and
    // the first of each pair would look exactly like a legitimately unfinished one. Keep the last
    // event per name: for a finished activity that is the one carrying the end, and for an activity
    // the simulation never saw finish there is only ever the start.
    val lastEventByName = LinkedHashMap<String, ActivityEvent>()
    for (event in results.activities) lastEventByName[event.name.toString()] = event

    var spanId = 0L
    for (activity in lastEventByName.values) {
        val directiveId = directiveForName[activity.name.toString()] ?: continue
        val startUs = (activity.start - planStart).inWholeMicroseconds
        val endUs = activity.end?.let { (it - planStart).inWholeMicroseconds }
        spanId += 1
        add(buildJsonObject {
            put("spanId", spanId)
            put("type", activity.type)
            put("startOffset", startUs)
            put("directiveId", directiveId)
            put("parentId", JsonNull)
            // The EFFECTIVE arguments the host normalized, echoed rather than re-derived. An
            // argument the model invented here is one merlin's gate rejects as undeclared.
            put("arguments", argumentsFor[directiveId] ?: JsonObject(emptyMap()))
            if (endUs != null && endUs <= durationUs) {
                val spanUs = endUs - startUs
                put("duration", spanUs)
                putJsonObject("computedAttributes") {
                    if (activity.type == "Downlink") {
                        put("drainSeconds", spanUs.toDouble() / US_PER_S)
                    }
                }
            }
        })
    }
}
