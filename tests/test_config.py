"""Config loading + default-writing tests."""

from __future__ import annotations

from pathlib import Path

from dictate.config import Config, DEFAULT_TOML, load_config, write_default_config


def test_default_config_values():
    cfg = Config()
    assert cfg.hotkey.key == "alt_r"
    assert cfg.recording.sample_rate == 16000
    assert cfg.transcription.backend == "whisper-cpp"
    assert cfg.transcription.model == "small"
    assert cfg.output.copy_to_clipboard is True
    assert cfg.output.auto_paste is False
    assert cfg.output.auto_submit is False
    assert cfg.output.submit_delay_ms == 40


def test_load_missing_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.hotkey.key == "alt_r"


def test_load_partial_merges_with_defaults(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[hotkey]\nkey = "f9"\n')
    cfg = load_config(p)
    assert cfg.hotkey.key == "f9"
    # Defaults preserved for unspecified sections
    assert cfg.transcription.model == "small"


def test_write_default_idempotent(tmp_path: Path):
    p = tmp_path / "c.toml"
    write_default_config(p)
    assert p.exists()
    original = p.read_text()
    # second write should not overwrite
    p.write_text("# customized\n[hotkey]\nkey = \"f1\"\n")
    write_default_config(p)
    assert "customized" in p.read_text()


def test_default_toml_parses(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(DEFAULT_TOML)
    cfg = load_config(p)
    assert cfg.hotkey.key == "alt_r"
    assert cfg.transcription.model == "small"


def test_load_chord_hotkey(tmp_path: Path):
    """Chord hotkey strings load verbatim from TOML."""
    p = tmp_path / "c.toml"
    p.write_text('[hotkey]\nkey = "ctrl+shift+l"\n')
    cfg = load_config(p)
    assert cfg.hotkey.key == "ctrl+shift+l"


def test_load_auto_submit_override(tmp_path: Path):
    """auto_submit + submit_delay_ms parse from TOML."""
    p = tmp_path / "c.toml"
    p.write_text('[output]\nauto_paste = true\nauto_submit = true\nsubmit_delay_ms = 120\n')
    cfg = load_config(p)
    assert cfg.output.auto_paste is True
    assert cfg.output.auto_submit is True
    assert cfg.output.submit_delay_ms == 120


def test_model_file_path():
    cfg = Config()
    cfg.transcription.model = "medium"
    cfg.paths.models_dir = "/tmp/models"
    assert str(cfg.model_file()) == "/tmp/models/ggml-medium.bin"
