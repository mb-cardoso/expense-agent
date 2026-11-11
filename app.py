"""The web page: the same agent as the terminal.
Run: uv run streamlit run app.py"""

import json
import uuid
from typing import Any

import streamlit as st

from expense_agent import agent, config, llm, tools, tracing
from expense_agent.store import make_store

st.title("Expense agent")
if not config.API_KEY:
    st.error(f"No API key: set {config.KEY_NAME} in .env, or in the host's secrets when deployed.")
    st.stop()
st.caption("You are talking to an AI system, not a person. The tool lines are what was done.")
tracing.setup()  # on every run: one client per process, even after a re-import

# One dict, read once per run: Streamlit may stop a run at any access to st.session_state.
if "chat" not in st.session_state:  # once per browser tab: every message runs this file again
    st.session_state.chat = {
        "model": llm.make_model(tools.DECLARATIONS),  # kept: a local client closes with the run
        "store": make_store(),  # kept too: one connection to the data per tab, not one per run
        "id": uuid.uuid4().hex,  # one session per tab in the traces
        "previous_id": None,
        "messages": [],  # each with the tool lines it caused
        "questions": {},  # question: (tool, arguments), for each question waiting for a click
        "answers": [],  # the clicks' result lines, sent in front of the next message
    }
chat = st.session_state.chat
store = chat["store"]


def run_tool(name: str, arguments: dict[str, Any]) -> tools.Result:
    def confirm(question: str) -> None:  # a page cannot wait for a click: keep the question
        chat["questions"][question] = (name, arguments)

    return tools.run_tool(name, arguments, store, confirm)


def answer(question: str, yes: bool) -> None:
    """A click: the code runs the tool again with the user's answer. The model is not asked."""
    if (call := chat["questions"].pop(question, None)) is None:  # a second click
        return
    name, arguments = call
    said = "Yes" if yes else "No"
    with tracing.agent_turn(said, chat["id"]) as root:  # a turn of its own, in the same session
        with tracing.tool_call(name, "click", arguments) as span:
            # The question is rebuilt from the row: if the row changed, it differs, so no delete.
            result = tools.run_tool(name, arguments, store, lambda q: yes and q == question)
            tracing.tool_result(span, result)
        line = f"Answered {said} to: {question} Result: {json.dumps(result)}"
        tracing.end_turn(root, "answer", 0, line)
    chat["messages"].append({"role": "assistant", "content": line, "tools": []})
    chat["answers"].append(line)


for message in chat["messages"]:
    with st.chat_message(message["role"]):
        if message["tools"]:  # collapsed, as the live status ends
            with st.expander(f"Tool calls: {len(message['tools'])}"):
                for line in message["tools"]:
                    st.text(line)
        st.markdown(message["content"])

# disable: the input is off while a message is answered, so no second run starts on top of it.
if prompt := st.chat_input("Ask about your expenses", submit_mode="disable"):
    chat["questions"].clear()  # a new message drops the open questions: no old button acts
    chat["messages"].append({"role": "user", "content": prompt, "tools": []})
    with st.chat_message("user"):
        st.markdown(prompt)
    turn = agent.Turn()
    with st.chat_message("assistant"):
        with st.status("Working...") as status:
            try:
                agent.ask(
                    chat["model"],
                    "\n".join([*chat["answers"], prompt]),
                    chat["previous_id"],
                    run_tool,
                    config.MAX_ROUNDS,
                    turn,
                    on_log=status.text,  # each tool line as it happens
                    conversation_id=chat["id"],
                )
                chat["previous_id"] = turn.last_id
                chat["answers"].clear()  # only now: after a failed request, the retry sends them
            except Exception as error:  # noqa: BLE001 - explain() re-raises anything that is a bug
                turn.note = llm.explain(error)
                if getattr(error, "status_code", None) == 404 and chat["previous_id"]:
                    chat["previous_id"] = None  # the stored conversation is gone: start a new one
                    chat["id"] = uuid.uuid4().hex
                    turn.note = (
                        "The stored conversation is gone, or the model name is unknown: "
                        "the next message starts a new one."
                    )
            status.update(label=f"Tool calls: {len(turn.log)}", state="complete", expanded=False)
        response = turn.reply or turn.note or ""
        st.markdown(response)
    chat["messages"].append({"role": "assistant", "content": response, "tools": turn.log})

# After the message: a question this turn left is drawn now, and one a message dropped is not.
for i, question in enumerate(chat["questions"]):  # outside the messages: a click must reach it
    st.warning(question)
    yes, no = st.columns(2)
    yes.button("Yes", key=f"yes{i}", on_click=answer, args=(question, True))
    no.button("No", key=f"no{i}", on_click=answer, args=(question, False))

st.sidebar.dataframe(store.all(), hide_index=True)  # last: after this message's tools ran
