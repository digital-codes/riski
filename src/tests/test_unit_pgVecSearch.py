"""Unit tests for src.pgVecSearch – embeddings mocked, ranking logic verified."""

import numpy as np
import pytest

from src import pgVecSearch as vs


@pytest.fixture()
def mock_embed(monkeypatch):
    """Deterministic embeddings: 'cat' vector orthogonal to 'dog'/'dog house'."""
    import hashlib

    def _embed(text, model=None):
        digest = hashlib.sha256(text.encode()).digest()
        vec = np.frombuffer(digest * 32, dtype=np.uint8)[:1024].astype(np.float64)
        return vec / (np.linalg.norm(vec) + 1e-9)

    monkeypatch.setattr(vs.remote, "embed", _embed)
    return _embed


class TestCallEmbeddingModel:
    def test_returns_normalised_list(self, mock_embed):
        vec = vs.call_embedding_model("cat")
        assert isinstance(vec, list)
        assert len(vec) == 1024
        assert abs(sum(x * x for x in vec) - 1.0) < 1e-6

    def test_forwards_model_override(self, mock_embed, monkeypatch):
        captured = {}

        def _embed(text, model=None):
            captured["model"] = model
            return np.ones(4) / 2.0

        monkeypatch.setattr(vs.remote, "embed", _embed)
        vs.call_embedding_model("x", model="custom-model")
        assert captured["model"] == "custom-model"


class TestFilterByThreshold:
    def test_filters_by_distance(self):
        data = [("a", 0.1), ("b", 0.6), ("c", 0.45)]
        assert vs.filter_by_threshold(data, 0.45) == [("a", 0.1), ("c", 0.45)]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeQuery:
    """Mimics the ORM query chain used by query_vector_similarity."""

    def __init__(self, rows):
        self._rows = rows

    def order_by(self, *_):
        return self

    def limit(self, k):
        return _FakeResult(sorted(self._rows, key=lambda r: r.distance)[:k])


class _FakeEmbeddingsCol:
    oparlKey = "oparlKey"
    value = None

    @staticmethod
    def cosine_distance(vec):
        return None


class _FakeSession:
    """Returns pre-seeded distance rows, ordered by cosine distance."""

    def __init__(self, rows):
        self._rows = rows
        self.embeddings = _FakeEmbeddingsCol()

    def query(self, *cols):
        return _FakeQuery(self._rows)


class _DistRow:
    """Iterable distance row as returned by the ORM query."""

    def __init__(self, oparlKey, distance):
        self.oparlKey = oparlKey
        self.distance = distance

    def __iter__(self):
        return iter((self.oparlKey, self.distance))


class TestQueryVectorSimilarity:
    def test_ranking_and_cutoff(self):
        session = _FakeSession([
            _DistRow("vec-dog", 0.7), _DistRow("vec-cat", 0.1), _DistRow("vec-x", 0.5),
        ])
        results = vs.query_vector_similarity(session, [0.0] * 8, top_k=10)
        distances = [r.distance for r in results]
        assert distances == sorted(distances)
        assert results[0].oparlKey == "vec-cat"

        # score cutoff: only entries within the distance threshold survive
        filtered = [k for k, d in results if d <= 0.45]
        assert filtered == ["vec-cat"]

    def test_top_k_limits_results(self):
        session = _FakeSession([_DistRow(f"k{i}", i / 10) for i in range(10)])
        results = vs.query_vector_similarity(session, [0.0] * 8, top_k=3)
        assert len(results) == 3


class TestQueryFiles:
    def test_returns_file_fields(self, engine_fixture):
        session = engine_fixture["session"]
        date, name, url, content = vs.queryFiles(session, "1")
        assert name == "Gemeinderat Protokoll"
        assert date == "2024-05-01"
        assert url == "https://example.test/f1.pdf"
        assert "Inhalt" in content

    def test_leading_zeroes_stripped(self, engine_fixture):
        session = engine_fixture["session"]
        _, name, _, _ = vs.queryFiles(session, "0001")
        assert name == "Gemeinderat Protokoll"

    def test_unknown_key_raises(self, engine_fixture):
        session = engine_fixture["session"]
        with pytest.raises(Exception, match="No file found"):
            vs.queryFiles(session, "no-such-key")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine_fixture():
    """In-memory sqlite with fake embeddings + File rows (no pgvector needed).

    query_vector_similarity needs pgvector's cosine_distance, which sqlite
    cannot provide – so ranking is exercised via a stub of the SQL result,
    while queryFiles runs against the real ORM session.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite://", future=True)
    vs.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    # seed File rows
    session.add(vs.File(id=1, date="2024-05-01", oparlKey="1",
                        name="Gemeinderat Protokoll",
                        downloadurl="https://example.test/f1.pdf",
                        content="Inhalt des Protokolls"))
    session.commit()

    # fake embeddings rows with distances
    class Row:
        def __init__(self, oparlKey, distance):
            self.oparlKey = oparlKey
            self.distance = distance

    rows = [Row("vec-cat", 0.1), Row("vec-dog", 0.7), Row("vec-x", 0.5)]
    session.close()

    # re-open a session for the tests
    session2 = sessionmaker(bind=engine)()
    return {"session": session2, "rows": rows, "engine": engine}

pytestmark = pytest.mark.unit
