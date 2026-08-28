package examples.orbiter.geometry.activities.spawner;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.jpl.time.Time;
import gov.nasa.ammos.plandev.geometry.globals.JPLTimeConvertUtility;
import examples.orbiter.Mission;
import gov.nasa.ammos.plandev.geometry.globals.Window;
import examples.orbiter.geometry.activities.atomic.EnterOccultation;
import examples.orbiter.geometry.activities.atomic.ExitOccultation;
import gov.nasa.ammos.plandev.geometry.directspicecalls.SpiceDirectEventGenerator;
import gov.nasa.ammos.plandev.geometry.interfaces.GeometryInformationNotAvailableException;

import java.util.ArrayList;
import java.util.List;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static examples.orbiter.generated.ActivityActions.spawn;

@ActivityType("AddOccultations")
@Subsystem("geometry")
public class AddOccultations {

  @Export.Parameter
  public gov.nasa.ammos.plandev.merlin.protocol.types.Duration searchDuration;

  @Export.Parameter
  public String observer;
  @Export.Parameter
  public String target;
  @Export.Parameter
  public String occultingBody;
  @Export.Parameter
  public gov.nasa.ammos.plandev.merlin.protocol.types.Duration stepSize;
  @Export.Parameter
  public Boolean useDSK;

  @ActivityType.EffectModel
  public void run(Mission model){
    SpiceDirectEventGenerator generator = new SpiceDirectEventGenerator();

    List<Window> occultationTimes;

    try {
      // we are looking from the observer (e.g. a DSN station) and treating the target spacecraft as a point source,
      // and so a 'partial' is not meaningful
      occultationTimes = generator.getOccultations( JPLTimeConvertUtility.nowJplTime(model.absoluteClock),
        JPLTimeConvertUtility.jplTimeFromUTCInstant(
          model.absoluteClock.now().plusMillis( searchDuration.in(Duration.MILLISECOND) )),
        JPLTimeConvertUtility.getJplTimeDur(stepSize), observer, target, occultingBody,"CN", true, true, useDSK);
    } catch (GeometryInformationNotAvailableException e) {
      occultationTimes = new ArrayList<>();
    }

    Duration durToSearchEnd = searchDuration;

    // There may be some occultations that are before the start of this activity. Remove them or alter the start time to start
    // at the start time of the activity
    Time actStart = JPLTimeConvertUtility.nowJplTime(model.absoluteClock);
    while (!occultationTimes.isEmpty() && occultationTimes.get(0).getStart().lessThan(actStart)) {
      if (occultationTimes.get(0).getEnd().lessThanOrEqualTo(actStart)) {
        occultationTimes.remove(0);
      } else if (occultationTimes.get(0).getStart().lessThan(actStart)) {
        occultationTimes.set(0, new Window(actStart, occultationTimes.get(0).getEnd(), occultationTimes.get(0).getType()) );
      }
    }

    for(Window w : occultationTimes){
      // Don't spawn any occultations at or after the end of the search duration
      if (w.getStart().lessThan(actStart.plus(JPLTimeConvertUtility.getJplTimeDur(searchDuration)))) {
        // Wait until start time of occultation and spawn EnterOccultation
        Duration delayTime = JPLTimeConvertUtility.getDuration(
          w.getStart().minus(JPLTimeConvertUtility.nowJplTime(model.absoluteClock)));
        delay(delayTime);

        // Assume 'target' is always the spacecraft
        spawn(model, new EnterOccultation(occultingBody, observer));
        durToSearchEnd = durToSearchEnd.minus(delayTime);

        // Wait until end time of occultation and spawn ExitOccultation
        delayTime = JPLTimeConvertUtility.getDuration(
          w.getEnd().minus(JPLTimeConvertUtility.nowJplTime(model.absoluteClock)));

        // Check to make sure the end of the occultation is not past the end of the search window. If it is, we are done
        // and do not need to add an exit occultation activity
        if (durToSearchEnd.minus(delayTime).isPositive()) {
          delay(delayTime);
          // Assume 'target' is always the spacecraft
          spawn(model, new ExitOccultation(occultingBody, observer));
          durToSearchEnd = durToSearchEnd.minus(delayTime);
        }
      }

    }

    // Make the activity span the entire search window
    delay (durToSearchEnd);
  }
}
