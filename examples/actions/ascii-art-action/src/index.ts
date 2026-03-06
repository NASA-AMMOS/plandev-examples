import {
  ActionsAPI,
  ActionParameterDefinitions,
  ActionParameters,
  ActionSettingDefinitions,
  ActionSettings,
} from "@nasa-jpl/aerie-actions";
import figlet from "figlet";

// register inline figlet fonts to be included in the bundle
// typescript doesn't work correctly with these kinds of imports without some additional config,
// so "@ts-ignore" tells the typescript compiler to suppress errors on the next line
// @ts-ignore
import Roman from "figlet/importable-fonts/Roman.js";
// @ts-ignore
import Caligraphy from "figlet/importable-fonts/Caligraphy.js";
// @ts-ignore
import Colossal from "figlet/importable-fonts/Colossal.js";
figlet.parseFont("roman", Roman);
figlet.parseFont("caligraphy", Caligraphy);
figlet.parseFont("colossal", Colossal);

// Define schemas for your action's settings and parameters
export const parameterDefinitions = {
  inputFile: { type: "string" },
  font: { type: "string" },
} satisfies ActionParameterDefinitions;

export const settingDefinitions = {
  writeFile: { type: "boolean" },
} satisfies ActionSettingDefinitions;

// generate the correct typescript types from the schemas
type MyActionParameters = ActionParameters<typeof parameterDefinitions>;
type MyActionSettings = ActionSettings<typeof settingDefinitions>;

export async function main(actionParameters: MyActionParameters, settings: MyActionSettings, actions: ActionsAPI) {
  // read input from a sequence provided by 'inputFile' parameter
  if (!actionParameters.inputFile) {
    throw new Error("Input file is required");
  }
  const inputSequence = await actions.readSequence(actionParameters.inputFile);
  const inputStr = inputSequence.definition || "";

  console.log(`Generating art for "${inputStr}"...`);
  let artStr: string;
  const options: figlet.Options = { font: (actionParameters.font as figlet.Fonts) || "roman" };
  artStr = figlet.textSync(inputStr, options);
  console.log(artStr);

  // make a unique file name
  const timeStr = new Date().toISOString().replace(/[-.:]/g, "");
  const outFileName = `figlet-${timeStr}`;

  // write the ascii art string to the output file
  if (settings.writeFile) {
    await actions.writeSequence(outFileName, artStr);
  }

  return {
    status: "SUCCESS",
    data: {
      outFileName,
      output: artStr,
    },
  };
}
