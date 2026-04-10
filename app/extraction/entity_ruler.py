import json
from pathlib import Path

from spacy.language import Language


def load_entity_ruler(nlp: Language, patterns_dir: str = "data/patterns") -> Language:
    """Add EntityRuler with oncology patterns to the spaCy pipeline."""
    ruler = nlp.add_pipe("entity_ruler", before="ner")
    patterns = []
    patterns_path = Path(patterns_dir)
    if patterns_path.exists():
        for pattern_file in sorted(patterns_path.glob("*.jsonl")):
            with open(pattern_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(json.loads(line))
    ruler.add_patterns(patterns)
    return nlp
