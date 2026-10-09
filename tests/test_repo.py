"""Konsistensi repo: config = SPEC v1.1, control, workflow, dan aturan keamanan yang mudah rusak diam-diam."""
import os
import re

import pytest
import yaml

from rntbot import config, control

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wf(name):
    with open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8") as fh:
        return fh.read()


def test_config_matches_spec_v11():
    cfg = config.load()
    s = cfg.strategy
    assert (s.vol_span, s.min_hist, s.liq_win, s.rs_top, s.rs_in, s.rs_out, s.tr_top) == (30, 200, 30, 20, 4, 8, 5)
    assert s.rs_lookbacks == (7, 14, 28, 56) and s.tr_channels == (20, 55, 100)
    assert (s.tr_coin_vol, s.sleeve_vol, s.vt_lookback, s.vt_cap, s.gross_cap) == (0.40, 0.20, 60, 2.0, 2.5)
    assert (s.age_mode, s.pct_scope) == ("real", "traded")
    assert (cfg.rules.min_order_usdc, cfg.rules.band) == (10, 0.40)
    assert cfg.costs.taker_fee + cfg.costs.paper_slippage == pytest.approx(0.0007)
    a = cfg.alarms
    assert (a.yellow_dd_pct, a.red_dd_pct, a.cusum_h, a.yellow_scale, a.tracking_max_pct) == (20, 25, 0.45, 0.5, 3)
    assert cfg.capital_usdc == 200 and cfg.execution.margin_mode == "cross"


def test_unknown_or_unsafe_config_rejected():
    with pytest.raises(ValueError):
        config.from_dict({"strategy": {"rs_ot": 8}})
    with pytest.raises(ValueError):
        config.from_dict({"execution": {"margin_mode": "isolated"}})
    with pytest.raises(ValueError):
        config.from_dict({"universe": {"fetch_days": 200}})
    with pytest.raises(ValueError):
        config.from_dict({"execution": {"leverage": 2}})       # gross_cap 2,5 > leverage


def test_all_workflows_are_valid_yaml():
    d = os.path.join(ROOT, ".github", "workflows")
    names = sorted(os.listdir(d))
    assert names == ["bot.yml", "canary.yml", "ci.yml", "control.yml", "smoke.yml", "watchdog.yml"]
    for f in names:
        doc = yaml.safe_load(wf(f))
        assert doc.get("name", "").startswith(("RNT", "tests")) and doc.get("jobs"), f
        on = doc.get("on", doc.get(True))
        assert "workflow_dispatch" in on, f"{f}: tanpa workflow_dispatch"


def test_agent_secret_name_matches_workflows():
    cfg = config.load()
    for f in ("bot.yml", "canary.yml", "smoke.yml"):
        assert f"secrets.{cfg.execution.agent_secret}" in wf(f), f


def test_watcher_loop_guards_every_command():
    """bash -e: exit non-nol tanpa penjaga mengakhiri job sebelum state disimpan."""
    body = wf("bot.yml").split("while :; do", 1)[1].split("done", 1)[0]
    for line in body.splitlines():
        s = line.strip()
        if re.match(r"^(RNT_AGENT_KEY=.*)?(timeout|python|bash)\b", s) and not s.startswith("if "):
            assert "||" in s, f"perintah tanpa penjaga: {s}"


def test_default_control_is_paper():
    c = control.read((os.path.join(ROOT, "control", "bot.yaml"),))
    assert (c.mode, c.problem) == ("paper", None)


def test_control_off_unquoted_and_garbage(tmp_path):
    p = tmp_path / "bot.yaml"
    p.write_text("mode: off\n")
    assert control.read((str(p),)).mode == "off"
    p.write_text("mode: yolo\n")
    c = control.read((str(p),))
    assert c.mode == "paper" and c.problem
    p.write_text("::: not yaml [")
    assert control.read((str(p),)).mode == "paper"


def test_control_workflow_options_match_modes():
    doc = yaml.safe_load(wf("control.yml"))
    on = doc.get("on", doc.get(True))
    assert set(on["workflow_dispatch"]["inputs"]["mode"]["options"]) - {"tetap"} == set(control.MODES)


def test_no_secret_values_in_repo():
    pat = re.compile(r"0x[0-9a-fA-F]{64}")
    for d, _, files in os.walk(ROOT):
        if any(x in d for x in (".git", "research", "__pycache__", ".pytest_cache")):
            continue
        for f in files:
            if f.endswith((".py", ".yml", ".yaml", ".md", ".json", ".txt", ".sh")):
                with open(os.path.join(d, f), encoding="utf-8", errors="ignore") as fh:
                    assert not pat.search(fh.read()), f"kemungkinan private key di {f}"


def test_gitignore_keeps_heavy_research_data_out():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        gi = fh.read()
    for x in ("research/data/", "research/results/cache/", "research/audit_2026-10-09/_*"):
        assert x in gi
