import {
  ActionsAPI,
  ActionParameterDefinitions,
  ActionSettingDefinitions,
  ActionParameters,
  ActionSettings,
} from "@nasa-jpl/plandev-actions";
import { RefreshResponse } from "./models/refresh.js";

export const parameterDefinitions = {
  sequenceName: { type: "string" },
} satisfies ActionParameterDefinitions;

export const settingDefinitions = {
  refreshUrl: { type: "string" },
} satisfies ActionSettingDefinitions;

const sequenceNameError =
  "Fresh cannot be invoked without providing a valid sequence name.";

// generate the correct typescript types from the schemas
type MyActionParameters = ActionParameters<typeof parameterDefinitions>;
type MyActionSettings = ActionSettings<typeof settingDefinitions>;

export async function main(
  parameters: MyActionParameters,
  settings: MyActionSettings,
  actionsAPI: ActionsAPI,
) {
  if (
    parameters.sequenceName === undefined ||
    parameters.sequenceName === null
  ) {
    throw new Error(sequenceNameError);
  }

  let sequenceJson: unknown;

  try {
    const sequenceContents = await actionsAPI.readFile(parameters.sequenceName);
    sequenceJson = JSON.parse(sequenceContents);
  } catch (error) {
    throw new Error(
      `Sequence file "${parameters.sequenceName}" does not contain valid SeqJSON.`,
      { cause: error },
    );
  }

  const parcel = await actionsAPI.readParcel();

  const commandDictionary = await actionsAPI.readCommandDictionary(
    parcel.command_dictionary_id,
  );
  const commandDictionaryFile = await actionsAPI.readDictionaryFile(
    commandDictionary.dictionary_file_path,
  );

  const result = await fetch(settings.refreshUrl, {
    body: JSON.stringify({
      sequence: sequenceJson,
      command_dictionary: commandDictionaryFile,
    }),
    method: "post",
    headers: {
      "Content-Type": "application/json",
    },
  });

  // `fetch` only rejects on network failure -- an HTTP 4xx/5xx resolves normally,
  // so a non-ok response has to be turned into an error explicitly. Without this
  // check the action would report SUCCESS for a rejected or failed evaluation.
  if (!result.ok) {
    const body = await result.text().catch(() => "<unreadable response body>");
    throw new Error(
      `Refresh service at ${settings.refreshUrl} returned HTTP ${result.status} ${result.statusText}: ${body}`,
    );
  }

  const refreshResponse = (await result.json()) as RefreshResponse;

  return {
    status: "SUCCESS",
    data: refreshResponse,
  };
}
