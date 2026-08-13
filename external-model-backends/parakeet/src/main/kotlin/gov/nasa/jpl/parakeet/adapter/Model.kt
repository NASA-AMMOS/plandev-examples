package gov.nasa.jpl.parakeet.adapter

import gov.nasa.jpl.parakeet.foundation.plans.Activity
import gov.nasa.jpl.parakeet.foundation.reporting.Reporting.registered
import gov.nasa.jpl.parakeet.foundation.resources.discrete.DiscreteResourceOperations.discreteResource
import gov.nasa.jpl.parakeet.foundation.resources.discrete.IntResourceOperations.increment
import gov.nasa.jpl.parakeet.foundation.resources.discrete.DiscreteResourceOperations.set
import gov.nasa.jpl.parakeet.foundation.resources.discrete.DoubleResourceOperations.increase
import gov.nasa.jpl.parakeet.foundation.resources.discrete.DoubleResourceOperations.decrease
import gov.nasa.jpl.parakeet.foundation.resources.discrete.MutableDiscreteResource
import gov.nasa.jpl.parakeet.foundation.resources.getValue
import gov.nasa.jpl.parakeet.foundation.tasks.InitScope
import gov.nasa.jpl.parakeet.foundation.tasks.ResourceScope.Companion.now
import gov.nasa.jpl.parakeet.foundation.tasks.TaskOperations.delay
import gov.nasa.jpl.parakeet.foundation.tasks.TaskOperations.delayUntil
import gov.nasa.jpl.parakeet.foundation.tasks.TaskScope
import kotlinx.serialization.Serializable
import kotlin.math.max
import kotlin.time.Duration
import kotlin.time.Duration.Companion.microseconds
import kotlin.time.Duration.Companion.seconds

/**
 * A solid-state recorder and its downlink, modeled in Parakeet.
 *
 * This is the fifth backend on PlanDev's external-model contract, and it exists to answer a
 * question the other four cannot: what does the contract look like when the simulator has
 * RIGOROUS CHECKPOINTING? Parakeet's tasks are Kotlin coroutines rather than threads, so a
 * simulation can be saved and restored with a stated algebraic guarantee. That is the property
 * whose absence made scheduling against an external model expensive.
 *
 * The model is deliberately small. What it exercises that no other backend does is a single
 * activity type:
 *
 *     Downlink has NO duration parameter, and its span's duration is EMERGENT --
 *     determined by simulating, not by the plan.
 *
 * It runs until the recorder is empty, which depends on how full the recorder was when it
 * started, which depends on every Collect that came before it. PlanDev models this as an
 * activity with an uncontrollable duration; the original architecture research flagged it (risk
 * M3) as the case that cannot be pre-resolved by flattening a plan. Every other adapter here
 * takes `duration` as an argument and hands the same number back.
 *
 * WHY EVERY PROFILE HERE IS A STAIRCASE, INCLUDING THE NUMERIC ONES.
 *
 * A Parakeet discrete cell holds a CONSTANT between writes. The recorder's level really is 8192
 * from the moment a collection ends until the moment a downlink finishes draining it -- that is
 * the model's state, not an approximation of one.
 *
 * The first version of this adapter reported it as a real profile, and PlanDev drew a straight line
 * between consecutive samples. The endpoints were right and every point between them was invented:
 * the stored profile sloped gently down for twenty minutes before a downlink had even started, at a
 * rate belonging to no part of the model. Adding a sample at the drain's start does not fix it
 * either -- writing a cell its own value is not an effect, so Parakeet reports nothing.
 *
 * The fix is to say what is true. A piecewise-constant quantity is a DISCRETE profile whatever its
 * values happen to be, so these are declared with a `real` SCHEMA (the values are reals) and
 * emitted as discrete (the shape is a staircase). Blackbird's constant reals reach PlanDev the
 * same way.
 *
 * Getting a genuine ramp out of Parakeet means a cell that evolves continuously, which the engine
 * supports and this model does not use. Sloped reals are already covered by two other backends; a
 * fifth one lying about its shape would not have added anything.
 */
class Recorder(context: InitScope, config: Config) {
    @Serializable
    data class Config(
        val capacityMb: Double = 8_192.0,
        val downlinkRateMbps: Double = 40.0,
        val initialLevelMb: Double = 0.0,
    )

    val capacityMb = config.capacityMb
    val downlinkRateMbps = config.downlinkRateMbps

    /** Megabits on the recorder. Written only at breakpoints -- see the class docstring. */
    val levelMb: MutableDiscreteResource<Double>

    /** What the recorder is doing. A variant on the PlanDev side. */
    val mode: MutableDiscreteResource<String>

    /** How many Collects have completed. An int profile, and an int on the wire -- not 3.0. */
    val collections: MutableDiscreteResource<Int>

    /** Megabits dropped because the recorder was full when a Collect tried to write. */
    val droppedMb: MutableDiscreteResource<Double>

    init {
        with(context) {
            levelMb = discreteResource("levelMb", config.initialLevelMb).registered()
            mode = discreteResource("mode", MODE_IDLE).registered()
            collections = discreteResource("collections", 0).registered()
            droppedMb = discreteResource("droppedMb", 0.0).registered()
        }
    }

    companion object {
        const val MODE_IDLE = "Idle"
        const val MODE_RECORDING = "Recording"
        const val MODE_DOWNLINKING = "Downlinking"
    }
}

/**
 * Fill the recorder for a fixed duration at a fixed rate.
 *
 * The ordinary case: the planner says how long, and the span says the same. Present so the
 * emergent-duration case below has something to be contrasted with -- and so a plan can put the
 * recorder into a state whose drain time is not obvious from any single directive.
 */
@Serializable
data class Collect(
    /** Microseconds, matching the wire contract. */
    val durationUs: Long,
    val rateMbps: Double,
) : Activity<Recorder> {
    context(scope: TaskScope)
    override suspend fun effectModel(model: Recorder) {
        model.mode.set(Recorder.MODE_RECORDING)

        val seconds = durationUs.microseconds / 1.seconds
        val offered = rateMbps * seconds

        delay(durationUs.microseconds)

        // Read AFTER the delay and applied as an EFFECT, not as a read-modify-write.
        //
        // Parakeet runs everything scheduled at the same instant as one batch, and within a batch
        // no task observes another's effects -- so two collections ending together would each read
        // the same level, each compute an absolute total from it, and the second `set` would erase
        // the first. Both would look like they worked. `increase` is an effect the cell merges, so
        // concurrent writers add up instead of clobbering, which is the entire reason a cell-based
        // engine has effects rather than setters.
        val room = max(0.0, model.capacityMb - model.levelMb.getValue())
        val stored = minOf(offered, room)
        model.levelMb.increase(stored)
        if (offered > stored) {
            model.droppedMb.increase(offered - stored)
        }
        model.collections.increment()
        model.mode.set(Recorder.MODE_IDLE)
    }
}

/**
 * Empty the recorder. NO duration parameter -- how long this takes is a result of the simulation.
 *
 * This is the whole reason this backend exists. The span PlanDev stores gets its duration from
 * when the task actually finished, and the only way to know that is to run the model: it is a
 * function of the recorder's level, which is a function of every Collect scheduled before it, and
 * of whether an earlier Downlink already drained some of it.
 *
 * A downlink of an empty recorder is instantaneous and produces a zero-duration span, which is a
 * different thing from an unfinished one.
 */
@Serializable
class Downlink : Activity<Recorder> {
    context(scope: TaskScope)
    override suspend fun effectModel(model: Recorder) {
        val startLevel = model.levelMb.getValue()
        if (startLevel <= 0.0) return

        model.mode.set(Recorder.MODE_DOWNLINKING)

        // Computed rather than stepped toward. The drain is linear, so its end is known in closed
        // form -- and asking the engine to wake at that instant is both exact and O(1), where
        // polling a condition forward would be neither.
        val seconds = startLevel / model.downlinkRateMbps
        val finishesAt = now() + (seconds * 1_000_000.0).toLong().microseconds
        delayUntil(finishesAt)

        model.levelMb.decrease(startLevel)
        model.mode.set(Recorder.MODE_IDLE)
    }
}

/** Total drain time for a full recorder, used by the declaration's documentation only. */
fun drainDuration(levelMb: Double, rateMbps: Double): Duration =
    ((levelMb / rateMbps) * 1_000_000.0).toLong().microseconds
