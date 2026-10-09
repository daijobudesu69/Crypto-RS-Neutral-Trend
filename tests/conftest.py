import dataclasses
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tes tidak boleh pernah mengirim ke Telegram / Sheets sungguhan atau memakai kunci.
for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GSHEET_WEBHOOK_URL", "GOOGLE_SERVICE_ACCOUNT_JSON",
          "GSHEET_SPREADSHEET_ID", "RNT_AGENT_KEY"):
    os.environ.pop(k, None)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    from rntbot import store
    monkeypatch.setattr(store, "STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


@pytest.fixture
def cfg():
    """Config repo, dengan fetch_days lebih pendek untuk data sintetis dan tanpa forward_start."""
    from rntbot import config
    c = config.load()
    return dataclasses.replace(c, forward_start="")


@pytest.fixture
def live_cfg(cfg):
    ex = dataclasses.replace(cfg.execution, master_address="0x" + "a" * 40, account_address="0x" + "b" * 40,
                             agent_address="0x" + "c" * 40, agent_valid_until="2027-12-31")
    return dataclasses.replace(cfg, execution=ex)
