package tutorial;

import gov.nasa.jpl.aerie.contrib.streamline.modeling.Registrar;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.spawn;

public final class Mission {

  public final Registrar errorRegistrar;
  public final DataModel dataModel;

  public Mission(final gov.nasa.jpl.aerie.merlin.framework.Registrar registrar, final Configuration config) {
    this.errorRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Log);
    // Tutorial code
    this.dataModel = new DataModel(this.errorRegistrar, config);

    //
    // Integration Method 4 - Sample-based integration
    //
    // Spawn daemon task to integrate SSR at a fixed interval of time
    spawn(dataModel::integrateSampledSSR);
  }
}
