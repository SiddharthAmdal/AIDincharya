import os
from typing import List, Dict, Any
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from chromadb.utils import embedding_functions

from src.models import DoshaProfile, UserContext

class AyurvedaKnowledgeBase:
    """
    Authentic RAG Retriever powered by ChromaDB.
    Automatically ingests all authoritative PDFs in src/knowledge/data/ with source attribution.
    """

    _shared_embedding_func = None
    _shared_chroma_client = None
    _shared_collection = None
    _ingested_check_done = False

    def __init__(self):
        # Determine paths relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(current_dir, "data")
        chroma_db_dir = os.path.join(self.data_dir, "chroma")

        os.makedirs(self.data_dir, exist_ok=True)

        if AyurvedaKnowledgeBase._shared_embedding_func is None:
            AyurvedaKnowledgeBase._shared_embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name='all-MiniLM-L6-v2'
            )
        if AyurvedaKnowledgeBase._shared_chroma_client is None:
            AyurvedaKnowledgeBase._shared_chroma_client = chromadb.PersistentClient(path=chroma_db_dir)

        self.embedding_func = AyurvedaKnowledgeBase._shared_embedding_func
        self.chroma_client = AyurvedaKnowledgeBase._shared_chroma_client

        # We get or create the collection
        if AyurvedaKnowledgeBase._shared_collection is None:
            AyurvedaKnowledgeBase._shared_collection = self.chroma_client.get_or_create_collection(
                name='grounding_rag_final',
                embedding_function=self.embedding_func
            )
        self.collection = AyurvedaKnowledgeBase._shared_collection

        # Ensure all PDFs in data_dir are ingested into ChromaDB
        if not AyurvedaKnowledgeBase._ingested_check_done:
            self._ensure_all_pdfs_ingested()
            AyurvedaKnowledgeBase._ingested_check_done = True

    def _ensure_all_pdfs_ingested(self):
        """Scans src/knowledge/data/ for all .pdf files and ingests any not yet indexed."""
        if not os.path.exists(self.data_dir):
            return

        pdf_files = sorted([
            f for f in os.listdir(self.data_dir)
            if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(self.data_dir, f))
        ])
        if not pdf_files:
            print(f"WARNING: No grounding PDFs found in {self.data_dir}")
            return

        # If collection is completely empty, ingest all PDFs
        total_count = self.collection.count()
        for fname in pdf_files:
            filepath = os.path.join(self.data_dir, fname)
            # Legacy Core_Dinacharya_Grounding.pdf chunks used ids 'id_0', 'id_1', ...
            if fname == "Core_Dinacharya_Grounding.pdf" and total_count > 0:
                existing_legacy = self.collection.get(ids=["id_0"])
                if existing_legacy and existing_legacy.get("ids"):
                    continue

            prefix = self._sanitize_id_prefix(fname)
            existing = self.collection.get(ids=[f"{prefix}_0"])
            if existing and existing.get("ids"):
                continue

            self._ingest_pdf(filepath, source_name=fname, id_prefix=prefix)

    @staticmethod
    def _sanitize_id_prefix(filename: str) -> str:
        base = os.path.splitext(filename)[0]
        return "".join(c if c.isalnum() else "_" for c in base).lower()

    def _ingest_pdf(self, filepath: str, source_name: str = None, id_prefix: str = "id"):
        raw_name = source_name or os.path.basename(filepath)
        source_label = "Core Dinacharya Grounding PDF" if raw_name == "Core_Dinacharya_Grounding.pdf" else raw_name
        print(f"Reading {filepath} ({source_label})...")
        text = ""
        try:
            pdf_reader = PdfReader(filepath)
            for page in pdf_reader.pages:
                page_txt = page.extract_text()
                if page_txt:
                    text += page_txt + "\n"
        except Exception as e:
            print(f"WARNING: Could not read PDF {filepath}: {e}")
            return

        if not text.strip():
            print(f"WARNING: PDF {filepath} yielded 0 extractable characters; skipping.")
            return

        print(f"Extracted {len(text)} characters from {source_label}. Chunking...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(text)

        if not chunks:
            return

        print(f"Adding {len(chunks)} chunks from {source_label} to ChromaDB...")
        ids = [f"{id_prefix}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": source_label, "chunk_index": i} for i in range(len(chunks))]
        self.collection.add(
            documents=chunks,
            ids=ids,
            metadatas=metadatas
        )
        print(f"Ingestion of {source_label} complete.")

    def retrieve_by_query(
        self,
        query: str,
        k: int = 5,
        applicable_doshas: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes a semantic search query against ChromaDB and returns attributed guidelines.
        """
        print(f"[RAG] Querying ChromaDB with: '{query}'")
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "metadatas", "distances"]
            )

            retrieved_results = []
            if results and "documents" in results and len(results["documents"]) > 0:
                docs = results["documents"][0]
                metas = (results.get("metadatas") or [[]])[0]
                dists = (results.get("distances") or [[]])[0]
                for idx, doc in enumerate(docs):
                    meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
                    dist = dists[idx] if idx < len(dists) and dists[idx] is not None else 0.0
                    source = meta.get("source") or "Core Dinacharya Grounding PDF"
                    if source == "Core_Dinacharya_Grounding.pdf":
                        source = "Core Dinacharya Grounding PDF"
                    score = round(max(0.0, 1.0 / (1.0 + float(dist))), 4)
                    retrieved_results.append({
                        "text": doc,
                        "source": source,
                        "score": score,
                        "applicable_doshas": applicable_doshas if applicable_doshas else ["vata", "pitta", "kapha"],
                        "contraindications": []
                    })
            return retrieved_results
        except Exception as e:
            print(f"RAG Retrieval Error: {e}")
            return []

    def retrieve(self, profile: DoshaProfile, context: UserContext, k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves the top-k most relevant guidelines from the Grounding PDFs using semantic search.
        Constructs a query based on the user's Dosha imbalances and context.
        """
        aggravated = []
        if profile.vikriti_flags.vata_aggravated:
            aggravated.append("Vata")
        if profile.vikriti_flags.pitta_aggravated:
            aggravated.append("Pitta")
        if profile.vikriti_flags.kapha_aggravated:
            aggravated.append("Kapha")

        query_parts = ["Ayurvedic daily routine and practices (Dinacharya)"]

        if aggravated:
            query_parts.append(f"to balance and ground aggravated {' and '.join(aggravated)} dosha")
        else:
            p = profile.prakriti
            scores = {"Vata": p.vata, "Pitta": p.pitta, "Kapha": p.kapha}
            primary = max(scores, key=scores.get)
            query_parts.append(f"suitable for {primary} dominant body type")

        if context.season:
            query_parts.append(f"during the {context.season} season")

        if getattr(context, "self_report_symptoms", None):
            syms = ", ".join(context.self_report_symptoms)
            if syms:
                query_parts.append(f"contraindications and guidelines for {syms}")

        query = " ".join(query_parts)
        dosha_tags = aggravated if aggravated else ["vata", "pitta", "kapha"]
        return self.retrieve_by_query(query, k=k, applicable_doshas=dosha_tags)

    def retrieve_for_reschedule(
        self,
        activity_name: str,
        proposed_slot: str,
        adjacent_context: str = "",
        profile: DoshaProfile = None,
        k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves targeted Ayurvedic & Yogic grounding passages for validating a schedule change.
        Combines activity-specific rules, meal/bath/sleep temporal spacing rules, and circadian context.
        """
        dosha_str = ""
        dosha_tags = ["vata", "pitta", "kapha"]
        if profile:
            aggravated = []
            if profile.vikriti_flags.vata_aggravated:
                aggravated.append("Vata")
            if profile.vikriti_flags.pitta_aggravated:
                aggravated.append("Pitta")
            if profile.vikriti_flags.kapha_aggravated:
                aggravated.append("Kapha")
            if aggravated:
                dosha_str = f"for {'/'.join(aggravated)} aggravation"
                dosha_tags = [d.lower() for d in aggravated]

        # Build two focused semantic queries to cover both general practice guidelines and meal/sequence rules
        q1 = (
            f"Guidelines, timing rules, and contraindications for {activity_name} at {proposed_slot} "
            f"{adjacent_context} {dosha_str} empty stomach before practice after practice meal bath digestion"
        ).strip()
        q2 = (
            f"Dinacharya Ratricharya daily routine sequence {activity_name} bhuktavastu ajirna "
            f"after having food meal gap bath exercise pranayama sleep time"
        ).strip()

        results_1 = self.retrieve_by_query(q1, k=max(3, k - 2), applicable_doshas=dosha_tags)
        results_2 = self.retrieve_by_query(q2, k=3, applicable_doshas=dosha_tags)

        # Deduplicate preserving order
        seen = set()
        merged = []
        for item in results_1 + results_2:
            txt_key = item["text"][:150]
            if txt_key not in seen:
                seen.add(txt_key)
                merged.append(item)
            if len(merged) >= k:
                break
        return merged

    def query_text(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Direct semantic retrieval for arbitrary text queries against ChromaDB collection.
        Returns retrieved document chunks with metadata and distances.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "distances"]
            )
            retrieved = []
            if results and 'documents' in results and len(results['documents']) > 0:
                docs = results['documents'][0]
                dists = results['distances'][0] if 'distances' in results and results['distances'] else [0.0]*len(docs)
                ids = results['ids'][0] if 'ids' in results and results['ids'] else [f"id_{i}" for i in range(len(docs))]
                for doc_id, doc, dist in zip(ids, docs, dists):
                    retrieved.append({
                        "id": doc_id,
                        "text": doc,
                        "distance": dist,
                        "source": "Core Dinacharya Grounding PDF"
                    })
            return retrieved
        except Exception as e:
            print(f"RAG query_text Error: {e}")
            return []

