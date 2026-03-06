import { describe, it, test, mock } from "node:test";
import { ActionsAPI } from "@nasa-jpl/aerie-actions";

import { main } from "../src/index.js";

const mockActionsAPI = {
  workspaceId: 1,
  listSequences: async () => {},
  readSequence: async () => {
    console.log("got mocked");
    return { definition: "test" };
  },
  writeSequence: async () => {},
} as unknown as ActionsAPI;

test("aerie figlet action", async (t) => {
  await t.test("runs main", async () => {
    await main(
      {
        inputFile: "figlet-input",
        font: "roman",
      },
      {
        writeFile: true,
      },
      mockActionsAPI,
    );
  });
});
