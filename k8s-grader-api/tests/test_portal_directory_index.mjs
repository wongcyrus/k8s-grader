import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const template = readFileSync(new URL("../template.yaml", import.meta.url), "utf8");
const code = template.match(
  /  PortalDirectoryIndexFunction:[\s\S]*?      FunctionCode: \|\n([\s\S]*?)(?=\n  [A-Za-z])/,
)?.[1];
assert.ok(code, "CloudFront directory-index function is missing");
const handler = vm.runInNewContext(`${code}\nhandler`);

test("private REST origin preserves root and nested directory index pages", () => {
  for (const uri of ["/", "/game/", "/doom/", "/hkzero/", "/game/nested/"]) {
    const request = { uri, querystring: {} };
    assert.equal(handler({ request }), request);
    assert.equal(request.uri, `${uri}index.html`);
  }
});

test("bare game directories redirect to slash URLs without losing launch parameters", () => {
  for (const uri of ["/game", "/doom", "/hkzero"]) {
    const response = handler({
      request: {
        uri,
        querystring: {
          token: { value: "encoded%2Btoken%3D" },
          task: { value: "one", multiValue: [{ value: "one" }, { value: "two" }] },
        },
      },
    });
    assert.equal(response.statusCode, 301);
    assert.equal(
      response.headers.location.value,
      `${uri}/?token=encoded%2Btoken%3D&task=one&task=two`,
    );
  }
});

test("bare game redirects without query parameters do not add a question mark", () => {
  assert.equal(handler({ request: { uri: "/doom", querystring: {} } }).headers.location.value, "/doom/");
});

test("explicit pages, assets, and unrelated extensionless URLs remain unchanged", () => {
  for (const uri of ["/teacher.html", "/exam.js", "/hkzero/assets/app.js", "/game/index.html", "/gameboard"]) {
    const request = { uri, querystring: { value: { value: "unchanged" } } };
    assert.equal(handler({ request }), request);
    assert.equal(request.uri, uri);
    assert.equal(request.querystring.value.value, "unchanged");
  }
});
