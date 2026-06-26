/**
 * The client is auth-agnostic: it sends no credentials (no login call, no Authorization
 * or x-hasura-role header) — the deployment's proxy attaches auth. It surfaces upstream
 * failures (e.g. a proxy auth error) rather than swallowing them.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PlandevApi } from '../src/plandev-api';

afterEach(() => vi.unstubAllGlobals());

function stubFetch(handler: (url: string) => Response): { url: string; init: RequestInit }[] {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ init, url: String(url) });
      return handler(String(url));
    }),
  );
  return calls;
}

describe('PlandevApi (auth-agnostic)', () => {
  it('sends no credentials — no login call, no Authorization/role header', async () => {
    const calls = stubFetch(() => new Response(JSON.stringify({ data: { plan: [] } }), { status: 200 }));
    const api = new PlandevApi({ graphqlUrl: '/api/graphql' });
    await api.getPlans();

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('graphql');
    expect(calls.some(c => c.url.includes('login'))).toBe(false);
    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(headers['x-hasura-role']).toBeUndefined();
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('surfaces an upstream error (e.g. a proxy auth failure) instead of swallowing it', async () => {
    stubFetch(() => new Response('forbidden', { status: 403 }));
    const api = new PlandevApi({ graphqlUrl: '/api/graphql' });
    await expect(api.getPlans()).rejects.toThrow(/failed \(403\)/);
  });
});
