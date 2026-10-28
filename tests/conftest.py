"""Runs before the tests: use a temporary in-memory database, never the real tickets.db."""
import os

os.environ["DATABASE_PATH"] = ":memory:"
os.environ["LLM_PROVIDER"] = "fake"