from unittest.mock import MagicMock, patch
from src.knowledge.retriever import AyurvedaKnowledgeBase, get_knowledge_base
from src.models import DoshaProfile, DoshaVector, UserContext

def test_singleton_get_knowledge_base():
    with patch("src.knowledge.retriever.chromadb.PersistentClient"), \
         patch("src.knowledge.retriever.embedding_functions.SentenceTransformerEmbeddingFunction"):
        kb1 = get_knowledge_base()
        kb2 = get_knowledge_base()
        assert kb1 is kb2

def test_retriever_mock_query():
    profile = DoshaProfile(
        user_id="test_user",
        prakriti=DoshaVector(vata=0.5, pitta=0.3, kapha=0.2),
        timestamp=1000.0
    )
    context = UserContext(
        season="Winter",
        weather="Cold",
        temperature_c=10.0,
        calendar_events=[],
        self_report_symptoms=[]
    )

    with patch("src.knowledge.retriever.chromadb.PersistentClient") as mock_chroma, \
         patch("src.knowledge.retriever.embedding_functions.SentenceTransformerEmbeddingFunction"):
        
        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_collection.query.return_value = {
            "documents": [["Ayurvedic daily routine recommendation text"]],
            "distances": [[0.15]]
        }
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        kb = AyurvedaKnowledgeBase()
        results = kb.retrieve(profile, context, k=3)

        assert len(results) == 1
        assert "Ayurvedic" in results[0]["text"]
        assert results[0]["source"] == "Core Dinacharya Grounding PDF"

def test_search_query_mock():
    with patch("src.knowledge.retriever.chromadb.PersistentClient") as mock_chroma, \
         patch("src.knowledge.retriever.embedding_functions.SentenceTransformerEmbeddingFunction"):
        
        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_collection.query.return_value = {
            "documents": [["Nasya oil application guideline"]],
            "distances": [[0.22]]
        }
        mock_chroma.return_value.get_or_create_collection.return_value = mock_collection

        kb = AyurvedaKnowledgeBase()
        results = kb.search_query("Nasya", k=2)

        assert len(results) == 1
        assert "Nasya" in results[0]["text"]
        assert results[0]["score"] == 0.22
