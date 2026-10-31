# Wiki page template and writing rules

The run generates this structure. Keep it; edit the words, not the skeleton.

```
# Database discovery: <engine> at <host:port>
Run `<name>`, evidence collected <date> with the read only account `<user>`. (one sentence on verifiability)

## 1. Summary
| Item | Value |            version, started or uptime, role, databases and size, extensions or engines, connections, replicas
| Severity | Findings |     High, Medium, Low, Info, Unknowns
### Top actions            five numbered lines: title (severity, effort): recommendation

## 2. Findings by area      one subsection per area, 2.1 to 2.10, in the fixed order
### 2.n <Area>
Evidence reviewed: `area.key`, ...
**`ID` Title** (Severity)
What the evidence shows: ...
Recommendation: ... Effort: ... Evidence: `area.key`.
Unknown: question. How to obtain: ...

## 3. Unknowns and how to obtain them    table: Area, Question, How to obtain

## 4. Prioritized recommendations        table: Priority, Id, Action, Severity, Effort, Area, Evidence

## Appendix A: Evidence                   every query and its rows, grouped by area, keyed `area.key`
```

## Writing rules

Write for a manager first and a DBA second: the summary and the prioritized table must stand alone; the appendix must let the DBA rerun everything.

One finding, one weakness. Do not bundle three problems into one paragraph; each gets an id so it can be assigned and closed on its own.

Numbers over adjectives. "Cache hit is 81 percent over 5 million reads since March" beats "cache performance is poor".

Every claim cites its evidence key, and every recommendation is an instruction someone can start: the setting to change, the command to run, the person to ask.

Severity describes consequence, not how easy the fix is; effort describes the fix. Both are stated on every finding.

Unknowns are not failures. Say what was not answered and exactly how to answer it, and keep them visible in section 3 until they are resolved.

Add the owner's interview answers as quoted evidence under `interview.<topic>` in the appendix, and cite them like any other key.

Never place credentials, connection strings or tokens on the page. The collector redacts them; the editor must too.

Do not remove appendix rows to shorten the page; shorten by tightening the sentences in sections 1 to 4.

Plain sentences, spelled out words, no dashes as punctuation; identifiers, commands and values go in backticks.
