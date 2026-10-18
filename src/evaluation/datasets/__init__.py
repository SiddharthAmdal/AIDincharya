"""Versioned Evaluation Datasets Package"""
import os
import json
from typing import List, Dict, Any

DATASETS_DIR = os.path.dirname(os.path.abspath(__file__))

def load_dataset(dataset_name: str, version: str = "v1") -> List[Dict[str, Any]]:
    """Loads a versioned JSON evaluation dataset."""
    filename = f"{dataset_name}_eval_{version}.json"
    file_path = os.path.join(DATASETS_DIR, version, filename)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Evaluation dataset not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
