import sys
from types import SimpleNamespace

import numpy as np
import pytest

from core.index.embeddings import LocalEmbeddingProvider, get_embedding_provider, hash_embeddings


def test_backend_configuration(monkeypatch):
    assert get_embedding_provider() is hash_embeddings
    monkeypatch.delenv("EMBEDDING_BACKEND")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    provider = get_embedding_provider()
    assert isinstance(provider, LocalEmbeddingProvider)
    assert provider.model_name == "BAAI/bge-small-zh-v1.5"
    monkeypatch.setenv("EMBEDDING_BACKEND", "invalid")
    with pytest.raises(ValueError, match="EMBEDDING_BACKEND"):
        get_embedding_provider()


@pytest.mark.parametrize("cuda,override,expected", [(True, None, "cuda"), (False, None, "cpu"),
                                                    (True, "cpu", "cpu"), (False, "cuda:0", "cuda:0")])
def test_local_device_without_real_model(monkeypatch, cuda, override, expected):
    calls = []

    class FakeModel:
        def __init__(self, name, **kwargs):
            calls.append((name, kwargs))

        def encode(self, texts, **kwargs):
            assert kwargs["convert_to_numpy"] and kwargs["normalize_embeddings"]
            return np.ones((len(texts), 3))

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: cuda)))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeModel))
    monkeypatch.delenv("EMBED_DEVICE", raising=False)
    if override:
        monkeypatch.setenv("EMBED_DEVICE", override)
    monkeypatch.setenv("EMBEDDING_MODEL", "synthetic-model")
    provider = LocalEmbeddingProvider()
    assert not calls  # Lazy, no download or GPU access in tests.
    assert provider(["营业收入"]).shape == (1, 3)
    provider(["第二次调用"])
    assert calls == [("synthetic-model", {"device": expected, "local_files_only": True})]


def test_missing_optional_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    with pytest.raises(RuntimeError, match="embedding"):
        LocalEmbeddingProvider()(["营业收入"])
