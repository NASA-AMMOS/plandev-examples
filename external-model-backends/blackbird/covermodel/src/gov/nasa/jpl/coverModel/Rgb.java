package gov.nasa.jpl.coverModel;

/**
 * A custom Comparable value type.
 *
 * This is the ONLY kind of non-scalar a Blackbird resource can hold: Resource is declared
 * {@code Resource<V extends Comparable>}, so List- and Map-valued resources are impossible
 * (ArrayList/HashMap are not Comparable). Blackbird emits such a resource as
 * {@code <RgbValue>} containing {@code toString()}, with DataType = the simple class name.
 */
public class Rgb implements Comparable<Rgb> {
    private final int r, g, b;

    public Rgb(int r, int g, int b) { this.r = r; this.g = g; this.b = b; }

    private int packed() { return (r << 16) | (g << 8) | b; }

    @Override
    public int compareTo(Rgb o) { return Integer.compare(packed(), o.packed()); }

    @Override
    public String toString() { return r + "," + g + "," + b; }
}
