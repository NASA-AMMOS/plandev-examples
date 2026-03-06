import { main } from "../src/index";

import assert from 'node:assert';
import { test, mock } from "node:test";
import type {ActionsAPI, ReadSequenceResult} from "@nasa-jpl/aerie-actions";

// The basic-action example makes a `fetch` call to an external URL when it runs.
// This test avoids relying on making an actual call to an external URL by "mocking"
// the `fetch` API and replacing it with our own test function.

// create a mock Response-like object
function createMockResponse(data) {
  return {
    ok: true,
    status: 200,
    json: async () => data,
    clone: function() {
      return createMockResponse(data);
    }
  };
}

// mock fetch that returns it
const mockFetch = mock.fn(async (url, options) => {
  console.log(`mock fetch called with url: ${url}`);
  return createMockResponse({ message: "mock response" });
});

// TS utility that lets us mock only selected parts of an object,
// while treating it as a fully-typed instance of the whole thing.
function createMock<T extends object>(overrides: Partial<{ [K in keyof T]: T[K] }>): T {
  return overrides as T;
}

// create a partial mock of the actions API, so we can test it without making real database calls
// TODO: extract createMockActionsAPI into aerie-actions TestUtils package
const mockActionsAPI = createMock<ActionsAPI>({
  listSequences: async () => {
    return [];
  },
  readSequence: async () => {
    console.log("called readSequence");
    return { id: 1, definition: "test" } as ReadSequenceResult;
  },
  writeSequence: async () => {},
});

test("aerie basic example action", async (t) => {
  t.mock.method(globalThis, 'fetch', mockFetch);

  await t.test("runs main", async () => {
    await main(
      {
        urlPath: "repos/NASA-AMMOS/aerie",
        myBool: false,
        sleepMs: 0,
      },
      {
        externalUrl: "https://api.github.com",
        retries: 0,
      },
      mockActionsAPI,
    );
    assert.equal(mockFetch.mock.calls.length, 1, "fetch should have been called once");
  });
});
