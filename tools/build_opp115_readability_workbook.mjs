import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const auditPath = path.join(root, "data", "opp115", "experiment", "audits", "readability_compression_audit.json");
const csvPath = path.join(root, "data", "opp115", "experiment", "evaluations", "readability_compression.csv");
const outputDir = path.join(root, "outputs", "opp115_readability_review");
const previewDir = path.join(outputDir, "previews");

const audit = JSON.parse(await fs.readFile(auditPath, "utf8"));
const csvText = await fs.readFile(csvPath, "utf8");
await fs.mkdir(previewDir, { recursive: true });

const navy = "#173F6D";
const blue = "#DDEAF7";
const pale = "#F4F7FA";
const ink = "#172033";
const muted = "#64748B";
const green = "#147D64";
const border = "#CBD5E1";

const workbook = Workbook.create();
const overview = workbook.worksheets.add("Study Overview");
const conditions = workbook.worksheets.add("Condition Summary");
const policies = workbook.worksheets.add("Policy Summary");
const raw = workbook.worksheets.add("All Results");

// This experiment CSV contains only identifiers, booleans, and numeric values;
// therefore a line-safe parser preserves the flat scientific table exactly.
const csvLines = csvText.trim().split(/\r?\n/);
const rawHeaders = csvLines[0].split(",");
const rawRows = csvLines.slice(1).map((line) => line.split(",").map((value) => {
  if (value === "True") return true;
  if (value === "False") return false;
  if (value === "") return null;
  if (/^-?\d+(?:\.\d+)?$/.test(value)) return Number(value);
  return value;
}));
raw.getRangeByIndexes(0, 0, 1, rawHeaders.length).values = [rawHeaders];
raw.getRangeByIndexes(1, 0, rawRows.length, rawHeaders.length).values = rawRows;

for (const sheet of [overview, conditions, policies, raw]) {
  sheet.showGridLines = false;
}

function titleBand(sheet, range, title, subtitle) {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[title]];
  sheet.getRange(range).format = {
    fill: navy,
    font: { bold: true, color: "#FFFFFF", fontSize: 18 },
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 34;
  const subtitleRange = range.replace(/1/g, "2");
  sheet.getRange(subtitleRange).merge();
  sheet.getRange(subtitleRange).values = [[subtitle]];
  sheet.getRange(subtitleRange).format = {
    fill: "#EAF2FA",
    font: { color: muted, italic: true, fontSize: 10 },
    verticalAlignment: "center",
  };
  sheet.getRange(subtitleRange).format.rowHeight = 25;
}

function sectionHeader(range) {
  range.format = {
    fill: blue,
    font: { bold: true, color: navy },
    borders: { bottom: { style: "medium", color: navy } },
  };
}

function tableHeader(range) {
  range.format = {
    fill: navy,
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    verticalAlignment: "center",
    borders: { bottom: { style: "thin", color: border } },
  };
}

titleBand(
  overview,
  "A1:J1",
  "OPP-115 Extension: Readability, Length and Compression",
  "Verified review workbook for 486 frozen summaries generated from 27 privacy policies"
);

overview.getRange("A4:J4").merge();
overview.getRange("A4:J4").values = [["Evaluation completeness"]];
sectionHeader(overview.getRange("A4:J4"));

const cards = [
  ["A5:B5", "A6:B7", "Outputs evaluated", audit.rows],
  ["D5:E5", "D6:E7", "Policies", audit.policies],
  ["G5:H5", "G6:H7", "Model families", Object.keys(audit.models).length],
  ["I5:J5", "I6:J7", "Experimental conditions", audit.condition_summary.length],
];
for (const [labelRange, valueRange, label, value] of cards) {
  overview.getRange(labelRange).merge();
  overview.getRange(labelRange).values = [[label]];
  overview.getRange(labelRange).format = { fill: pale, font: { bold: true, color: muted }, horizontalAlignment: "center" };
  overview.getRange(valueRange).merge();
  overview.getRange(valueRange).values = [[value]];
  overview.getRange(valueRange).format = {
    fill: "#FFFFFF",
    font: { bold: true, color: navy, fontSize: 20 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: border },
  };
}

overview.getRange("A9:J9").merge();
overview.getRange("A9:J9").values = [["Metric interpretation"]];
sectionHeader(overview.getRange("A9:J9"));
overview.getRange("A10:C10").values = [["Metric", "Meaning", "Interpretation"]];
tableHeader(overview.getRange("A10:C10"));
overview.getRange("A11:C16").values = [
  ["Summary words", "Number of words in the generated summary", "Lower values indicate shorter summaries, not necessarily better summaries"],
  ["Flesch Reading Ease", "Formula-based reading-ease indicator", "Higher values indicate easier text under this formula"],
  ["Flesch-Kincaid Grade", "Estimated US school grade level", "Lower values indicate less complex wording and sentence structure"],
  ["SMOG Grade", "Estimated education level based on polysyllabic words", "Lower values indicate simpler vocabulary"],
  ["Word compression ratio", "Summary words divided by source-policy words", "Lower values indicate stronger compression"],
  ["Character compression ratio", "Summary characters divided by source-policy characters", "A second measure of compression that is less sensitive to tokenisation"],
];
overview.getRange("A11:C16").format = {
  wrapText: true,
  verticalAlignment: "top",
  borders: { insideHorizontal: { style: "thin", color: border } },
};
overview.getRange("A18:J18").merge();
overview.getRange("A18:J18").values = [["Quality-control findings"]];
sectionHeader(overview.getRange("A18:J18"));
overview.getRange("A19:B24").values = [
  ["Audit status", audit.valid ? "VALID" : "CHECK REQUIRED"],
  ["Unique conditions", `${audit.unique_conditions} / 486`],
  ["Missing metric values", Object.values(audit.missing_numeric_values).reduce((a, b) => a + b, 0)],
  ["Duplicate conditions", audit.duplicates.length],
  ["Token-ceiling outputs", audit.token_ceiling_rows],
  ["Reasoning-leak flags", audit.reasoning_leak_rows],
];
overview.getRange("A19:B24").format = { borders: { insideHorizontal: { style: "thin", color: border } } };
overview.getRange("B19").format = { fill: audit.valid ? "#DCFCE7" : "#FEE2E2", font: { bold: true, color: audit.valid ? green : "#B91C1C" } };
overview.getRange("D19:J24").merge();
overview.getRange("D19:J24").values = [[
  "Important: these readability scores are formula-based indicators, not direct evidence that an ordinary reader understood the summaries. All valid outputs were retained as observed. The final generation audit recorded 50 summaries with at least one formatting deviation, all from Mistral; these were not regenerated."
]];
overview.getRange("D19:J24").format = {
  fill: "#FFF7E6",
  font: { color: "#7C4A03" },
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "outside", style: "thin", color: "#F3C77A" },
};
overview.getRange("A26:J26").merge();
overview.getRange("A26:J26").values = [[
  "Files: the full condition-level data are in ‘All Results’; condition and policy summaries are provided in separate sheets."
]];
overview.getRange("A26:J26").format = { font: { color: muted, italic: true }, wrapText: true };
overview.freezePanes.freezeRows(2);
overview.getRange("A:A").format.columnWidth = 24;
overview.getRange("B:B").format.columnWidth = 25;
overview.getRange("C:C").format.columnWidth = 58;
overview.getRange("D:J").format.columnWidth = 14;

titleBand(conditions, "A1:J1", "Condition Summary", "Means across 27 policies for each model × prompt set × prompting strategy condition");
const condHeaders = [["Model", "Prompt set", "Prompting strategy", "n", "Mean words", "Median words", "Mean Flesch Reading Ease", "Mean Flesch-Kincaid Grade", "Mean SMOG Grade", "Mean word compression ratio"]];
conditions.getRange("A4:J4").values = condHeaders;
tableHeader(conditions.getRange("A4:J4"));
const condRows = audit.condition_summary.map((r) => [
  r.model_family.toUpperCase(), r.prompt_set, r.prompting_strategy, r.n, r.mean_words, r.median_words,
  r.mean_flesch_reading_ease, r.mean_flesch_kincaid_grade, r.mean_smog_grade, r.mean_word_compression_ratio,
]);
conditions.getRange(`A5:J${4 + condRows.length}`).values = condRows;
conditions.getRange(`A5:J${4 + condRows.length}`).format = { borders: { insideHorizontal: { style: "thin", color: border } } };
conditions.getRange(`D5:D${4 + condRows.length}`).format.numberFormat = "0";
conditions.getRange(`E5:F${4 + condRows.length}`).format.numberFormat = "0.00";
conditions.getRange(`G5:I${4 + condRows.length}`).format.numberFormat = "0.00";
conditions.getRange(`J5:J${4 + condRows.length}`).format.numberFormat = "0.0%";
conditions.tables.add(`A4:J${4 + condRows.length}`, true, "ConditionSummaryTable").style = "TableStyleMedium2";

const aggregate = new Map();
for (const row of audit.condition_summary) {
  const key = `${row.model_family}|${row.prompt_set}`;
  if (!aggregate.has(key)) aggregate.set(key, { model: row.model_family.toUpperCase(), set: row.prompt_set, n: 0, words: 0, fre: 0, compression: 0 });
  const item = aggregate.get(key);
  item.n += 1;
  item.words += row.mean_words;
  item.fre += row.mean_flesch_reading_ease;
  item.compression += row.mean_word_compression_ratio;
}
const aggRows = [...aggregate.values()].map((x) => [
  `${x.model} · ${x.set}`, Number((x.words / x.n).toFixed(2)), Number((x.fre / x.n).toFixed(2)), Number((x.compression / x.n).toFixed(4)),
]);
conditions.getRange("A26:D26").values = [["Model and prompt set", "Mean words", "Mean Flesch Reading Ease", "Mean word compression ratio"]];
tableHeader(conditions.getRange("A26:D26"));
conditions.getRange(`A27:D${26 + aggRows.length}`).values = aggRows;
conditions.getRange(`B27:C${26 + aggRows.length}`).format.numberFormat = "0.00";
conditions.getRange(`D27:D${26 + aggRows.length}`).format.numberFormat = "0.0%";
conditions.getRange("F26:G26").values = [["Model and prompt set", "Mean Flesch Reading Ease"]];
conditions.getRange("F27:G27").formulas = [["=A27", "=C27"]];
conditions.getRange(`F27:G${26 + aggRows.length}`).fillDown();
const chart = conditions.charts.add("bar", conditions.getRange(`F26:G${26 + aggRows.length}`));
chart.title = "Mean reading ease by model and prompt set";
chart.hasLegend = false;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
chart.setPosition("F34", "J49");
conditions.freezePanes.freezeRows(4);
conditions.getRange("A:A").format.columnWidth = 25;
conditions.getRange("B:C").format.columnWidth = 19;
conditions.getRange("D:D").format.columnWidth = 8;
conditions.getRange("E:J").format.columnWidth = 19;

titleBand(policies, "A1:H1", "Policy Summary", "Average results across 18 summaries for each OPP policy");
policies.getRange("A4:H4").values = [["Policy ID", "Source words", "n", "Mean summary words", "Mean Flesch Reading Ease", "Mean Flesch-Kincaid Grade", "Mean SMOG Grade", "Mean word compression ratio"]];
tableHeader(policies.getRange("A4:H4"));
const policyRows = audit.policy_summary.map((r) => [
  r.policy_id, r.source_words, r.n, r.mean_summary_words, r.mean_flesch_reading_ease,
  r.mean_flesch_kincaid_grade, r.mean_smog_grade, r.mean_word_compression_ratio,
]);
policies.getRange(`A5:H${4 + policyRows.length}`).values = policyRows;
policies.getRange(`B5:C${4 + policyRows.length}`).format.numberFormat = "0";
policies.getRange(`D5:G${4 + policyRows.length}`).format.numberFormat = "0.00";
policies.getRange(`H5:H${4 + policyRows.length}`).format.numberFormat = "0.0%";
policies.tables.add(`A4:H${4 + policyRows.length}`, true, "PolicySummaryTable").style = "TableStyleMedium2";
policies.freezePanes.freezeRows(4);
policies.getRange("A:A").format.columnWidth = 13;
policies.getRange("B:H").format.columnWidth = 20;

const rawUsed = raw.getUsedRange();
raw.getRange("A1:S1").format = {
  fill: navy,
  font: { bold: true, color: "#FFFFFF", name: "Aptos", fontSize: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
raw.getRange("A2:S487").format.font = { name: "Aptos", fontSize: 9, color: ink };
raw.getRange("A2:S487").format.borders = { insideHorizontal: { style: "thin", color: "#E2E8F0" } };
raw.getRange("D2:D487").format.columnWidth = 27;
raw.getRange("A:A").format.columnWidth = 38;
raw.getRange("B:C").format.columnWidth = 14;
raw.getRange("E:S").format.columnWidth = 16;
raw.getRange("J:K").format.columnWidth = 19;
raw.getRange("Q:S").format.numberFormat = "0.0000";
raw.freezePanes.freezeRows(1);
raw.freezePanes.freezeColumns(2);
raw.tables.add("A1:S487", true, "AllResultsTable").style = "TableStyleMedium2";

const inspect = await workbook.inspect({ kind: "sheet,table,drawing", maxChars: 8000, tableMaxRows: 4, tableMaxCols: 6 });
await fs.writeFile(path.join(outputDir, "workbook_inspection.ndjson"), inspect.ndjson ?? String(inspect), "utf8");

for (const sheetName of ["Study Overview", "Condition Summary", "Policy Summary", "All Results"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const safeName = sheetName.toLowerCase().replaceAll(" ", "_");
  await fs.writeFile(path.join(previewDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(path.join(outputDir, "opp115_readability_length_compression_review.xlsx"));
console.log(path.join(outputDir, "opp115_readability_length_compression_review.xlsx"));
