const timeZone = "America/New_York";

export function getTimeZoneShortName(timeZone) {
  // set up formatter
  const formatter = new Intl.DateTimeFormat(undefined, {
    timeZoneName: "short",
    timeZone,
  });
  // run formatter on current date
  const parts = formatter?.formatToParts(Date.now());
  // extract the actual value from the formatter
  const timeZoneName = parts.find(
    (formatted) => formatted.type === "timeZoneName"
  );
  if (timeZoneName) {
    return timeZoneName.value;
  }
  return "UNK";
}

export async function getPlugin() {
  console.log("Plugin loaded");
  return {
    time: {
      additional: [
        {
          format: (date) => date.toLocaleString("en-US", { timeZone }),
          label: getTimeZoneShortName(timeZone),
        },
      ],
    },
  };
}
