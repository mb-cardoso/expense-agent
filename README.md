# Expense agent

An agent that keeps a university student's expense records. It adds, lists, totals
and deletes expenses through four tools, and asks the user before every delete. A
terminal interface and a web page use the same package, and the tests never call
the model. It runs on Gemini or on Claude, one setting apart, and can trace each
message in Langfuse: these are this repository's choices, not requirements. It is a
reference to read, not a template: each project is built from scratch.

## Before you start

- Install uv: https://docs.astral.sh/uv/getting-started/installation/
- `git clone <this repository's URL>`, then `cd expense-agent`. uv fetches the
  Python that `.python-version` names (3.12) by itself.
- An API key: Gemini's from Google AI Studio (https://aistudio.google.com/apikey),
  which has a free tier; or Claude's from the Claude Console, which needs paid credits.
- `uv run pytest` passes with no key.

## Run it

```bash
uv sync
cp .env.example .env               # then fill in GOOGLE_API_KEY
uv run expense-agent               # the terminal; --trace prints each request and reply
uv run streamlit run app.py        # the page, at http://localhost:8501
```

Every setting, its values and its default are listed at the top of
`expense_agent/config.py`. The expenses are kept in `data/expenses.json`, created
with six examples the first time it is read; delete it to start again.

## Your first messages

Type "How much did I spend on food?", then "I bought a sandwich yesterday, 4 euros.",
then "Delete my last coffee.". Each tool call shows as a line, `[tool] arguments ->
result`: the record of what was done. Before the delete, the terminal asks y/N and
the page shows Yes and No. In the terminal, `/data` shows the data, `/clear` starts a
new conversation, `/help` lists the commands and `/quit` leaves.

## Switch providers

In `.env`:

```bash
PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

Leave `MODEL` unset, or set it to a model of that provider, and restart the program;
nothing else changes. `docs/ARCHITECTURE.md` says why, and what each adapter keeps.

## Check it

```bash
uv run pytest                      # offline: the model is scripted, no key needed
uv run ruff check                  # lint
uv run ruff format --check         # formatting
uv run mypy                        # types
```

## Evaluate it

```bash
uv run python evals/run_evals.py   # 2 sets x 5 trials x 5 cases: 50 real conversations, billed
```

Each case in `evals/cases.jsonl` is a message and the data it should leave; a trial
is one conversation of a case, and a set is a trial of every case. The grades are
reported set by set, so the model's variation shows. Run it by hand, never in CI.

## Trace it

Prompts, replies and tool data are recorded only with `TRACE_CONTENT=true`. It is
off by default, so a first trace shows the steps, timings, tokens and cost, but no
text; turn it on with made-up data only.

Create a project at https://cloud.langfuse.com, and paste its two keys in `.env` as
`LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`: tracing is on from then on. That
address is the EU region, the default; another region or server goes in
`LANGFUSE_BASE_URL`.

Each message is one trace: the turn, a generation per model request and a tool
observation per tool call. The page traces too, and each Yes or No click is a trace
of its own. With tracing on, `--trace` also prints each message's trace id: open it
at `<LANGFUSE_BASE_URL>/project/<project id>/traces/<trace id>`, or find it in **Tracing**.

## Project structure

```
app.py                     the web page
expense_agent/
  cli.py                   the terminal; in the package because the expense-agent command imports it
  agent.py                 the loop: one message in, one Turn out
  prompts.py               the instruction and the message tags
  llm.py                   the Model protocol, GeminiModel, ClaudeModel, make_model(), explain()
  schemas.py               the tools' argument models, and check(): the rules on their values
  tools.py                 the tools, their declarations and run_tool()
  store.py                 the data: the only code that reads or writes it
  config.py                every setting, with its values, default and meaning
  tracing.py               traces: the only module that imports the Langfuse SDK
tests/                     offline tests: a scripted model stands in for both adapters
evals/                     the labelled cases and the script that runs them
docs/                      ARCHITECTURE.md (the layers and one message through them), TOOLS.md
.github/workflows/ci.yml   the four checks on every push
pyproject.toml, uv.lock    the dependencies, and the exact version of each, committed
.python-version            the Python version uv uses
.env.example               the variables to fill in; config.py says what each one does
.gitignore                 keeps .env, data/, .venv and the caches out of git
LICENSE                    MIT
```

`app.py` is at the root because Streamlit runs a page by its path.
`docs/ARCHITECTURE.md` follows one message through the layers, in a recorded run.

## How a project like this grows

- More tools on the same data: `tools.py`, with their argument models in `schemas.py`.
- Tools on other data: a `tools/` package, one module per group, with the registry and
  `run_tool()` in `tools/__init__.py`, and `Result` and `Confirm` in `schemas.py`, or
  the imports go in a circle.
- Retrieval: one `retrieval.py`, the only module that imports the vector store, called by a tool.
- A second page: `app.py` becomes the `st.navigation` router, with the pages in `pages/`;
  never a second entrypoint.
- Uploads: the page saves them to `data/uploads/` and passes them to the package.
- Split a module only when it holds two jobs.

## Practices behind it

- **A lock file.** Every package you import declared in `pyproject.toml`,
  `uv.lock` committed, dev tools in the `dev` group. A fresh clone runs
  `uv sync --locked`, then `uv run pytest`.
- **A build system once the code is a package folder** (`[build-system]`, with
  `module-root = ""` for a package at the root): it gives the command and the imports.
- **Layers.** The logic in one package; the interface only shows and collects.
- **Settings in one module**, `config.py`; no `.env`, secret or data file committed.
- **Prompts and schemas in their own modules.**
- **Offline tests that pass with no key**, with a scripted model for the loop.
- **A linter, a formatter and a type checker run clean**, and CI runs them with the
  tests on every push.
- **Evals by hand, in sets** (see "Evaluate it").

## License

MIT: see `LICENSE`.
