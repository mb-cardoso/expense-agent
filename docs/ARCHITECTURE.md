# Architecture

- **Turn**: one user message and everything the agent does for it, up to its reply.
- **Tool log**: one line per tool call in a turn, the call and its result: the record of what was done.
- **Round cap**: the most tool rounds a turn may take (`MAX_ROUNDS` in `config.py`).
- **Instruction**: the system prompt, sent with every request to the model.
- **Adapter**: the class that turns the agent's requests into one provider's API.
- **Trace**: the record of one turn in Langfuse; a **generation** is one model request in it.
- **Waiting**: the delete's answer while the user has not clicked Yes or No on the page.

Four layers: an interface (the terminal or the web page), a service, AI access, and
the tools with their data.

| Layer | Files | Its job | Never |
|---|---|---|---|
| Interface | `expense_agent/cli.py`, the terminal; `app.py`, the web page | collects the message and the user's yes or no; shows the tool log and the reply; creates the model and the store and passes them in | builds a prompt or decides which tool runs |
| Service | `expense_agent/agent.py`, `prompts.py` | fills in the instruction and the message for each request; runs the loop and its rules; returns a Turn | prints, reads input, imports the SDK |
| AI access | `expense_agent/llm.py` | turns a request into one provider's API call, and its answer into a Reply; records each request as a generation; explains API errors | touches the data |
| Tools and data | `expense_agent/tools.py`, `schemas.py`, `store.py` | validates the model's arguments, applies the rules, asks before deleting, reads and writes the data | talks to the user |

Imports go one way. Each interface imports the rest; `agent.py` imports
`prompts.py` and `llm.py`; `tools.py` imports `schemas.py` and `store.py`; nothing
in the package imports an interface. `config.py` is the only module that reads
the environment, and every module that needs a setting imports it from there. An
unknown `PROVIDER` stops the program when `config.py` is imported, with a
`ValueError` that names the two values. What to do when a setting is missing, such
as stopping on a missing key, stays in the entry points (`cli.py`, `app.py`,
`evals/run_evals.py`). `tracing.py` is the only module that imports the Langfuse
SDK: `agent.py`, `tools.py` and the two adapters say what happened. Every entry
point calls `tracing.setup()` before the first message: the terminal once, the page
on every run of its script. Without it, the SDK would make its own client from the
environment.

**The loop.** The terminal, the page and the tests call the same `agent.ask()`,
and none of them builds a prompt or picks a tool. It sends the message with the
instruction and the tool declarations. While the reply asks for tools, it runs the
calls in the order given, writes a tool-log line for each, and sends the results
back. It stops on an answer (a complete reply with text), on a reply without one
(`no_answer`: cut short, refused or empty), or at the round cap (`round_cap`).

**The confirmation.** The delete asks the user in code, through the `confirm()`
the interface passes in, so nothing the model writes can skip it. The terminal asks
y/N and waits. The page cannot wait: its `confirm()` keeps the question, the tool
answers "waiting", and the page draws Yes and No. A click runs the delete again in
code, and its result line goes to the model in front of the next message. The
package needed nothing else for the page.

## Two providers, one Model protocol

`agent.py` asks a model for two things only, through the `Model` protocol in
`llm.py`: `send_text()` and `send_results()`, each with the id of the reply it
answers and the instruction, each returning a `Reply` (its id, the calls, the
text, a status). An adapter, in the same file, turns that into one provider's API:

| | `GeminiModel` | `ClaudeModel` |
|---|---|---|
| API | Interactions | Messages |
| The conversation | kept on Google's server; the reply id is `previous_interaction_id` | kept by the adapter: each reply id names the system prompt, the messages and the calls still without a result |
| The instruction | sent with every request | the conversation's first is kept, date included: a new one would void the thinking blocks sent back |
| A call left without a result (the round cap, a reply cut short) | accepted | answered "Not run" before the next text, or the API rejects the request |
| A refused or cut reply | a status other than `completed` | `status="refusal"` (or `incomplete`); a refused reply is never sent back, and the refused message stays in the history until `/clear` |
| Thinking | the model's default | on by default (adaptive); `config.EFFORT` sets how much |
| The generation's tokens | input, and output plus thoughts | input, and output (the thinking is in it) |

A reply id therefore means the same on both: `None` starts a conversation (the
terminal's `/clear`), and after a failed request the interface sends the last id
that answered, which goes on from before the failed turn. Neither interface keeps
the id across a restart, so a restarted program starts a new conversation.

`PROVIDER` in `.env` picks the adapter, through `llm.make_model()`, and `MODEL`
defaults to that provider's model. The loop, the tools, the prompts and both
interfaces never name a provider, so switching changes none of them: the same
tool lines, the same `--trace` lines, the same trace shape in Langfuse.

**Retries are the SDKs' own.** A failed request is sent again on 408, 409, 429, a
5xx or no connection, with backoff, before the error reaches `explain()`. Against a
server that always answered 503 or 429, anthropic 2.3.0 sent 3 requests and
google-genai 2.34.0 (Interactions) sent 4. The interface then shows `explain()`'s
sentence and keeps the conversation's id, so the next message goes on from the last
reply that arrived.

A 404 on a message sent with a conversation id means Gemini's stored conversation
is gone, or the model name is unknown; on Claude it can only be the model name. The
terminal and the page drop the id, and the next message starts a new conversation.
The facts are in the data, so nothing that mattered is lost.

## One message, traced

`uv run expense-agent --trace` on `gemini-flash-lite-latest`, with the confirmation
answered `n`. The `request` and `reply` lines are the `--trace` log; ids are cut to
their last eight characters. With tracing on, the message's trace id follows the
reply.

```
you > Delete my last coffee.
  request  previous=None instruction=446 chars tools=4 input='<message>Delete my last coffee.</message>'
  reply    id=4UFJpUUU status=requires_action calls=['list_expenses {"category": "food"}'] text=''
  [list_expenses] {"category": "food"} -> {"expenses": [{"id": 1, "amount": 3.2, "category": "food", "date": "2026-10-26", "description": "coffee"}, {"i
  request  previous=4UFJpUUU instruction=446 chars tools=4 input=result of list_expenses (call_1367108)
  reply    id=4djMtQTg status=requires_action calls=['delete_expense {"id": 5}'] text=''
  Delete expense 5: coffee, 3.00 euros on 2026-10-30? [y/N] n
  [delete_expense] {"id": 5} -> {"deleted": false, "reason": "The user declined. Nothing was deleted. Do not ask again unless the user asks yo
  request  previous=4djMtQTg instruction=446 chars tools=4 input=result of delete_expense (call_1217045)
  reply    id=5N2tvUW8 status=completed calls=none text='The user declined to delete the last coffee (id: 5, description: "coffee", 3.00 '

ai  > The user declined to delete the last coffee (id: 5, description: "coffee", 3.00 euros on 2026-10-30), so nothing was deleted.
```

1. **Interface.** `cli.py` reads the line and calls `agent.ask()` with the model,
   the message, `previous_id` (None: a new conversation), its `run_tool` and the
   round cap from `config.py`.
2. **Service.** `agent.ask()` fills in `prompts.INSTRUCTION` with today's date and
   wraps the message in `<message>` tags.
3. **AI access.** `llm.py` sends the model name, the instruction, the four
   declarations, the message and `previous_interaction_id`. The reply asks for
   `list_expenses` and has no text.
4. **Tools and data.** `run_tool()` validates the arguments and `list_expenses`
   reads `store.py`. The line goes into the Turn and, through `on_log`, to the screen.
5. **Service.** The result goes back with its call's id, on top of the reply that
   asked for it, with the same instruction and tools.
6. **Tools and data.** The model asks for `delete_expense` with id 5. The tool puts
   its question to `confirm()`: the terminal asks y/N. On `n` nothing is deleted,
   and the result says so.
7. **Service, then interface.** The reply holds no call, is complete and has text,
   so it is the answer. `agent.ask()` returns the Turn; `cli.py` prints it and
   keeps its last id for the next message.

The reply is a sentence the model wrote. What happened is in the tool log and the
data: `/data` shows expense 5 still there, whatever a reply says.
