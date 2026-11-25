/**
 * Browser verification of the FYP-I workflow: features, requirements, SRS, architecture,
 * domain model, UML diagrams and traceability, with approval gates and visual rendering.
 *
 * Drives the real frontend in headless Chrome against a backend that runs the real app on a
 * throw-away database with a scripted language model (backend: `python -m tests.e2e.server`).
 *
 *   API_URL=http://localhost:8001 UI_URL=http://localhost:5174 npm run verify:ui
 *
 * Exits non-zero if any check fails.
 */
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const API = process.env.API_URL ?? "http://localhost:8001";
const UI = process.env.UI_URL ?? "http://localhost:5174";
const CHROME = process.env.CHROME_PATH ?? "/usr/bin/google-chrome";
const SHOTS = process.env.SHOTS_DIR ?? "/tmp/ui-shots";
fs.mkdirSync(SHOTS, { recursive: true });

let failures = 0;
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
}

async function api(path, init) {
  const r = await fetch(`${API}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  return { status: r.status, body: await r.json().catch(() => null) };
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--window-size=1400,1800"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1400, height: 1800 });
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error" && !m.text().includes("favicon")) consoleErrors.push(m.text());
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const text = () => page.evaluate(() => document.body.innerText);
async function waitText(needle, timeout = 20000) {
  await page.waitForFunction((n) => document.body.innerText.includes(n), { timeout }, needle);
}
async function clickButton(label, { exact = false, within = "body" } = {}) {
  const ok = await page.evaluate(
    (l, ex, scope) => {
      const root = document.querySelector(scope) ?? document.body;
      const b = [...root.querySelectorAll("button, a")].find((x) => {
        const t = x.textContent.trim();
        return ex ? t === l : t.includes(l);
      });
      if (!b || b.disabled) return false;
      b.click();
      return true;
    },
    label,
    exact,
    within,
  );
  if (!ok) throw new Error(`button not found or disabled: ${label}`);
}
async function isDisabled(selector) {
  return page.$eval(selector, (b) => b.disabled);
}
const stageStatus = (key) =>
  page.$eval(`[data-stage="${key}"]`, (li) => li.getAttribute("data-status"));
const path = () => new URL(page.url()).pathname;
async function shot(name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}
async function goto(p) {
  await page.goto(`${UI}${p}`, { waitUntil: "networkidle0" });
}

try {
  // ---- project with extracted, unreviewed features ---------------------------------------
  const project = (await api("/projects", { method: "POST", body: JSON.stringify({ name: "Verify", description: "A reporting app" }) })).body;
  const pid = project.id;
  await api(`/projects/${pid}/extract`, { method: "POST" });

  await goto(`/projects/${pid}`);
  await page.waitForSelector('[data-testid="feature-gate"]');
  const steps = await page.$$eval(".wf-step[data-stage]", (els) =>
    els.map((e) => e.getAttribute("data-stage")),
  );
  check("workflow progress shows the five stages in order", steps.join() === "FEATURES,REQUIREMENTS,SRS,ARCHITECTURE,UML", steps.join());
  check("no code generation or database stage is offered", !/code generation|database design|sandbox|docker/i.test(await text()));
  check("features stage is PENDING_REVIEW", (await stageStatus("FEATURES")) === "PENDING_REVIEW");
  check("requirements stage is locked (BLOCKED)", (await stageStatus("REQUIREMENTS")) === "BLOCKED");
  check("total / pending counts are shown",
    (await page.$eval('[data-testid="count-total"]', (e) => e.textContent)) === "3" &&
      (await page.$eval('[data-testid="count-pending"]', (e) => e.textContent)) === "3");
  check("Move to Requirements is disabled with a reason",
    (await isDisabled('[data-testid="move-to-requirements"]')) &&
      (await text()).includes("still pending review"));
  check("locked stage is not a link",
    (await page.$('[data-stage="REQUIREMENTS"] a')) === null);
  await shot("01-workspace-pending");

  // ---- direct URL cannot bypass the gate --------------------------------------------------
  await goto(`/projects/${pid}/requirements`);
  await waitText("Feature approval required");
  check("requirements URL shows 'Feature approval required' + Back to Features",
    (await text()).includes("Back to Features"));
  check("no generator is offered on the blocked page", !(await text()).includes("Generate\n"));
  const direct = await api(`/projects/${pid}/artifacts/generate`, { method: "POST", body: JSON.stringify({ type: "REQUIREMENTS" }) });
  check("API refuses the same bypass with a structured 409",
    direct.status === 409 && direct.body.detail.blocked === true && !!direct.body.detail.required_stage,
    JSON.stringify(direct.body));
  await shot("02-requirements-blocked");
  await clickButton("Back to Features");
  await page.waitForSelector('[data-testid="feature-gate"]');
  check("Back to Features returns to the workspace", path() === `/projects/${pid}`);

  // ---- review features, then Move to Requirements ---------------------------------------
  await clickButton("Approve", { exact: true });
  await sleep(600);
  await clickButton("Approve", { exact: true });
  await sleep(600);
  check("still blocked while one feature is pending",
    await isDisabled('[data-testid="move-to-requirements"]'));
  await clickButton("Reject", { exact: true });
  await page.waitForFunction(
    () => document.querySelector('[data-testid="count-pending"]')?.textContent === "0",
    { timeout: 10000 },
  );
  check("counts update: 2 approved, 1 rejected",
    (await page.$eval('[data-testid="count-approved"]', (e) => e.textContent)) === "2" &&
      (await page.$eval('[data-testid="count-rejected"]', (e) => e.textContent)) === "1");
  check("features stage becomes APPROVED", (await stageStatus("FEATURES")) === "APPROVED");
  await shot("03-workspace-ready");
  await clickButton("Move to Requirements");
  await page.waitForFunction(() => location.pathname.endsWith("/requirements"), { timeout: 10000 });
  check("Move to Requirements navigates to the requirements page", path().endsWith("/requirements"));

  // ---- requirements --------------------------------------------------------------------------
  await waitText("No requirements yet");
  check("next-stage button is disabled before generation with a reason",
    (await isDisabled('[data-testid="next-stage-button"]')) &&
      (await page.$eval('[data-testid="next-stage-reason"]', (e) => e.textContent)).includes("Generate first"));
  await clickButton("Generate", { exact: true });
  await page.waitForSelector('[data-testid="fr-table"]', { timeout: 20000 });
  const ids = await page.$$eval('[data-testid="fr-table"] tbody code, [data-testid="nfr-table"] tbody code', (e) => e.map((x) => x.textContent));
  check("FR-/NFR- ids are shown in separate tables", ids.join() === "FR-001,FR-002,NFR-001", ids.join());
  check("functional table shows actor and expected behavior columns",
    (await text()).includes("Actor") && (await text()).includes("Expected behavior"));
  check("requirements are NOT auto-approved", (await stageStatus("REQUIREMENTS")) === "PENDING_REVIEW");
  check("next-stage button names the action",
    (await page.$eval('[data-testid="next-stage-button"]', (b) => b.textContent)) === "Approve Requirements and Continue to SRS");
  await shot("04-requirements");
  await clickButton("Approve Requirements and Continue to SRS");
  await page.waitForFunction(() => location.pathname.endsWith("/srs"), { timeout: 15000 });
  check("approve-and-continue navigates to SRS only after approval", path().endsWith("/srs"));
  await page.waitForSelector('[data-stage="REQUIREMENTS"]');
  check("progress updates immediately (requirements APPROVED)", (await stageStatus("REQUIREMENTS")) === "APPROVED");

  // ---- SRS gate for architecture ------------------------------------------------------------
  await goto(`/projects/${pid}/architecture`);
  await waitText("SRS approval required");
  check("architecture page blocked until SRS is approved", (await text()).includes("Back to SRS"));
  await clickButton("Back to SRS");
  await page.waitForFunction(() => location.pathname.endsWith("/srs"), { timeout: 10000 });
  await waitText("No srs yet");
  await clickButton("Generate", { exact: true });
  await waitText("Purpose");
  await clickButton("Approve SRS and Continue to Architecture");
  await page.waitForFunction(() => location.pathname.endsWith("/architecture"), { timeout: 15000 });
  await waitText("No architecture yet");
  await clickButton("Generate", { exact: true });
  await waitText("CMP-001");
  await clickButton("Approve Architecture and Continue to UML");
  await page.waitForFunction(() => location.pathname.endsWith("/uml"), { timeout: 15000 });
  check("SRS then architecture approved in order, arriving at UML", path().endsWith("/uml"));

  // ---- UML ------------------------------------------------------------------------------------
  await waitText("Domain Model");
  const tabs = await page.$$eval('[role="tab"]', (e) => e.map((x) => x.textContent.trim()));
  check("UML page has Domain Model, Class Diagram and Sequence Diagrams tabs",
    tabs.some((t) => t.startsWith("Domain Model")) && tabs.some((t) => t.startsWith("Class Diagram")) && tabs.some((t) => t.startsWith("Sequence Diagrams")), tabs.join("|"));
  await clickButton("Class Diagram", { within: '[role="tablist"]' });
  await waitText("Domain model approval required");
  check("class diagram blocked until the domain model is approved", (await text()).includes("Back to Domain Model"));
  await clickButton("Back to Domain Model");
  await waitText("No domain model yet");
  await clickButton("Generate", { exact: true });
  await page.waitForSelector('[data-testid="diagram-visual"] img', { timeout: 30000 });
  await page.waitForFunction(() => {
    const i = document.querySelector('[data-testid="diagram-visual"] img');
    return i && i.complete && i.naturalWidth > 0;
  }, { timeout: 30000 });
  const natural = await page.$eval('[data-testid="diagram-visual"] img', (i) => [i.naturalWidth, i.naturalHeight]);
  check("domain model is rendered as an image by default", natural[0] > 50 && natural[1] > 50, natural.join("x"));
  check("PlantUML source is not shown by default", (await page.$('[data-testid="diagram-source"]')) === null);
  check("domain entities, relationships and rules are listed",
    (await page.$('[data-testid="dm-entities"]')) !== null && (await text()).includes("A report always has exactly one author"));
  await shot("05-domain-model");

  const zoom0 = await page.$eval('[data-testid="diagram-zoom"]', (e) => e.textContent);
  await clickButton("+", { exact: true });
  const zoom1 = await page.$eval('[data-testid="diagram-zoom"]', (e) => e.textContent);
  check("zoom in changes the zoom level", zoom0 !== zoom1, `${zoom0} -> ${zoom1}`);
  await clickButton("Reset zoom");
  check("reset zoom returns to 100%", (await page.$eval('[data-testid="diagram-zoom"]', (e) => e.textContent)) === "100%");
  await clickButton("Fit to screen");
  check("fit to screen sets a computed zoom", (await page.$eval('[data-testid="diagram-zoom"]', (e) => e.textContent)) !== "100%");
  // pan by dragging
  const before = await page.$eval('[data-testid="diagram-visual"] img', (i) => i.style.transform);
  const box = await (await page.$('[data-testid="diagram-visual"]')).boundingBox();
  await page.mouse.move(box.x + 100, box.y + 100);
  await page.mouse.down();
  await page.mouse.move(box.x + 160, box.y + 140, { steps: 4 });
  await page.mouse.up();
  const after = await page.$eval('[data-testid="diagram-visual"] img', (i) => i.style.transform);
  check("dragging pans the diagram", before !== after);
  // wheel zoom
  const zoomBeforeWheel = await page.$eval('[data-testid="diagram-zoom"]', (e) => e.textContent);
  await page.mouse.move(box.x + 200, box.y + 200);
  await page.mouse.wheel({ deltaY: -300 });
  await sleep(300);
  const zoomAfterWheel = await page.$eval('[data-testid="diagram-zoom"]', (e) => e.textContent);
  check("mouse wheel zooms", zoomBeforeWheel !== zoomAfterWheel, `${zoomBeforeWheel} -> ${zoomAfterWheel}`);

  await clickButton("View PlantUML Source");
  await page.waitForSelector('[data-testid="diagram-source"]');
  const src = await page.$eval('[data-testid="diagram-source"]', (e) => e.textContent);
  check("source view shows PlantUML", src.includes("@startuml") && src.includes("class AppUser"));
  await clickButton("View diagram");
  await page.waitForSelector('[data-testid="diagram-visual"] img');
  check("toggling back shows the diagram again", true);

  // edit source: invalid source keeps the previous preview, shows the error, keeps the source
  await clickButton("Edit source");
  await page.waitForSelector('textarea[aria-label="PlantUML source"]');
  await page.$eval('textarea[aria-label="PlantUML source"]', (t) => { t.focus(); t.select(); });
  await page.keyboard.type("@startuml\nclass Broken {\n@enduml");
  await page.waitForSelector('[data-testid="diagram-error"]', { timeout: 15000 });
  check("invalid source shows an error while the last good preview stays",
    (await page.$('[data-testid="diagram-visual"] img')) !== null &&
      (await page.$eval('[data-testid="diagram-error"]', (e) => e.textContent)).includes("could not be rendered"));
  await shot("06-edit-invalid-source");
  await clickButton("Cancel");
  await sleep(500);
  check("cancelling keeps the original diagram without error", (await page.$('[data-testid="diagram-error"]')) === null);

  // valid edit saved as a new version
  await clickButton("Edit source");
  await page.waitForSelector('textarea[aria-label="PlantUML source"]');
  const current = await page.$eval('textarea[aria-label="PlantUML source"]', (t) => t.value);
  await page.$eval('textarea[aria-label="PlantUML source"]', (t) => { t.focus(); t.select(); });
  await page.keyboard.type(current.replace("@enduml", "note right of Report : edited in UI\n@enduml"));
  await sleep(1500);
  await clickButton("Save as new version");
  await waitText("saved as a new version", 15000).catch(() => waitText("Source saved"));
  const dmArt = (await api(`/projects/${pid}/artifacts?type=DOMAIN_MODEL`)).body.artifacts[0];
  check("source edit created a new artifact version and kept history",
    dmArt.current_version === 2 && dmArt.content.diagrams[0].plantuml.includes("edited in UI") && dmArt.status === "PENDING_REVIEW",
    `v${dmArt.current_version} ${dmArt.status}`);

  await clickButton("Approve", { exact: true });
  await waitText("Approved. It can now be used");
  await clickButton("Class Diagram", { within: '[role="tablist"]' });
  await waitText("No class diagram yet");
  await clickButton("Generate", { exact: true });
  await page.waitForSelector('[data-testid="diagram-visual"] img', { timeout: 30000 });
  await clickButton("Sequence Diagrams", { within: '[role="tablist"]' });
  await waitText("No sequence diagrams yet");
  await clickButton("Generate", { exact: true });
  await page.waitForSelector('[data-testid="diagram-visual"] img', { timeout: 30000 });
  check("class and sequence diagrams render visually", true);
  await shot("07-sequence");
  check("UML next-stage button label",
    (await page.$eval('[data-testid="next-stage-button"]', (b) => b.textContent)) === "Approve UML and Complete Design");
  await shot("07b-traceability");
  check("traceability panel lists requirement, component and domain entity links",
    (await text()).includes("DOMAIN_ENTITY") && (await text()).includes("IMPLEMENTS") && (await text()).includes("DERIVED_FROM"));
  await clickButton("Check cross-artifact consistency");
  await waitText("Deterministic validation");
  check("cross-artifact consistency check runs", true);
  await clickButton("Approve UML and Complete Design");
  await page.waitForFunction(() => location.pathname.split("/").length === 3, { timeout: 20000 });
  await page.waitForSelector('[data-stage="UML"]');
  const all = await Promise.all(["FEATURES", "REQUIREMENTS", "SRS", "ARCHITECTURE", "UML"].map(stageStatus));
  check("all five stages are APPROVED after completing the design", all.every((s) => s === "APPROVED"), all.join());
  await shot("08-complete");

  // ---- invalidation -----------------------------------------------------------------------
  const srs = (await api(`/projects/${pid}/artifacts?type=SRS`)).body.artifacts[0];
  await api(`/artifacts/${srs.id}`, { method: "PUT", body: JSON.stringify({ content: srs.content }) });
  await goto(`/projects/${pid}`);
  await page.waitForSelector('[data-stage="ARCHITECTURE"]');
  check("editing SRS marks architecture as REQUIRES_REVIEW",
    (await stageStatus("ARCHITECTURE")) === "REQUIRES_REVIEW" && (await stageStatus("SRS")) === "PENDING_REVIEW");
  await goto(`/projects/${pid}/architecture`);
  await waitText("SRS approval required");
  check("downstream page is blocked and says why", (await text()).includes("Back to SRS"));
  await shot("09-requires-review");

  // ---- a fresh project: later stages are blocked ------------------------------------
  const p2 = (await api("/projects", { method: "POST", body: JSON.stringify({ name: "Second", description: "x" }) })).body.id;
  await goto(`/projects/${p2}/uml`);
  await waitText("Architecture approval required");
  check("UML page blocked until architecture is approved", (await text()).includes("Back to Architecture"));
  await goto(`/projects/${p2}/srs`);
  await waitText("Requirements approval required");
  check("SRS page blocked until requirements are approved", (await text()).includes("Back to Requirements"));
} catch (e) {
  check("script completed without an exception", false, String(e?.stack ?? e));
  await shot("zz-failure").catch(() => {});
} finally {
  const relevant = consoleErrors.filter((m) => !/409|Failed to load resource/.test(m));
  check("no uncaught page errors", relevant.length === 0, relevant.slice(0, 3).join(" | "));
  await browser.close();
}
console.log(`\n${results.filter((r) => r.ok).length} passed, ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
