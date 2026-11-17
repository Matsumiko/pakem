# Pakem evals

24 behavioral evals: one prompt, one `expected_output`, and 3–5 `assertion`s that can be graded. The format follows Agent Skills / skill-creator, so `evals.json` can be read by other tools; the runner in this repo adds a way to run them.

## What is measured

Not Pakem's code — the code already has `tests/`. What is measured: **whether an agent holding this skill actually behaves according to SKILL.md**. Example assertions: "The init command is run from `scripts/pakem.py` with `--type app`", "the agent does not claim it is done before `pakem finish` exits 0".

## Check the structure first

```bash
python3 scripts/run_evals.py --validate
```

Checks unique ids, non-empty prompts, non-empty assertions. This is cheap and can go into CI.

## Run one eval

```bash
python3 scripts/run_evals.py --agent-cmd "<perintah agent>" --eval 1 --keep
```

The runner sets up an empty sandbox directory, sends the prompt over stdin, records the exit code and transcript, then saves `stdout.txt`, `stderr.txt`, and `report.json` in the sandbox. **Without a judge, assertions are not graded** — the runner does not pretend to know quality.

## One trap: relative paths

Agents and judges run with **cwd = the sandbox directory**, not your directory. So `--agent-cmd "python3 agent.py"` will fail with `can't open file` because `agent.py` is not inside the sandbox. Use an absolute path:

```bash
python3 scripts/run_evals.py --agent-cmd "$(which python3) /opt/kerja/agent.py" ...
```

The runner prints the line `! agent exit N: ...` along with an excerpt of stderr so that failures like this are visible, not buried as "0 files written".

## Grade with a judge

Assertions are written in natural language, so grading them needs a grader. The judge is any command — a model, a script, or a combination:

```bash
python3 scripts/run_evals.py \
  --agent-cmd "<perintah agent>" \
  --judge-cmd "python3 my-judge.py" \
  --out evals-results.json
```

Judge contract:

- **stdin**: one JSON object — `eval_id`, `prompt`, `expected_output`, `assertions`, `exit_code`, `timed_out`, `transcript` (truncated to 20k characters), `files` (path + size in the sandbox).
- **stdout**: `{"results": [{"assertion": "...", "pass": true, "why": "..."}]}`
- Every assertion must appear exactly once. Ones that are not graded count as **failed** with the reason `judge tidak menilai assertion ini`, so a lazy judge cannot produce a fake score.
- non-zero exit or output that is not JSON = all assertions for that eval fail, and `judge_error` is recorded in the report.

## Exit code

- `--validate`: 1 if the structure is broken.
- With `--judge-cmd`: 1 if any assertion fails.
- Without `--judge-cmd`: always 0 (record mode).

## What the runner deliberately does not do

- It does not choose a model, inject the skill, or configure the system prompt. That is your `--agent-cmd`'s job.
- It does not clean up agent side effects outside the sandbox.
- It does not run evals in parallel. One at a time, so transcripts are easy to read when something fails.
