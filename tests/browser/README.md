# Dashboard browser acceptance

Development tooling only: Node plus `playwright-core@1.62.1` and a compatible
installed Chromium. No browser dependency, CDN or Node server is shipped in the
Facet image. This bounded script exercises the actual bundled page from a
loopback test server; only the five aggregate API responses are intercepted.
It never opens an OAuth flow or touches Gmail/config/state. Negative malformed
fixtures test failure handling, not permissible production DTO output.

Start an isolated `facet web --port 18084` using the candidate package or publish
an isolated, non-root candidate container's web port to `127.0.0.1:18084`.
Do not use the real sync service as the test server. Run:

```sh
FACET_DASHBOARD_TEST_URL=http://127.0.0.1:18084/ \
FACET_BROWSER_EXECUTABLE=/absolute/path/to/chromium \
NODE_PATH=/absolute/path/to/development/node_modules \
node tests/browser/dashboard.cjs
```

`NODE_PATH` is optional when the development module is already discoverable.
The executable override is optional for Playwright's installed Chromium.
Optional `FACET_BROWSER_SCREENSHOT_DIR` writes only synthetic desktop/mobile
screenshots to an existing private local directory. Viewports are not a claim of
physical iOS/Android acceptance. Production backend sentinel/output tests remain
the HTTP privacy boundary; DOM filtering does not replace those tests.
