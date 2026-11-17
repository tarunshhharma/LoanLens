"""The demo access code in ui/app.py, driven through Streamlit's AppTest (no browser, no API).

AppTest runs the script the way Streamlit would and lets a test type into widgets.
Nothing here reaches the API: the gate stops the script before any call is made.

Run from the project root:
    pytest tests/test_ui_access.py -v
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# AppTest resolves relative paths from this file's folder, not the project root
SCRIPT = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")
WELCOME = "Upload a loan agreement in the sidebar to begin."


def start(monkeypatch, code=None):
  if code is None:
    monkeypatch.delenv("LOANLENS_ACCESS_CODE", raising=False)
  else:
    monkeypatch.setenv("LOANLENS_ACCESS_CODE", code)
  return AppTest.from_file(SCRIPT, default_timeout=30).run()


def shows_app(at) -> bool:
  return any(box.value == WELCOME for box in at.info)


def test_no_code_set_means_no_gate(monkeypatch):
  # Local use and docker compose: no access code, straight to the app
  at = start(monkeypatch)
  assert len(at.text_input) == 0
  assert shows_app(at)


def test_gate_hides_the_app_until_a_code_is_entered(monkeypatch):
  at = start(monkeypatch, code="letmein")
  assert at.text_input[0].label == "Access code"
  assert not shows_app(at)
  assert len(at.sidebar.get("file_uploader")) == 0  # no way to upload


def test_wrong_code_is_rejected(monkeypatch):
  at = start(monkeypatch, code="letmein")
  at.text_input[0].input("guess").run()
  assert at.error[0].value == "Wrong access code."
  assert not shows_app(at)


@pytest.mark.parametrize("attempt", ["letmei", "letmein ", "LETMEIN"])
def test_near_misses_are_rejected(monkeypatch, attempt):
  at = start(monkeypatch, code="letmein")
  at.text_input[0].input(attempt).run()
  assert not shows_app(at)


def test_right_code_unlocks_the_app(monkeypatch):
  at = start(monkeypatch, code="letmein")
  at.text_input[0].input("letmein").run()
  assert at.session_state.unlocked
  assert len(at.text_input) == 0  # the code box is gone
  assert shows_app(at)
