import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Map;
import java.util.TreeMap;

/**
 * Dump a Blackbird adaptation's SIMULATION CONFIGURATION as JSON, so the adapter can report it to
 * PlanDev and let a planner edit it.
 *
 * Blackbird's configuration is the set of public static fields on subclasses of
 * {@code gov.nasa.jpl.engine.ParameterDeclaration} -- the adaptation's globals. The engine can already
 * enumerate them ({@code collectNamesOfAllParameters} fills a {@code className -> fieldName -> Field}
 * map), report their types, and set them ({@code SET_PARAMETER Class.Field value}). What it has no way
 * to do is *print* them: CREATE_DICTIONARY emits only activities, and there is no SHOW_PARAMETERS
 * command. This 40-line helper is the missing accessor, not new machinery.
 *
 * Output: [{"class":..., "field":..., "type":..., "default":...}], sorted, one line.
 * The default is the field's initial value -- what the adaptation runs with when PlanDev sends nothing.
 */
public final class BbParams {
  public static void main(final String[] args) throws Exception {
    final var pd = Class.forName("gov.nasa.jpl.engine.ParameterDeclaration");
    pd.getMethod("collectNamesOfAllParameters").invoke(null);

    final var registry = pd.getDeclaredField("allFieldsInAdaptation");
    registry.setAccessible(true);
    @SuppressWarnings("unchecked")
    final var byClass = (Map<String, Map<String, Field>>) registry.get(null);

    final var out = new StringBuilder("[");
    var first = true;
    for (final var cls : new TreeMap<>(byClass == null ? Map.<String, Map<String, Field>>of() : byClass).entrySet()) {
      for (final var fld : new TreeMap<>(cls.getValue()).entrySet()) {
        final var f = fld.getValue();
        if (!Modifier.isStatic(f.getModifiers())) continue;
        f.setAccessible(true);
        Object value;
        try {
          value = f.get(null);
        } catch (final Throwable t) {
          value = null;
        }
        if (!first) out.append(',');
        first = false;
        out.append("{\"class\":").append(quote(cls.getKey()))
           .append(",\"field\":").append(quote(fld.getKey()))
           .append(",\"type\":").append(quote(f.getType().getSimpleName()))
           .append(",\"default\":").append(quote(value == null ? null : String.valueOf(value)))
           .append('}');
      }
    }
    System.out.println(out.append(']'));
  }

  /** Values reach us as toString() text, so everything is emitted as a JSON string or null. */
  private static String quote(final String s) {
    if (s == null) return "null";
    final var b = new StringBuilder("\"");
    for (final var c : s.toCharArray()) {
      switch (c) {
        case '"'  -> b.append("\\\"");
        case '\\' -> b.append("\\\\");
        case '\n' -> b.append("\\n");
        case '\r' -> b.append("\\r");
        case '\t' -> b.append("\\t");
        default   -> { if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c); }
      }
    }
    return b.append('"').toString();
  }
}
