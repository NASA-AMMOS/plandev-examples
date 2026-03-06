import { bisector, range } from "d3-array";
import { Spice } from "timecraftjs";
import { differenceInDays, format } from "date-fns";

const SPACECRAFT_ID: number = 168; // Perseverence Rover Spacecraft ID
const LMST_SPACECRAFT_ID = parseInt(`-${SPACECRAFT_ID}900 `, 10);
const SPICE_LMST_RE: RegExp = /^\d\/(\d+):(\d{2}):(\d{2}):(\d{2}):(\d+)?$/;
const DISPLAY_LMST_RE: RegExp = /^(\d+)M(\d{2}):(\d{2}):(\d{2})(\.(\d+))?$/;
const LMST_FORMAT_STRING: string = "DDDDDMHH:MM:SS";

let spiceInstance: any = undefined;

// Mars seconds since Sol-0
function msss0(lmst: string): number {
  try {
    const sols = +lmst.split("M")[0];
    const hours = +lmst.split("M")[1].split(":")[0];
    const minutes = +lmst.split("M")[1].split(":")[1];
    const seconds = +lmst.split("M")[1].split(":")[2];
    const sss0 = sols * 86400 + hours * 3600 + minutes * 60 + seconds;
    return sss0;
  } catch (err) {
    console.log("LMST Plugin Error: msss0:", lmst, err);
    return NaN;
  }
}

function msss0_to_lmst(msss0: number): string {
  let sols = String(Math.floor(msss0 / 86400));
  let secondsLeft = msss0 % 86400;
  let hours = String(Math.floor(secondsLeft / 3600));
  secondsLeft = secondsLeft % 3600;
  let minutes = String(Math.floor(secondsLeft / 60));
  secondsLeft = secondsLeft % 60;
  let seconds = String(secondsLeft.toFixed(2));
  while (sols.length < 5) {
    sols = "0" + sols;
  }
  while (hours.length < 2) {
    hours = "0" + hours;
  }
  while (minutes.length < 2) {
    minutes = "0" + minutes;
  }
  while (seconds.length < 5) {
    seconds = "0" + seconds;
  }
  const lmst = sols + "M" + hours + ":" + minutes + ":" + seconds;
  return lmst;
}

function trimLeadingZeroes(s: string): string {
  return parseInt(s, 10).toString(10);
}

function lmstToEphemeris(lmst: string): number | null {
  const matcher = lmst.match(DISPLAY_LMST_RE);
  if (!matcher) {
    return null;
  }

  const sol = trimLeadingZeroes(matcher[1] || "");
  const hour = matcher[2] || "";
  const mins = matcher[3] || "";
  const secs = matcher[4] || "";
  const subsecs = parseFloat(matcher[5] || "0")
    .toFixed(5)
    .substring(2);
  const sclkch = `${sol}:${hour}:${mins}:${secs}:${subsecs}`;
  return spiceInstance.scs2e(LMST_SPACECRAFT_ID, sclkch);
}

function ephemerisToLMST(et: number): string | null {
  const lmst = spiceInstance.sce2s(LMST_SPACECRAFT_ID, et);
  // something like "1/01641:07:16:13:65583"
  const m = lmst.match(SPICE_LMST_RE);
  if (m) {
    const sol = trimLeadingZeroes(m[1]);
    const hour = m[2];
    const mins = m[3];
    const secs = m[4];
    const subsecs = m[5] || "0";
    return sol + "M" + hour + ":" + mins + ":" + secs + "." + subsecs;
  }
  return null;
}

function ephemerisToSCLK(et: number): string {
  const sclkStr = spiceInstance.sce2s(-SPACECRAFT_ID, et);
  // sclkStr = "1/0436236010-12059"
  const split: string[] = sclkStr.substring(2).split("-");
  const sclk =
    parseInt(split[0], 10) + parseInt(split[1], 10) / Math.pow(2, 16);
  return sclk.toFixed();
}

function ephemerisToUTC(et: number): Date {
  // Do not use more than 6 digits of precision since javascript date parsing will
  // not correctly interpret more precise numbers correctly since ISO-8601 spec is vague
  // This is not documented within JS Date parsing but can be seen by examining the output of
  // the following two statements:
  // new Date('2024 JUN 03 15:05:28.000001' + "Z").toISOString() -> '2024-06-03T15:05:28.000Z'
  // new Date('2024 JUN 03 15:05:28.0000010000000' + "Z").toISOString() -> '2024-06-03T15:05:28.010Z'
  // Notice the difference in the fractional seconds.
  // Semi-related post https://stackoverflow.com/a/50570660
  return new Date(spiceInstance.et2utc(et, "ISOC", 6) + "Z");
}

function lmstToUTC(lmst: string): Date | null {
  if (spiceInstance) {
    try {
      const et = lmstToEphemeris(lmst);
      if (typeof et !== "number") {
        throw new Error(`Ephemeris time not a number: ${et}`);
      }
      return ephemerisToUTC(et);
    } catch (error) {
      console.log("LMST Plugin Error: lmstToUTC:", error);
    }
  }
  return null;
}

function utcStringToLMST(utc: string): string | null {
  if (spiceInstance) {
    try {
      const et = spiceInstance.str2et(utc);
      return ephemerisToLMST(et);
    } catch (error) {
      console.error("LMST Plugin Error: utcStringToLMST:", utc, error);
      return null;
    }
  }
  return null;
}

function utcStringToSCLK(utc: string): string | null {
  if (spiceInstance) {
    try {
      const et = spiceInstance.str2et(utc);
      return ephemerisToSCLK(et);
    } catch (error) {
      console.error(error);
      return null;
    }
  }
  return null;
}

export function lmstTicks(start: Date, stop: Date, tickCount: number): Date[] {
  const lmstStart = utcStringToLMST(start.toISOString().slice(0, -1));
  const lmstEnd = utcStringToLMST(stop.toISOString().slice(0, -1));
  if (!lmstStart || !lmstEnd) {
    return [];
  }
  const lsmtStartSeconds = msss0(lmstStart);
  const lsmtStartSols = lsmtStartSeconds / 60 / 60 / 24;
  const lsmtEndSeconds = msss0(lmstEnd);
  const lsmtEndSols = lsmtEndSeconds / 60 / 60 / 24;
  // TODO handle duration = 0 case
  const lmstDurationSeconds = lsmtEndSeconds - lsmtStartSeconds;
  let stepSize;
  const stepSizeSols = lmstDurationSeconds / 60 / 60 / 24 / tickCount;
  const dayInSeconds = 86400;

  const lmstSteps = [
    0.1 / dayInSeconds,
    0.5 / dayInSeconds,
    1 / dayInSeconds,
    2 / dayInSeconds,
    5 / dayInSeconds,
    10 / dayInSeconds,
    15 / dayInSeconds,
    20 / dayInSeconds,
    30 / dayInSeconds,
    (1 * 60) / dayInSeconds,
    (2 * 60) / dayInSeconds,
    (5 * 60) / dayInSeconds,
    (10 * 60) / dayInSeconds,
    (15 * 60) / dayInSeconds,
    (20 * 60) / dayInSeconds,
    (30 * 60) / dayInSeconds,
    (1 * 60 * 60) / dayInSeconds,
    (2 * 60 * 60) / dayInSeconds,
    (3 * 60 * 60) / dayInSeconds,
    (4 * 60 * 60) / dayInSeconds,
    (6 * 60 * 60) / dayInSeconds,
    (8 * 60 * 60) / dayInSeconds,
    (12 * 60 * 60) / dayInSeconds,
    1,
    2,
    5,
    10,
    25,
    50,
    100,
    250,
    500,
    1000,
    2500,
    5000,
    1000,
  ];

  const bisectTicks = bisector((d) => d).left;
  const i = bisectTicks(lmstSteps, stepSizeSols, 0);
  stepSize = lmstSteps[i];

  // round the domain to nearest step size values
  const minValRounded = Math.round(lsmtStartSols / stepSize) * stepSize;
  const maxValRounded = Math.round(lsmtEndSols / stepSize) * stepSize;

  const ticks = range(minValRounded, maxValRounded, stepSize)
    .map((x) => lmstToUTC(msss0_to_lmst(x * 24 * 60 * 60)))
    .filter(
      (date) =>
        date &&
        date.getTime() >= start.getTime() &&
        date.getTime() <= stop.getTime()
    ) as Date[];

  return ticks;
}

async function initializeSpice() {
  try {
    const initializingSpice = await new Spice().init();

    // Load the kernels
    // TODO ensure this works when ui is deployed under a sub path
    // may need to pass in a base path
    const kernelBuffers = await Promise.all(
      [
        "/resources/kernels/m2020_lmst_ops210303_v1.tsc",
        "/resources/kernels/m2020.tls",
        "/resources/kernels/m2020.tsc",
      ].map((url) => fetch(url).then((res) => res.arrayBuffer()))
    );

    // Load the kernels into Spice
    for (let i = 0; i < kernelBuffers.length; i++) {
      initializingSpice.loadKernel(kernelBuffers[i]);
    }
    spiceInstance = initializingSpice;

    spiceInstance.erract("SET", "REPORT");

    // Log stderr and stdout and reset spice if failed
    // TODO not seeing stdErr, spice/timecraft may not be reporting these errors to stderr under "REPORT"
    // mode so our try/catch exceptions may not be getting called. Need to sort out best way of handling
    // errors from spice/timecraft and figure out if it is plugin or aerie UI that needs to know if a
    // particular function failed.
    spiceInstance.onStdErr = (err: string) => {
      if (spiceInstance.failed()) {
        const msg = spiceInstance.getmsg("LONG");
        console.error(msg);
        spiceInstance.reset();
      } else {
        console.error(err);
      }
    };
    spiceInstance.onStdOut = (string: string) => {
      if (spiceInstance.failed()) {
        const msg = spiceInstance.getmsg("LONG");
        console.error(msg);
        spiceInstance.reset();
      } else {
        console.log(string);
      }
    };

    console.log("Spice initialized", spiceInstance);
    return true;
  } catch (error) {
    console.log("Error initializing Spice:", error);
    return false;
  }
}

function validateLMSTString(value: string): Promise<null | string> {
  return new Promise((resolve) => {
    const match = DISPLAY_LMST_RE.exec(value);
    const error = `LMST format required: ${LMST_FORMAT_STRING}`;
    return match ? resolve(null) : resolve(error);
  });
}

const LMST_TIME = "HH:mm:ss";
// 3613M04:04:13.84606
const lmstPattern = /(\d+)M(\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)/;
const ROUNDING_MS = 500;

// This function doesn't use surface epoch or mars seconds since it is purely for rounding times
export function roundLMST(s: string) {
  const m = s.match(lmstPattern);
  if (m) {
    const year = 2020;
    const monthIndex = 0;
    const dayOfMonth = 1;
    const sol = parseInt(m[1], 10);
    const hours = parseInt(m[2], 10);
    const minutes = parseInt(m[3], 10);
    const seconds = parseInt(m[4], 10);
    const ms = m[5] ? ROUNDING_MS + 1000 * parseFloat(m[5]) : 0;
    const t0 = new Date(year, monthIndex, dayOfMonth);
    const d = new Date(
      year,
      monthIndex,
      dayOfMonth,
      hours,
      minutes,
      seconds,
      ms
    );

    return `${sol + differenceInDays(d, t0)}M${format(d, LMST_TIME)}`;
  }

  return s;
}

function formatPrimaryTime(date: Date) {
  const dateWithoutTZ = date.toISOString().slice(0, -1);
  const lmst = utcStringToLMST(dateWithoutTZ);
  if (!lmst) {
    return null;
  }
  return roundLMST(lmst);
}

function formatTickLMST(
  date: Date,
  viewDurationMs: number,
  tickCount: number
): string | null {
  return formatPrimaryTime(date);
}

export async function getPlugin() {
  const success = await initializeSpice();
  if (success) {
    return {
      time: {
        enableDatePicker: false,
        getDefaultPlanEndDate: (start: Date) => {
          // Format to LMST, add a sol, parse back to Date
          const lmst = formatPrimaryTime(start);
          if (!lmst) {
            return null;
          }
          const sols = +lmst.split("M")[0];
          return lmstToUTC(`${sols + 1}M${lmst.split("M")[1]}`);
        },
        primary: {
          format: formatPrimaryTime,
          formatShort: formatPrimaryTime,
          formatString: LMST_FORMAT_STRING,
          formatTick: formatTickLMST,
          label: "LMST",
          parse: lmstToUTC,
          validate: validateLMSTString,
        },
        additional: [
          {
            format: (date: Date) => {
              const dateWithoutTZ = date.toISOString().slice(0, -1);
              return utcStringToSCLK(dateWithoutTZ);
            },
            label: "SCLK",
          },
          {
            format: (date: Date) => date.toISOString().slice(0, -5),
            label: "UTC",
          },
        ],
        ticks: {
          getTicks: lmstTicks,
          maxLabelWidth: 110,
        },
      },
    };
  } else {
    return {};
  }
}
