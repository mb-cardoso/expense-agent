"""Settings: the only module that reads the environment. A variable already set wins over .env.

Setting                       Values; default                   What it does
PROVIDER                      google, anthropic; google         the LLM API that answers
MODEL                         a model name; MODELS below        the model asked
GOOGLE_API_KEY                a key; none                       needed with google
ANTHROPIC_API_KEY             a key; none                       needed with anthropic
EXPENSES_FILE                 a path; data/expenses.json        where the expenses are kept
LANGFUSE_PUBLIC_KEY           a key; none                       with the secret key: tracing on
LANGFUSE_SECRET_KEY           a key; none                       with the public key: tracing on;
                                                                keep it secret
LANGFUSE_TRACING_ENABLED      true, false; true                 false: no tracing, even with keys
LANGFUSE_BASE_URL             a URL; https://cloud.langfuse.com the Langfuse region or server
LANGFUSE_TRACING_ENVIRONMENT  a name; default                   a tag on every trace, to filter
TRACE_CONTENT                 true, false; false                true: traces hold what the user,
                                                                the model and the tools wrote
LANGFUSE_HOST is not read: use LANGFUSE_BASE_URL. Set in code, below: EFFORT, MAX_ROUNDS.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # the project folder
load_dotenv(ROOT / ".env")  # an explicit path: otherwise it also searches parent folders

PROVIDER = os.getenv("PROVIDER", "google").strip().lower()
if PROVIDER not in ("google", "anthropic"):
    raise ValueError(f"PROVIDER must be google or anthropic, not {PROVIDER!r}. Fix it in .env.")
KEY_NAME = {"google": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[PROVIDER]
API_KEY = os.getenv(KEY_NAME)
# Fixed model ids: each provider retires a model on its own schedule, and the id is then changed here.
# Stronger models: gemini-3.8-flash; claude-sonnet-5-5, claude-opus-5-5.
MODELS = {"google": "gemini-3.5-flash-lite", "anthropic": "claude-haiku-5-5"}
MODEL = os.getenv("MODEL", MODELS[PROVIDER])
# How much Claude thinks. Sent explicitly: Opus 5.5 and Haiku 5.5 default to medium, others high.
EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
DATA_FILE = ROOT / os.getenv("EXPENSES_FILE", "data/expenses.json")  # relative to ROOT
MAX_ROUNDS = 8  # tool rounds for one message

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
LANGFUSE_ENVIRONMENT = os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "default")
TRACING = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY) and (
    os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() != "false"
)
TRACE_CONTENT = os.getenv("TRACE_CONTENT", "false").lower() == "true"
