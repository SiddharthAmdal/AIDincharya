"""
AI Dincharya RAG and Agent Evaluation Framework Package.
"""
from .evaluator import EvaluationEngine
from .datasets import load_dataset

__all__ = [
    "EvaluationEngine",
    "load_dataset",
]
