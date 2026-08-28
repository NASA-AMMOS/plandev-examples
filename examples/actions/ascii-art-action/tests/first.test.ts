import { describe, it, test, mock } from "node:test";
import { ActionsAPI } from "@nasa-jpl/plandev-actions";

import { main } from "../src/index.js";

const mockActionsAPI = {
  workspaceId: 1,
  readFile: async () => "test",
  writeFile: async () => ({ success: true as const }),
} as unknown as ActionsAPI;

test("plandev figlet action", async (t) => {
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
