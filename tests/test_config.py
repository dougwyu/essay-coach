import importlib, os, sys


def _reload_config(env):
    for mod in list(sys.modules.keys()):
        if "config" in mod:
            del sys.modules[mod]
    os.environ.update(env)
    import config
    return config


def test_defaults(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = _reload_config({})
    assert cfg.LLM_BACKEND == "anthropic"
    assert cfg.OLLAMA_BASE_URL == "http://ollama:11434"
    assert cfg.OLLAMA_MODEL == "llama3.3:70b"
    assert cfg.DATABASE_URL == ""


def test_ollama_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "phi4:14b")
    cfg = _reload_config({})
    assert cfg.LLM_BACKEND == "ollama"
    assert cfg.OLLAMA_MODEL == "phi4:14b"
