import { ActionsAPI, ActionParameterDefinitions, ActionSettingDefinitions, ActionParameters, ActionSettings } from "@nasa-jpl/aerie-actions";
import { RefreshResponse } from './models/refresh.js';

export const parameterDefinitions = {
  sequenceName: { type: 'string' }
} satisfies ActionParameterDefinitions;

export const settingDefinitions = {
  refreshUrl: { type: "string" },
} satisfies ActionSettingDefinitions;

const sequenceNameError = 'Fresh cannot be invoked without providing a valid sequence name.';

// generate the correct typescript types from the schemas
type MyActionParameters = ActionParameters<typeof parameterDefinitions>;
type MyActionSettings = ActionSettings<typeof settingDefinitions>;

export async function main(parameters: MyActionParameters, settings: MyActionSettings, actionsAPI: ActionsAPI) {
  if (parameters.sequenceName === undefined || parameters.sequenceName === null) {
    throw new Error(sequenceNameError);
  }

  const sequence = await actionsAPI.readSequence(parameters.sequenceName);

  if (sequence.seq_json === undefined || sequence.seq_json === null) {
    throw new Error(`Sequence: ${sequence.name} does not have any generated seqjson.`)
  }

  const parcel = await actionsAPI.readParcel(sequence.parcel_id);
  const commandDictionary = await actionsAPI.readCommandDictionary(parcel.command_dictionary_id);
  const commandDictionaryFile = await actionsAPI.readDictionaryFile(commandDictionary.dictionary_file_path);

  const result = await fetch(settings.refreshUrl, {
    body: JSON.stringify({
      'sequence': sequence.seq_json,
      'command_dictionary': commandDictionaryFile
    }),
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  const refreshResponse = await result.json() as RefreshResponse;

  return {
    status: "SUCCESS",
    data: refreshResponse,
  };
}
