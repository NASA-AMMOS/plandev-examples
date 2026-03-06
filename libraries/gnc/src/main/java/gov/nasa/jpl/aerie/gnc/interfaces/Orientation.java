package gov.nasa.jpl.aerie.gnc.interfaces;

import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

public class Orientation{

    private final Rotation rotation;
    private final Vector3D rotationRate;

    /**
     * Builds a rotation/rotation rate pair.
     *
     * @param rotation     rotation
     * @param rotationRate rotation rate omega (rad/s)
     */
    public Orientation(Rotation rotation, Vector3D rotationRate) {
        this.rotation = rotation;
        this.rotationRate = rotationRate;
    }

    /**
     * Orientation constructor when just rotation is available, so user does not need to pass null
     */
    public Orientation(Rotation rotation){
        this.rotation = rotation;
        this.rotationRate = null;
    }

    public Rotation getRotation(){
        return this.rotation;
    }

    public Vector3D getRotationRate(){
        return this.rotationRate;
    }

    public boolean isRotationRateDefined(){
        return rotationRate != null;
    }

}
