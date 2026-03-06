package tutorial;

public enum MagDataCollectionMode {
    OFF(0.0), // kbps
    LOW_RATE(500.0), // kbps
    HIGH_RATE(5000.0); // kbps

    private final double magDataRate;

    MagDataCollectionMode(double magDataRate) {
        this.magDataRate = magDataRate;
    }

    public double getDataRate() {
        return magDataRate;
    }
}
