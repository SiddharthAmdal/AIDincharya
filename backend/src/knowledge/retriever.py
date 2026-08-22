import os
from typing import List, Dict, Any
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.utils import embedding_functions

from src.models import DoshaProfile, UserContext

_kb_instance = None

def get_knowledge_base() -> "AyurvedaKnowledgeBase":
    """Singleton getter to prevent expensive re-initialization of SentenceTransformer and ChromaDB."""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = AyurvedaKnowledgeBase()
    return _kb_instance


class AyurvedaKnowledgeBase:
    """
    Authentic RAG Retriever powered by ChromaDB.
    """

    def __init__(self):
        # Determine paths relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(current_dir, "data")
        pdf_path = os.path.join(data_dir, "Core_Dinacharya_Grounding.pdf")
        chroma_db_dir = os.path.join(data_dir, "chroma")

        os.makedirs(data_dir, exist_ok=True)

        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='all-MiniLM-L6-v2')
        self.chroma_client = chromadb.PersistentClient(path=chroma_db_dir)
        
        # We get or create the collection
        self.collection = self.chroma_client.get_or_create_collection(
            name='grounding_rag_final', 
            embedding_function=self.embedding_func
        )

        # Check if we need to ingest the PDF
        if self.collection.count() == 0:
            print("ChromaDB is empty. Ingesting Grounding PDF...")
            if os.path.exists(pdf_path):
                self._ingest_pdf(pdf_path)
            else:
                print(f"WARNING: Grounding PDF not found at {pdf_path}")

    def _ingest_pdf(self, filepath: str):
        print(f"Reading {filepath}...")
        text = ""
        pdf_reader = PdfReader(filepath)
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
            
        print(f"Extracted {len(text)} characters. Chunking...")
        if not text.strip():
            print("WARNING: No text extracted from PDF.")
            return

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(text)
        
        print(f"Adding {len(chunks)} chunks to ChromaDB...")
        self.collection.upsert(
            documents=chunks,
            ids=[f'id_{i}' for i in range(len(chunks))]
        )
        print("Ingestion complete.")

    def search_query(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Direct text search endpoint over the knowledge base."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=k
            )
            retrieved = []
            if results and 'documents' in results and len(results['documents']) > 0:
                docs = results['documents'][0]
                distances = results.get('distances', [[]])[0] if 'distances' in results else []
                for idx, doc in enumerate(docs):
                    score = float(distances[idx]) if idx < len(distances) else 1.0
                    retrieved.append({
                        "text": doc,
                        "source": "Core Dinacharya Grounding PDF",
                        "score": round(score, 4)
                    })
            return retrieved
        except Exception as e:
            print(f"Knowledge Base Search Error: {e}")
            return []

    def retrieve(self, profile: DoshaProfile, context: UserContext, k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves the top-k most relevant guidelines from the Grounding PDF using semantic search.
        Constructs a query based on the user's Dosha imbalances and context.
        """
        # Formulate query based on Dosha and Vikriti
        aggravated = []
        if profile.vikriti_flags.vata_aggravated: aggravated.append("Vata")
        if profile.vikriti_flags.pitta_aggravated: aggravated.append("Pitta")
        if profile.vikriti_flags.kapha_aggravated: aggravated.append("Kapha")

        query_parts = ["Ayurvedic daily routine and practices (Dinacharya)"]
        
        if aggravated:
            query_parts.append(f"to balance and ground aggravated {' and '.join(aggravated)} dosha")
        else:
            # Fallback to prakriti
            p = profile.prakriti
            scores = {"Vata": p.vata, "Pitta": p.pitta, "Kapha": p.kapha}
            primary = max(scores, key=scores.get)
            query_parts.append(f"suitable for {primary} dominant body type")

        if context.season:
            query_parts.append(f"during the {context.season} season")

        query = " ".join(query_parts)
        print(f"[RAG] Querying ChromaDB with: '{query}'")

        try:
            results = self.collection.query(
                query_texts=[query], 
                n_results=k
            )
            
            retrieved_results = []
            if results and 'documents' in results and len(results['documents']) > 0:
                docs = results['documents'][0]
                for doc in docs:
                    retrieved_results.append({
                        "text": doc,
                        "source": "Core Dinacharya Grounding PDF",
                        "score": 1.0,
                        "applicable_doshas": aggravated if aggravated else ["vata", "pitta", "kapha"],
                        "contraindications": []
                    })
            return retrieved_results
            
        except Exception as e:
            print(f"RAG Retrieval Error: {e}")
            return []

