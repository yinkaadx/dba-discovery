---
name: dba-review
description: Turn a discovery page into an agreed action plan with the platform owner, decide severities and risk acceptance, set owners and dates, and prepare the follow up run. Use when a dba-discovery wiki page exists and the next step is a review meeting, a remediation plan, a status report, or a repeat discovery.
---

# Findings review and remediation plan

A discovery page is only useful once someone owns each finding. This skill runs the review, records the decisions in the inventory, and makes the next run measurable.

## Before the meeting

Read the page's section 1 and section 4. Group the prioritized table into three bands: do now (High, small or medium effort), plan (High with large effort, and Medium), and hygiene (Low and Info). Draft one sentence per band that says what the owner gets by doing it. Pull the interview answers and unknowns; the meeting must close as many unknowns as possible because they hide risk.

Check the evidence behind every High finding yourself before presenting it. A High that turns out to rest on a short statistics window or a misread setting costs credibility for the whole page; downgrade it or remove it before the meeting, and say so in the page's change note.

## In the meeting

Walk the table from the top. For each finding ask three questions: do you agree with the evidence, who owns the fix, by when. Record the answer as one of: `accepted` (agreed, not started), `in_progress`, `done`, or `risk_accepted` (the owner chooses to live with it, and the reason is written next to the status). Do not argue severity in the meeting beyond the evidence; if the owner disagrees, note the disagreement on the page and keep the rule's severity, because the page must stay comparable across platforms.

Close unknowns by asking the interview questions the owner can answer now. Assign the rest to a named person.

Agree the refresh date. Production: quarterly, or sooner after the do now band is complete. Anything else: before the next handover or audit.

## After the meeting

Record every decision with the inventory `status` command, including owner and due date. Add a "Review" section at the end of section 4 of the wiki page with the date, attendees, the three bands and the refresh date. Send the owner the do now band as a short list with the finding ids.

## Status report

When asked how a platform stands, answer from the inventory, not from memory: the platform row (`v_platform_summary`) gives open counts; `v_open_findings` filtered by host gives the list with owners and dates. Report overdue items first (due date passed, status not done), then in progress, then accepted and not started. Quote finding ids so the reader can open the page.

## Repeat discovery

Run `dba-discovery` again with a new run name, load it, then `python -m discovery diff --a runs/<earlier> --b runs/<later>`. The inventory views report from the latest run, so a resolved finding leaves the open list on its own while the older run keeps its record for history. New findings go through the same review. Report the three numbers (resolved, new, remaining) to the owner with the page link. A platform where the same High finding survives three runs is escalated to the business owner in writing, because the technical owner has been unable to act.

## Rules

Evidence decides, not seniority; a finding without evidence is removed, a finding with evidence stays until it is done or its risk is accepted in writing. Every finding has one owner and one date. The inventory is updated the same day as the meeting. The wiki page keeps the appendix untouched so that the next reviewer can verify the past.
