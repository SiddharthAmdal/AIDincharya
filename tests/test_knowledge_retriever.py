"""
Automated Test Suite for AyurvedaKnowledgeBase & ChromaDB RAG Retrieval
Validates semantic search, season queries, Dosha/Prakriti routing, top-k limits, and resilience.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from src.knowledge.retriever import AyurvedaKnowledgeBase
from src.models import DoshaProfile, DoshaVector, VikritiFlags, UserContext


@pytest.fixture(scope="module")
def knowledge_base():
    """Shared knowledge base fixture for the test module."""
    return AyurvedaKnowledgeBase()


class TestAyurvedaKnowledgeRetriever:
    """Test suite covering ChromaDB RAG retrieval functionality."""

    def test_knowledge_base_singleton_initialization(self, knowledge_base):
        """Verify knowledge base properly initializes ChromaDB collection and embeddings."""
        assert knowledge_base.collection is not None
        assert knowledge_base.embedding_func is not None
        doc_count = knowledge_base.collection.count()
        assert doc_count > 0, "ChromaDB collection should contain ingested grounding documents."

    def test_retrieve_vata_aggravation(self, knowledge_base):
        """Verify query formulated for Vata aggravation returns relevant guidance."""
        profile = DoshaProfile(
            user_id="test_vata",
            prakriti=DoshaVector(vata=0.33, pitta=0.33, kapha=0.34),
            vikriti_flags=VikritiFlags(vata_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season="Hemanta",
            weather="Cold and windy",
            temperature_c=12.0
        )

        results = knowledge_base.retrieve(profile, context, k=3)
        assert len(results) > 0
        assert len(results) <= 3
        first_doc = results[0]
        assert "text" in first_doc and len(first_doc["text"]) > 0
        assert "Vata" in first_doc["applicable_doshas"]

    def test_retrieve_pitta_aggravation(self, knowledge_base):
        """Verify query formulated for Pitta aggravation returns cooling/soothing guidance."""
        profile = DoshaProfile(
            user_id="test_pitta",
            prakriti=DoshaVector(vata=0.2, pitta=0.6, kapha=0.2),
            vikriti_flags=VikritiFlags(pitta_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season="Grishma",
            weather="Hot and arid",
            temperature_c=36.0
        )

        results = knowledge_base.retrieve(profile, context, k=3)
        assert len(results) > 0
        assert "Pitta" in results[0]["applicable_doshas"]

    def test_retrieve_kapha_aggravation(self, knowledge_base):
        """Verify query formulated for Kapha aggravation returns stimulating/warming guidance."""
        profile = DoshaProfile(
            user_id="test_kapha",
            prakriti=DoshaVector(vata=0.2, pitta=0.2, kapha=0.6),
            vikriti_flags=VikritiFlags(kapha_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season="Vasanta",
            weather="Damp and cool",
            temperature_c=18.0
        )

        results = knowledge_base.retrieve(profile, context, k=3)
        assert len(results) > 0
        assert "Kapha" in results[0]["applicable_doshas"]

    def test_retrieve_dual_aggravation(self, knowledge_base):
        """Verify query handles simultaneous dual dosha elevation (Vata + Pitta)."""
        profile = DoshaProfile(
            user_id="test_dual",
            prakriti=DoshaVector(vata=0.4, pitta=0.4, kapha=0.2),
            vikriti_flags=VikritiFlags(vata_aggravated=True, pitta_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season="Sharad",
            weather="Sunny and dry",
            temperature_c=25.0
        )

        results = knowledge_base.retrieve(profile, context, k=3)
        assert len(results) > 0
        doshas = results[0]["applicable_doshas"]
        assert "Vata" in doshas and "Pitta" in doshas

    def test_retrieve_prakriti_fallback_when_balanced(self, knowledge_base):
        """Verify when no Vikriti flags are active, retriever falls back to dominant Prakriti."""
        profile = DoshaProfile(
            user_id="test_balanced",
            prakriti=DoshaVector(vata=0.15, pitta=0.70, kapha=0.15),
            vikriti_flags=VikritiFlags(),  # No aggravation
            timestamp=time.time()
        )
        context = UserContext(
            season="Vasanta",
            weather="Mild and pleasant",
            temperature_c=22.0
        )

        results = knowledge_base.retrieve(profile, context, k=3)
        assert len(results) > 0
        assert results[0]["source"] == "Core Dinacharya Grounding PDF"
        # When falling back to prakriti, applicable doshas defaults to all three
        assert "pitta" in results[0]["applicable_doshas"] or "Pitta" in results[0]["applicable_doshas"]

    @pytest.mark.parametrize("season_name,weather,temp", [
        ("Hemanta (Early Winter)", "Cold and crisp", 10.0),
        ("Shishira (Late Winter)", "Freezing and dry", 4.0),
        ("Vasanta (Spring)", "Mild and floral", 20.0),
        ("Grishma (Summer)", "Blistering sunshine", 38.0),
        ("Varsha (Monsoon)", "Heavy downpour and humid", 26.0),
        ("Sharad (Autumn)", "Clear skies and moderate heat", 28.0),
    ])
    def test_retrieve_all_six_classical_seasons(self, knowledge_base, season_name, weather, temp):
        """Verify retrieval executes correctly across all 6 classical Ayurvedic Ritus."""
        profile = DoshaProfile(
            user_id="test_seasons",
            prakriti=DoshaVector(vata=0.34, pitta=0.33, kapha=0.33),
            vikriti_flags=VikritiFlags(vata_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season=season_name,
            weather=weather,
            temperature_c=temp
        )

        results = knowledge_base.retrieve(profile, context, k=2)
        assert len(results) > 0
        assert len(results) <= 2
        assert isinstance(results[0]["text"], str)

    @pytest.mark.parametrize("k", [1, 3, 5])
    def test_retrieve_top_k_limits(self, knowledge_base, k):
        """Verify retriever respects top-k boundary constraints."""
        profile = DoshaProfile(
            user_id="test_k",
            prakriti=DoshaVector(vata=0.33, pitta=0.33, kapha=0.34),
            vikriti_flags=VikritiFlags(kapha_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season="Shishira",
            weather="Cold",
            temperature_c=8.0
        )

        results = knowledge_base.retrieve(profile, context, k=k)
        assert len(results) == k

    def test_retrieve_schema_contract(self, knowledge_base):
        """Verify the returned document structure adheres strictly to the expected schema."""
        profile = DoshaProfile(
            user_id="test_contract",
            prakriti=DoshaVector(vata=0.5, pitta=0.25, kapha=0.25),
            vikriti_flags=VikritiFlags(vata_aggravated=True),
            timestamp=time.time()
        )
        context = UserContext(
            season="Hemanta",
            weather="Cold",
            temperature_c=11.0
        )

        results = knowledge_base.retrieve(profile, context, k=3)
        assert len(results) > 0
        for item in results:
            assert "text" in item
            assert "source" in item
            assert "score" in item
            assert "applicable_doshas" in item
            assert "contraindications" in item
            assert isinstance(item["text"], str)
            assert item["source"] == "Core Dinacharya Grounding PDF"
            assert isinstance(item["applicable_doshas"], list)
            assert isinstance(item["contraindications"], list)

    def test_retrieval_resilience_on_exception(self, knowledge_base):
        """Verify retriever handles unexpected ChromaDB exceptions gracefully without crashing."""
        profile = DoshaProfile(
            user_id="test_fail",
            prakriti=DoshaVector(vata=0.33, pitta=0.33, kapha=0.34),
            vikriti_flags=VikritiFlags(),
            timestamp=time.time()
        )
        context = UserContext(
            season="Vasanta",
            weather="Normal",
            temperature_c=22.0
        )

        with patch.object(knowledge_base.collection, "query", side_effect=RuntimeError("Simulated ChromaDB error")):
            results = knowledge_base.retrieve(profile, context, k=3)
            assert results == [], "Retriever should safely return an empty list upon error."
