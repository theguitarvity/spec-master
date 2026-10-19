# Token ledger and statusline

Real token consumption per feature, phase and agent, read from the host's own
transcripts. The normative formats are in
[contracts/token-ledger-v1.md](contracts/token-ledger-v1.md); this page is the
how-to.

## What is recorded

`.spec-master/metrics/tokens.jsonl` holds one `spec-master.tokens/v1` line per
model response: timestamp, session, request id, agent id and type, feature,
phase, model, the four token counters (`input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`),
`output_tokens_complete`, `cost_usd` and `cost_basis`. Only usage metadata is
read; prompts and responses never reach the ledger.

Attribution comes from `.spec-master/events.jsonl` (`spec-master.event/v1`):
`state transition` appends `phase.started` / `phase.finished`, and on Claude
Code the `SubagentStart` / `SubagentStop` hooks append `agent.started` /
`agent.finished`. A response outside any phase window keeps `feature_id` and
`phase` null; nothing is guessed.

## Commands

```bash
python3 spec-master/lib/cli.py tokens ingest --path .            # discover transcripts, append new usage
python3 spec-master/lib/cli.py tokens ingest --path . --transcript <file.jsonl>
python3 spec-master/lib/cli.py tokens summary --path . [--since <ISO 8601>]
```

Ingest is incremental (a persisted byte offset per transcript in
`.spec-master/metrics/tokens.offsets.json`) and idempotent: responses are
de-duplicated by message and request id, so running it twice, after a
rotation, or from the statusline appends nothing twice. `summary` returns
`spec-master.tokens-summary/v1`: totals plus `by_feature`, `by_phase`,
`by_agent`, `by_model`, cache hit ratio and burn rate.

## Cost

`cost_usd` is an estimate from a list-price table (`cost_basis: "estimated"`).
A model that is not in the table has `cost_usd: null`, and a summary that
mixes in such lines sums only the priced ones. Override or extend the table in
`.spec-master/metrics/prices.json`:

```json
{ "my-model": { "input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75 } }
```

Prices are USD per million tokens; keys match by model-id prefix, longest wins.

## Statusline

Point Claude Code's `statusLine` at the script:

```json
{ "statusLine": { "type": "command", "command": "python3 spec-master/lib/statusline.py" } }
```

It reads the host JSON on stdin, ingests the session transcript incrementally,
and prints one line, for example
`014-token-ledger implement M | 182.4k tok | ~$1.37 | cache 91% | ctx 42%`.
Parts it cannot know are omitted. It always exits 0, even on malformed input.

## Limits

- A format the reader does not recognise yields no lines and a note
  (`no usage found`), never a guessed count.
- The transcript records a streaming snapshot of `output_tokens`; lines flagged
  `output_tokens_complete: false` are a lower bound.
- A response whose lines straddle two ingests may be recorded from the first
  part only; the exact figure is in the headless JSON (`telemetry ingest`).
- Subagent hooks exist on Claude Code only; other hosts attribute by phase
  window.
- The optional OTLP/HTTP receiver is deferred; the ledger's `source` field
  already reserves its place.
