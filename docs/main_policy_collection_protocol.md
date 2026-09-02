# Main-study privacy-policy collection protocol

## Purpose

Build a balanced contemporary corpus of 30 English-language consumer privacy policies: five organisations in each of six sectors. Mozilla, DuckDuckGo and Automattic are excluded because they were used in the pilot.

The candidate list is stored in `data/main/metadata/collection_log.csv`. A candidate does not become part of the final corpus until it passes the checks below.

## Sampling frame

| Sector | Candidate IDs | Target |
|---|---|---:|
| Technology | C01–C05 | 5 |
| Retail and e-commerce | C06–C10 | 5 |
| Financial services | C11–C15 | 5 |
| Health and wellness | C16–C20 | 5 |
| Travel and hospitality | C21–C25 | 5 |
| Media and entertainment | C26–C30 | 5 |

## Eligibility rules

Include a candidate only when all of the following are true:

1. It is an official policy controlled by the organisation.
2. It is a substantive privacy policy or privacy statement for ordinary consumers.
3. An English version is publicly accessible without an account.
4. The complete policy can be saved and converted to clean text.
5. The document contains enough substantive prose for summarisation.
6. The organisation was not used in the pilot.
7. The selected document is not merely a cookie notice, HIPAA notice, recruitment notice, developer notice or short privacy-centre landing page.

If a page is ineligible, record the reason before selecting a replacement from the same sector. Do not silently substitute documents.

## Collection procedure

For each candidate:

1. Open the URL in a private browser window and confirm the organisation, policy title and applicable region.
2. Record the displayed effective date or last-updated date exactly. Leave it blank only if no date is displayed.
3. Save the original page as HTML. If the official document is available only as a PDF, save the PDF instead.
4. Use the temporary candidate name until eligibility is confirmed: `C01_2026-08-14_source.html`.
5. Store originals in `data/main/raw/`. Never edit an original file.
6. Record the access date, source format and any collection problem in `collection_log.csv`.
7. Run the standard preprocessing procedure and save clean UTF-8 text in `data/main/clean/`.
8. Compare the cleaned text with the official page, checking headings, lists, tables, omissions, duplicated menus and cookie-banner text.
9. Record raw and clean word counts and SHA-256 hashes.
10. Mark `qa_status` as `passed` only after a second check confirms that the clean text preserves the policy meaning.

## Final IDs and filenames

Assign final IDs only after all candidates pass quality assurance. Use a reproducible order: sector order shown above, then organisation name alphabetically within each sector.

For a policy assigned `MAIN01`, use:

- Original: `MAIN01_2026-08-14_source.html` or `.pdf`
- Clean text: `MAIN01.txt`
- Metadata row: `MAIN01`
- Generated summary: `MAIN01__gpt__zero__r1.txt`

The collection date belongs in the source filename. A displayed policy date belongs in metadata and must not replace the collection date.

## Required metadata

Copy each accepted candidate into `data/main/metadata/policies.csv` and complete every applicable field: organisation, sector, region, title, canonical URL, effective date, access date, source filename, source format, language, raw word count, collection method and notes.

## Freeze rule

After the corpus is frozen, retain the collected snapshot even if an organisation later updates its live policy. Do not mix collection dates or silently replace a frozen source. Any correction must be recorded in the study decision log with the old and new hashes.
