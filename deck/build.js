// Builds Data-Plumber-Hackathon.pptx:  node build.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");

const C = {
  bg: "0B0D14", panel: "151925", panel2: "1C2130", line: "2A3042",
  text: "EEF0F5", dim: "A3AABB", faint: "6B7285",
  violet: "8B7CFF", violet2: "B7ADFF", emerald: "34D399", amber: "F5B546", rose: "FB7185", sky: "60A5FA",
  violetFill: "221E3D", violetLine: "5B4FC0", emeraldLine: "2D6B55", roseFill: "2A1720", amberFill: "2A2215",
};
const HEAD = "Segoe UI";
const BODY = "Segoe UI";
const MONO = "Consolas";
const TOTAL = 6;

async function icon(name, color) {
  const svg = renderToStaticMarkup(React.createElement(lu[name], { color: "#" + color, size: 256 }));
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}

function text(slide, value, x, y, w, h, opts = {}) {
  slide.addText(value, { x, y, w, h, margin: 0, fontFace: BODY, fontSize: 14, color: C.text, valign: "top", isTextBox: true, ...opts });
}

function card(slide, x, y, w, h, fill = C.panel, line = C.line) {
  slide.addShape("roundRect", { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: line, width: 0.75 } });
}

async function tile(slide, x, y, s, iconName, color, fill = C.panel2) {
  slide.addShape("roundRect", { x, y, w: s, h: s, rectRadius: 0.1, fill: { color: fill }, line: { color: C.line, width: 0.75 } });
  const pad = s * 0.24;
  slide.addImage({ data: await icon(iconName, color), x: x + pad, y: y + pad, w: s - 2 * pad, h: s - 2 * pad });
}

function letterTile(slide, x, y, s, letter, color = C.violet2, fill = C.violetFill, line = C.violetLine) {
  slide.addShape("roundRect", { x, y, w: s, h: s, rectRadius: 0.08, fill: { color: fill }, line: { color: line, width: 0.75 } });
  text(slide, letter, x, y, s, s, { fontSize: 14, bold: true, color, align: "center", valign: "middle" });
}

function header(slide, kicker, title, n) {
  slide.background = { color: C.bg };
  text(slide, kicker, 0.7, 0.55, 11.9, 0.3, { fontSize: 11, bold: true, color: C.violet2, charSpacing: 3 });
  text(slide, title, 0.7, 0.85, 11.9, 0.75, { fontFace: HEAD, fontSize: 32, bold: true });
  text(slide, `${n} / ${TOTAL}`, 11.63, 7.0, 1.0, 0.25, { fontSize: 10, color: C.faint, align: "right" });
}

function chip(slide, x, y, w, label, color, mono = false) {
  slide.addShape("roundRect", { x, y, w, h: 0.44, rectRadius: 0.22, fill: { color: C.panel }, line: { color, width: 1 } });
  text(slide, label, x, y, w, 0.44, { fontSize: 13, bold: true, color, align: "center", valign: "middle", fontFace: mono ? MONO : BODY });
}

function arrow(slide, x1, y1, x2, y2, color = C.faint) {
  slide.addShape("line", { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color, width: 1.5, endArrowType: "triangle" } });
}

// ---------------------------------------------------------------- slide 1: title
async function slideTitle(pres) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  text(s, "SOLANA HACKATHON  ·  AGENT INFRASTRUCTURE ON PAY.SH", 0.7, 0.95, 7.2, 0.3, { fontSize: 12, bold: true, color: C.violet2, charSpacing: 3 });
  text(s, "Data Plumber", 0.7, 1.35, 7.2, 1.1, { fontFace: HEAD, fontSize: 60, bold: true });
  text(s, "The reliable step between tools in an agent workflow.", 0.7, 2.6, 6.9, 0.9, { fontSize: 24, color: C.dim });
  text(s, "Send any payload and the JSON Schema you need. Get back valid data, with every value grounded in the source or explicitly flagged.",
    0.7, 3.65, 6.6, 1.0, { fontSize: 16, color: C.text, lineSpacingMultiple: 1.15 });
  chip(s, 0.7, 4.95, 2.15, "POST /v1/adapt", C.violet2, true);
  chip(s, 3.03, 4.95, 2.65, "$0.02 / call via Pay.sh", C.amber);
  chip(s, 5.86, 4.95, 2.0, "JSON · CSV · text", C.emerald);
  text(s, "github.com/sudhersankv/data-plumber", 0.7, 6.75, 6, 0.3, { fontSize: 12, color: C.faint, fontFace: MONO });

  card(s, 8.3, 0.95, 4.33, 5.6);
  const rows = [
    ["LuBot", C.text, "Agent", "fetches data, pays, decides"],
    ["LuWallet", C.amber, "Pay.sh gateway", "402 → pay $0.02 → forward"],
    ["LuWorkflow", C.violet2, "Data Plumber", "reshape · validate · flag"],
    ["LuSparkles", C.emerald, "Fireworks LLM", "meaning only, never the math"],
  ];
  for (let i = 0; i < rows.length; i++) {
    const [ic, col, name, role] = rows[i];
    const y = 1.35 + i * 1.3;
    await tile(s, 8.7, y, 0.72, ic, col);
    text(s, name, 9.7, y + 0.04, 2.8, 0.35, { fontSize: 16, bold: true });
    text(s, role, 9.7, y + 0.4, 2.8, 0.3, { fontSize: 12, color: C.dim });
    if (i < rows.length - 1) arrow(s, 9.06, y + 0.78, 9.06, y + 1.24, C.faint);
  }
  s.addNotes(
    "Agents rarely fail at reasoning; they fail at the seams between tools. Data Plumber is one paid API endpoint that fixes those seams: " +
      "send any payload plus the JSON Schema the next step needs, and get back valid data. Agents pay for it themselves, two cents per call, through Pay.sh."
  );
}

// ---------------------------------------------------------------- slide 2: problem
async function slideProblem(pres) {
  const s = pres.addSlide();
  header(s, "THE PROBLEM", "Agents break at the seams between tools", 2);

  const steps = ["goal", "plan", "fetch × 5", "5 shapes → 1", "compare", "decide", "act"];
  const w = 1.45, gap = 0.29;
  steps.forEach((label, i) => {
    const x = 0.7 + i * (w + gap), seam = i === 3;
    s.addShape("roundRect", { x, y: 1.85, w, h: 0.5, rectRadius: 0.25, fill: { color: seam ? C.roseFill : C.panel }, line: { color: seam ? C.rose : C.line, width: seam ? 1.25 : 0.75 } });
    text(s, label, x, 1.85, w, 0.5, { fontSize: 13, bold: seam, color: seam ? C.rose : C.dim, align: "center", valign: "middle" });
    if (i < steps.length - 1) arrow(s, x + w + 0.04, 2.1, x + w + gap - 0.04, 2.1, C.faint);
  });

  card(s, 0.7, 2.75, 7.35, 3.95);
  text(s, "TASK: 8× H100 FOR 6 HOURS, US WEST. FIVE PROVIDERS ANSWER:", 1.0, 2.98, 6.9, 0.3, { fontSize: 11, bold: true, color: C.faint, charSpacing: 2 });
  const providers = [
    ["A", "usd_per_gpu_hour: 2.49", "clean, per GPU-hour", C.text],
    ["B", '"$19.92/hr" for 8xH100', "whole machine → ÷ 8", C.text],
    ["C", "503 → \"starting at $24.80/hr\"", "outage + a floor price", C.rose],
    ["D", "0.00082 USD/GPU-second", "per second → × 3600", C.text],
    ["E", "CSV: $3.10 per GPU / hour", "no GPU count, no billing", C.text],
  ];
  providers.forEach(([id, payload, trick, col], i) => {
    const y = 3.42 + i * 0.63;
    if (id === "C") letterTile(s, 1.0, y, 0.44, id, C.amber, C.amberFill, "7A5A22");
    else letterTile(s, 1.0, y, 0.44, id);
    text(s, payload, 1.62, y, 3.75, 0.44, { fontSize: 13, fontFace: MONO, color: col, valign: "middle" });
    text(s, trick, 5.45, y, 2.45, 0.44, { fontSize: 13, color: C.dim, valign: "middle" });
  });

  card(s, 8.3, 2.75, 4.33, 3.95);
  text(s, "IF THE PLANNER PLUMBS IT ITSELF", 8.6, 2.98, 3.9, 0.3, { fontSize: 11, bold: true, color: C.faint, charSpacing: 2 });
  const fails = [
    "Raw payloads bloat context; every later turn costs more",
    "Unit math slips (÷ 8, × 3600)",
    "Unknown fields become confident guesses",
    "\u201CStarting at\u201D silently becomes a price",
    "An outage forces a replan",
  ];
  const x = await icon("LuCircleX", C.rose);
  fails.forEach((f, i) => {
    const y = 3.42 + i * 0.63;
    s.addImage({ data: x, x: 8.6, y: y + 0.08, w: 0.28, h: 0.28 });
    text(s, f, 9.02, y, 3.4, 0.46, { fontSize: 13, color: C.text, valign: "middle" });
  });
  s.addNotes(
    "A long agent run is a chain of tool calls, and every handoff is a seam. Our demo task: book 8 H100s for 6 hours in US West. " +
      "Five providers answer five ways: per GPU-hour, per whole machine, per GPU-second, a CSV row, and C's API is down so all we have is scraped text that says 'starting at'. " +
      "If the expensive planner model does this plumbing itself, its context fills with raw payloads, the unit math slips, unknown fields get guessed, and 'starting at' quietly becomes a real price."
  );
}

// ---------------------------------------------------------------- slide 3: product
async function slideProduct(pres) {
  const s = pres.addSlide();
  header(s, "THE PRODUCT", "One call: what you got → what you need", 3);

  card(s, 0.7, 1.9, 6.1, 1.95);
  text(s, "REQUEST  ·  POST /v1/adapt", 1.0, 2.1, 5.5, 0.3, { fontSize: 11, bold: true, color: C.violet2, charSpacing: 2 });
  text(s,
    '{ "source": { "content_type": "text",\n' +
      '    "data": "H100 SXM, 8x80 GB, starting at $24.80/hr" },\n' +
      '  "target_schema": { …GpuOffer JSON Schema… },\n' +
      '  "instructions": "The provider name is C." }',
    1.0, 2.5, 5.6, 1.6, { fontSize: 12, fontFace: MONO, color: C.dim, lineSpacingMultiple: 1.2 });

  card(s, 0.7, 4.1, 6.1, 2.25);
  text(s, "RESPONSE  ·  200", 1.0, 4.3, 5.5, 0.3, { fontSize: 11, bold: true, color: C.emerald, charSpacing: 2 });
  text(s, [
      { text: '{ "data": { "gpu": "H100 SXM", "gpu_count": 8,\n', options: { color: C.dim } },
      { text: '    "price_per_gpu_hour_usd": 3.1,\n', options: { color: C.emerald, bold: true } },
      { text: '    "price_type": "starting_at" },\n', options: { color: C.dim } },
      { text: '  "valid": true,\n', options: { color: C.dim } },
      { text: '  "warnings": ["price is a lower bound, not a quote"] }', options: { color: C.amber } },
    ], 1.0, 4.7, 5.6, 1.85, { fontSize: 12, fontFace: MONO, lineSpacingMultiple: 1.2 });

  text(s, "WHERE IT PLUGS INTO A LONG AGENT RUN", 7.2, 1.95, 5.4, 0.3, { fontSize: 11, bold: true, color: C.faint, charSpacing: 2 });
  const uses = [
    ["LuMerge", C.violet2, "Fan-in", "Many sources, many shapes → one table the planner can compare."],
    ["LuRefreshCw", C.amber, "Recovery", "API down? Send the fallback text with the same schema. The run continues, no replanning."],
    ["LuPlug", C.emerald, "Handoff", "One tool's output must validate as the next tool's input."],
  ];
  for (let i = 0; i < uses.length; i++) {
    const [ic, col, name, desc] = uses[i];
    const y = 2.45 + i * 1.3;
    await tile(s, 7.2, y, 0.66, ic, col);
    text(s, name, 8.1, y - 0.02, 4.5, 0.36, { fontSize: 18, bold: true });
    text(s, desc, 8.1, y + 0.36, 4.5, 0.7, { fontSize: 13, color: C.dim, lineSpacingMultiple: 1.1 });
  }
  text(s, "Any payload · any schema · nothing GPU-specific", 7.2, 6.3, 5.4, 0.35, { fontSize: 15, italic: true, color: C.violet2 });
  s.addNotes(
    "The whole contract is one endpoint. You send the source payload, JSON, CSV or text, plus a target JSON Schema and optional instructions. " +
      "You get back data that validates, a valid flag, and warnings. Here C's scraped text becomes a clean row: 24.80 for 8 GPUs is 3.10 per GPU-hour, " +
      "and the 'starting at' meaning is kept as price_type plus a warning. It is used at three kinds of moments: fan-in, recovery, and handoff. Nothing in it is GPU-specific."
  );
}

// ---------------------------------------------------------------- slide 4: architecture
async function slideArchitecture(pres) {
  const s = pres.addSlide();
  header(s, "ARCHITECTURE", "Payment at the edge, math in code", 4);

  const nodes = [
    ["LuBot", C.text, "Agent", "Fetches data, pays with the\npay CLI, plans"],
    ["LuWallet", C.amber, "Pay.sh gateway", "402 challenge · verifies\nUSDC · forwards"],
    ["LuWorkflow", C.violet2, "Data Plumber", "The API: reshapes, validates.\nNo payment code."],
    ["LuSparkles", C.emerald, "Fireworks LLM", "Semantic mapping only,\nnever the math"],
  ];
  for (let i = 0; i < nodes.length; i++) {
    const [ic, col, name, role] = nodes[i];
    const x = 0.7 + i * 3.15;
    card(s, x, 1.85, 2.45, 1.55, C.panel, i === 2 ? C.violetLine : C.line);
    await tile(s, x + 0.2, 2.05, 0.5, ic, col);
    text(s, name, x + 0.85, 2.1, 1.55, 0.4, { fontSize: 14, bold: true, valign: "middle" });
    text(s, role, x + 0.2, 2.68, 2.15, 0.62, { fontSize: 11.5, color: C.dim });
    if (i < nodes.length - 1) {
      s.addShape("line", { x: x + 2.5, y: 2.62, w: 0.6, h: 0, line: { color: C.faint, width: 1.5, beginArrowType: "triangle", endArrowType: "triangle" } });
    }
  }
  text(s, [
      { text: "1 ", options: { bold: true, color: C.amber } }, { text: "unpaid call → 402, $0.02     ", options: { color: C.dim } },
      { text: "2 ", options: { bold: true, color: C.amber } }, { text: "pay settles USDC on Solana (sandbox)     ", options: { color: C.dim } },
      { text: "3 ", options: { bold: true, color: C.violet2 } }, { text: "gateway proxies to /v1/adapt     ", options: { color: C.dim } },
      { text: "4 ", options: { bold: true, color: C.emerald } }, { text: "{ data, valid, warnings }", options: { color: C.dim } },
    ], 0.7, 3.62, 11.9, 0.35, { fontSize: 12.5 });

  text(s, "INSIDE ONE /v1/adapt CALL", 0.7, 4.3, 5, 0.3, { fontSize: 11, bold: true, color: C.faint, charSpacing: 2 });
  s.addShape("ellipse", { x: 7.35, y: 4.36, w: 0.16, h: 0.16, fill: { color: C.violet }, line: { color: C.violet } });
  text(s, "model: what the data means", 7.58, 4.3, 2.4, 0.3, { fontSize: 12, color: C.dim });
  s.addShape("ellipse", { x: 10.0, y: 4.36, w: 0.16, h: 0.16, fill: { color: C.emerald }, line: { color: C.emerald } });
  text(s, "code: validity + exact math", 10.23, 4.3, 2.4, 0.3, { fontSize: 12, color: C.dim });

  const steps = [
    ["Parse", "JSON · CSV · text. Bad input → 422, no model call", false],
    ["Annotate", "Every number gets an id, e.g. q1 = $19.92/hr", false],
    ["LLM map", "Evidence + a formula per field, e.g. q1 / q2", true],
    ["Normalize", "Evaluate formulas exactly; reject ungrounded values", false],
    ["Validate", "JSON Schema check, one repair attempt", false],
    ["Respond", "data · valid · warnings, plus a per-field trace", false],
  ];
  steps.forEach(([name, cap, model], i) => {
    const x = 0.7 + i * 2.02;
    card(s, x, 4.75, 1.8, 1.75, model ? C.violetFill : C.panel, model ? C.violetLine : C.emeraldLine);
    text(s, String(i + 1), x + 0.18, 4.9, 0.5, 0.3, { fontSize: 12, bold: true, color: model ? C.violet2 : C.emerald });
    text(s, name, x + 0.18, 5.16, 1.5, 0.35, { fontSize: 15, bold: true });
    text(s, cap, x + 0.18, 5.55, 1.5, 0.9, { fontSize: 11, color: C.dim, lineSpacingMultiple: 1.05 });
    if (i < steps.length - 1) arrow(s, x + 1.83, 5.62, x + 1.99, 5.62, C.faint);
  });
  text(s, "The model decides what the data means. Code decides whether it's valid, and does the math.", 0.7, 6.72, 11.9, 0.35,
    { fontSize: 14, italic: true, color: C.violet2 });
  s.addNotes(
    "Four parts. The agent fetches data and pays. The Pay.sh gateway owns all payment: an unpaid call gets 402 with a two-cent challenge, " +
      "the pay client settles it in USDC on the Solana sandbox, and only then is the request forwarded. The Data Plumber API has no payment code at all; a test enforces that. " +
      "Inside one call: parse, give every number an id, let the model propose each field as evidence plus a formula over those ids, then code evaluates the formula exactly, " +
      "rejects anything not grounded in the source, validates against the schema, repairs once if needed, and responds with data, valid and warnings."
  );
}

// ---------------------------------------------------------------- slide 5: result
async function slideResult(pres) {
  const s = pres.addSlide();
  header(s, "LIVE DEMO RESULT", "5 providers, 1 outage, 1 plan, for 10 cents", 5);

  const hdr = (t, align = "left") => ({ text: t, options: { bold: true, color: C.faint, fontSize: 11, fill: { color: C.panel2 }, align } });
  const cell = (t, o = {}) => ({ text: t, options: { color: C.text, fill: { color: C.panel }, ...o } });
  const rows = [
    [hdr("PROVIDER"), hdr("$ / GPU-HR", "right"), hdr("8 GPUs × 6 h", "right"), hdr("STATUS")],
    [cell("A", { bold: true, color: C.emerald }), cell("2.49", { align: "right", color: C.emerald }), cell("$119.52", { align: "right", bold: true, color: C.emerald }), cell("✓ Pick · on-demand quote", { bold: true, color: C.emerald })],
    [cell("B", { bold: true }), cell("2.49", { align: "right" }), cell("$119.52", { align: "right" }), cell("Tie · more warnings", { color: C.dim })],
    [cell("D", { bold: true }), cell("2.952", { align: "right" }), cell("$141.70", { align: "right" }), cell("On-demand quote", { color: C.dim })],
    [cell("E", { bold: true }), cell("3.10", { align: "right" }), cell("$148.80", { align: "right" }), cell("Price type not stated", { color: C.dim })],
    [cell("C", { bold: true, color: C.faint }), cell("3.10", { align: "right", color: C.faint }), cell("$148.80", { align: "right", color: C.faint, strike: "sngStrike" }), cell("✕ Excluded: \u2018starting at\u2019 floor", { color: C.rose })],
  ];
  s.addTable(rows, {
    x: 0.7, y: 1.9, w: 7.6, colW: [1.25, 1.45, 1.75, 3.15], rowH: 0.52, fontFace: BODY, fontSize: 14, valign: "middle",
    margin: [0, 0.14, 0, 0.14], border: { type: "solid", color: C.bg, pt: 1.5 },
  });

  card(s, 0.7, 5.3, 7.6, 1.05, C.panel, C.emeraldLine);
  await tile(s, 0.95, 5.53, 0.58, "LuShieldCheck", C.emerald);
  text(s, [
      { text: "Honesty, enforced in code. ", options: { bold: true, color: C.text } },
      { text: "For provider E the model guessed gpu_count = 1 and price_type = on_demand. Neither is in the source, so both were rejected to null, with the reason in warnings.", options: { color: C.dim } },
    ], 1.75, 5.38, 6.35, 0.9, { fontSize: 13, lineSpacingMultiple: 1.1, valign: "middle" });

  const stats = [
    ["$119.52", C.emerald, "best plan: provider A,\n8× H100 for 6 hours"],
    ["$0.10", C.amber, "5 calls × $0.02, paid by the\nagent itself via Pay.sh"],
    ["0 replans", C.violet2, "C's API was down; its scraped text\nwent through the same schema"],
  ];
  stats.forEach(([big, col, label], i) => {
    const y = 1.9 + i * 1.52;
    card(s, 8.75, y, 3.88, 1.41);
    text(s, big, 9.05, y + 0.15, 3.4, 0.65, { fontSize: 34, bold: true, color: col });
    text(s, label, 9.05, y + 0.8, 3.4, 0.55, { fontSize: 12, color: C.dim });
  });
  s.addNotes(
    "This is the real output of the paid demo run. Five rows, one schema. The planner only does simple math on validated rows: price times 8 times 6. " +
      "A and B tie at 119.52 and A wins on fewer warnings. C is excluded because 'starting at' is a floor, not a quote. " +
      "For E, the model tried to invent a GPU count and a billing type; code rejected both. Five calls at two cents: ten cents total, paid by the agent through Pay.sh. " +
      "Now let me show it live."
  );
}

// ---------------------------------------------------------------- slide 6: why + close
async function slideWhy(pres) {
  const s = pres.addSlide();
  header(s, "WHY AN AGENT SHOULD CALL IT", "Spend intelligence on the goal, not on reformatting", 6);

  const items = [
    ["LuLayers", C.violet2, "Saves context", "The expensive planner only sees small, clean rows."],
    ["LuCalculator", C.emerald, "Exact math", "The model writes the formula; code computes it."],
    ["LuShieldCheck", C.emerald, "No invented values", "Grounded in the source, or null with a warning."],
    ["LuRefreshCw", C.amber, "Contained failures", "Fallback data flows through the same schema."],
    ["LuCoins", C.amber, "Predictable cost", "A flat $0.02 per payload, not premium tokens."],
    ["LuWallet", C.violet2, "No setup", "Agents pay per call via Pay.sh: no keys, no accounts."],
  ];
  for (let i = 0; i < items.length; i++) {
    const [ic, col, name, desc] = items[i];
    const x = 0.7 + (i % 3) * 4.05, y = 1.9 + Math.floor(i / 3) * 1.62;
    card(s, x, y, 3.83, 1.42);
    await tile(s, x + 0.25, y + 0.27, 0.6, ic, col);
    text(s, name, x + 1.07, y + 0.24, 2.6, 0.36, { fontSize: 16, bold: true });
    text(s, desc, x + 1.07, y + 0.62, 2.6, 0.65, { fontSize: 12.5, color: C.dim, lineSpacingMultiple: 1.05 });
  }

  card(s, 0.7, 5.3, 11.93, 1.2, C.panel2);
  text(s, "BUILT", 1.0, 5.52, 1.2, 0.3, { fontSize: 11, bold: true, color: C.emerald, charSpacing: 2 });
  text(s, "/v1/adapt · 109 tests + live Fireworks and gateway tests · Pay.sh sandbox 402 → 200 · live console · MCP tool adapt_data",
    2.2, 5.5, 10.2, 0.35, { fontSize: 13 });
  text(s, "NEXT", 1.0, 5.97, 1.2, 0.3, { fontSize: 11, bold: true, color: C.amber, charSpacing: 2 });
  text(s, "Public HTTPS + mainnet listing in the Pay.sh catalog · batch large tables in one call · cache repeated source formats",
    2.2, 5.95, 10.2, 0.35, { fontSize: 13 });
  text(s, "github.com/sudhersankv/data-plumber", 0.7, 6.98, 6, 0.28, { fontSize: 11, color: C.faint, fontFace: MONO });
  s.addNotes(
    "Why should an agent call this instead of plumbing itself? It keeps the expensive model's context clean, the math exact, and every value grounded or flagged. " +
      "Failures stay contained at one seam, the cost is a flat two cents per payload, and there is no setup: the agent pays per call through Pay.sh. " +
      "When not to use it: small, clean payloads that already match the target; plain code mapping is cheaper there. " +
      "Built and tested today on the Pay.sh sandbox; next is a public HTTPS deployment, a mainnet listing, and batching large tables."
  );
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = "Data Plumber";
  pres.author = "Data Plumber";
  await slideTitle(pres);
  await slideProblem(pres);
  await slideProduct(pres);
  await slideArchitecture(pres);
  await slideResult(pres);
  await slideWhy(pres);
  const out = path.join(__dirname, "Data-Plumber-Hackathon.pptx");
  await pres.writeFile({ fileName: out });
  console.log("wrote", out);
})();
