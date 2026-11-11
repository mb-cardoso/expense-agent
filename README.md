# Expense agent, in the cloud

The expense agent of <https://github.com/mb-cardoso/expense-agent>, with what a
deployed application needs: the expenses in MongoDB Atlas, a find-similar example on
Atlas Vector Search, and the steps to deploy it on Streamlit Community Cloud. The
first commit is that repository as it stands; the commits after it are the changes.

The agent keeps a university student's expense records. It adds, lists, totals and
deletes expenses through four tools, and asks the user before every delete. A
terminal interface and a web page use the same package, and the tests never call
the model. It runs on Gemini or on Claude, one setting apart, and can trace each
message in Langfuse: these are this repository's choices, not requirements. It is a
reference to read, not a template: each project is built from scratch.

## Before you start

- Install uv: https://docs.astral.sh/uv/getting-started/installation/
- `git clone <this repository's URL>`, then `cd expense-agent-cloud`. uv fetches the
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
with six examples the first time it is read, until `MONGODB_URI` is set (below).

## Your first messages

Type "How much did I spend on food?", then "I bought a sandwich yesterday, 4 euros.",
then "Delete my last coffee.". Each tool call shows as a line, `[tool] arguments ->
result`: the record of what was done. Before the delete, the terminal asks y/N and
the page shows Yes and No. In the terminal, `/data` shows the data, `/clear` starts a
new conversation, `/help` lists the commands and `/quit` leaves.

## Where the data lives

With `MONGODB_URI` set, the expenses are in MongoDB instead of the file: one document
per expense in the `expense_agent` database, and the next id in a counter document,
so an id is never reused. `make_store()` in `store.py` picks the database or the
file, as `make_model()` picks the provider; the tools see the same four methods
either way. A database used for the first time starts from the six examples.

To get a connection string: create a free cluster at <https://www.mongodb.com/atlas>,
a database user with read and write access, and your address in **Network Access**;
**Connect > Drivers** gives the string, with the password to fill in. A deployed app
connects from addresses you do not control: allow access from anywhere (`0.0.0.0/0`)
and let the user name and password do the protecting. In `.env`:

```bash
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
```

`uv run pytest` then runs two tests against the database, in a database of their
own, and skips them when `MONGODB_URI` is not set.

## Find similar: the tickets example

`examples/similar_tickets.py` is a second agent over the same package, with one tool,
`similar_tickets`. Thirty past support tickets are embedded once with Gemini's
embedding model and stored with their vectors in Atlas, next to the expenses; a vector
index ranks them in one query, and the model answers from the five nearest and how
each was resolved. With `MONGODB_URI` and `GOOGLE_API_KEY` set:

```bash
uv run python examples/similar_tickets.py
```

The first run stores the tickets and waits for the index, about a minute; later runs
only search. Similarity is for a query that is an item, "a ticket like this one"; for
"which tickets mention a refund", a lookup does.

## Deploy it

Streamlit Community Cloud runs a Streamlit app from a GitHub repository, at a public
address, free.

1. Fork this repository into your GitHub account.
2. At <https://share.streamlit.io>, sign in with GitHub and choose **New app**: your
   repository, the branch `main`, the file `app.py`.
3. In **Advanced settings**: Python 3.12, the version in `.python-version`; and the
   secrets, as TOML:

   ```toml
   PROVIDER = "google"
   GOOGLE_API_KEY = "..."
   MONGODB_URI = "mongodb+srv://..."
   LANGFUSE_PUBLIC_KEY = "pk-lf-..."
   LANGFUSE_SECRET_KEY = "sk-lf-..."
   LANGFUSE_TRACING_ENVIRONMENT = "production"
   TRACE_CONTENT = "false"
   ```

   Community Cloud gives them to the app as environment variables, so `config.py`
   reads them as it reads `.env`. They can be changed later in the app's settings.
4. **Deploy**. Community Cloud installs the packages from `uv.lock` and starts
   `app.py`. The first message sent to the public address shows in Langfuse under the
   environment `production`.

What to know:

- The app starts from the repository on every deploy and reboot: nothing it writes
  to its own folder survives, and `data/` is not even in git. The expenses live in
  Atlas. A file the app reads, such as a knowledge base, is committed, outside `data/`.
- An app nobody opens for twelve hours goes to sleep; whoever opens it wakes it with
  a click. Open yours before a demonstration.
- Content recording stays off: the traces show the steps, tokens and cost of real
  people's messages, not their text.
- A package the app cannot import shows in its logs (**Manage app**) as
  `ModuleNotFoundError`: add it with `uv add`, commit `pyproject.toml` and `uv.lock`,
  and push; the app redeploys.

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
  store.py                 the data: the only code that reads or writes it, in a file or in MongoDB
  config.py                every setting, with its values, default and meaning
  tracing.py               traces: the only module that imports the Langfuse SDK
tests/                     offline tests: a scripted model stands in for both adapters; two on the database, with MONGODB_URI
examples/                  similar_tickets.py and its tickets.json: find similar, on Atlas Vector Search
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
