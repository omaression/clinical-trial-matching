import re
import uuid

import spacy
from spacy.language import Language

from app.config import settings
from app.extraction.abbreviation_resolver import AbbreviationResolver
from app.extraction.criteria_classifier import RuleBasedClassifier
from app.extraction.entity_ruler import load_entity_ruler
from app.extraction.section_splitter import SectionSplitter
from app.extraction.types import ClassifiedCriterion, CriterionText, Entity, PipelineResult


class ExtractionPipeline:
    """Orchestrates the 6-stage NLP extraction pipeline."""

    def __init__(self, nlp: Language | None = None, loaded_model_name: str | None = None):
        if nlp is None:
            nlp, loaded_model_name = self._load_nlp()
        self._nlp = nlp
        self.loaded_model_name = loaded_model_name or settings.spacy_model
        self._splitter = SectionSplitter()
        self._abbreviation_resolver = AbbreviationResolver(settings.abbreviation_dict_path)
        self._classifier = RuleBasedClassifier()

    def _load_nlp(self) -> tuple[Language, str]:
        try:
            nlp = spacy.load(settings.spacy_model)
            loaded_model_name = settings.spacy_model
        except OSError:
            nlp = spacy.load("en_core_web_sm")
            loaded_model_name = "en_core_web_sm (fallback)"
        nlp = self._add_abbreviation_detector(nlp)
        nlp = load_entity_ruler(nlp, settings.patterns_dir)
        return nlp, loaded_model_name

    def _add_abbreviation_detector(self, nlp: Language) -> Language:
        if "abbreviation_detector" in nlp.pipe_names:
            return nlp
        try:
            from scispacy.abbreviation import AbbreviationDetector  # noqa: F401
        except ImportError:
            return nlp
        nlp.add_pipe("abbreviation_detector")
        detector = nlp.get_pipe("abbreviation_detector")
        global_matcher = getattr(detector, "global_matcher", None)
        # Some SciSpaCy installs register the component with an empty matcher, which only emits warnings.
        if global_matcher is not None and len(global_matcher) == 0:
            nlp.remove_pipe("abbreviation_detector")
        return nlp

    def extract(self, eligibility_text: str) -> PipelineResult:
        # Stage 1: Section Splitter
        criterion_texts = self._splitter.split(eligibility_text)

        criteria: list[ClassifiedCriterion] = []
        for ct in criterion_texts:
            criteria.extend(self._extract_criterion(ct))

        return PipelineResult(criteria=criteria, pipeline_version=settings.pipeline_version)

    def _extract_criterion(self, ct: CriterionText, *, allow_decompose: bool = True) -> list[ClassifiedCriterion]:
        entities = self._extract_entities(ct.text)
        classified = self._classifier.classify(ct.text, entities)
        classified = classified.model_copy(update={
            "type": ct.type,
            "review_required": classified.review_required or ct.review_required,
            "review_reason": classified.review_reason or ct.review_reason,
        })

        if not allow_decompose:
            return [classified]

        split_clauses = self._split_compound_criterion(classified)
        if not split_clauses:
            return [classified]

        shared_group_id = classified.logic_group_id or str(uuid.uuid4())
        split_criteria: list[ClassifiedCriterion] = []
        for clause in split_clauses:
            derived = self._extract_criterion(
                CriterionText(
                    text=clause,
                    type=ct.type,
                    review_required=ct.review_required,
                    review_reason=ct.review_reason,
                ),
                allow_decompose=False,
            )[0]
            derived = derived.model_copy(update={
                "logic_group_id": shared_group_id,
                "logic_operator": classified.logic_operator,
            })
            split_criteria.append(derived)
        return split_criteria

    def _extract_entities(self, criterion_text: str) -> list[Entity]:
        doc = self._nlp(criterion_text)
        entities = [
            Entity(text=ent.text, label=ent.label_, start=ent.start_char, end=ent.end_char)
            for ent in doc.ents
        ]
        dynamic_abbreviations = {}
        doc_extensions = getattr(doc._, "abbreviations", None)
        if doc_extensions:
            dynamic_abbreviations = {
                abbreviation.text.lower(): str(abbreviation._.long_form)
                for abbreviation in doc._.abbreviations
                if getattr(abbreviation._, "long_form", None)
            }

        entities = self._abbreviation_resolver.resolve(
            entities,
            criterion_text,
            dynamic_abbreviations=dynamic_abbreviations,
        )
        return self._suppress_redundant_entities(entities)

    def _split_compound_criterion(self, criterion: ClassifiedCriterion) -> list[str] | None:
        if criterion.category not in {"diagnosis", "cns_metastases"}:
            return None

        previous_history_split = self._split_previous_history_clause(criterion.original_text)
        if previous_history_split:
            return previous_history_split

        return self._split_entity_coordinated_clause(criterion.original_text, criterion.entities)

    def _split_previous_history_clause(self, text: str) -> list[str] | None:
        match = re.match(
            r"^(?P<lemma>\*?\s*(?:has|have))\s+(?P<left>.+?)\s+or\s+(?P<right>previous history of .+)$",
            text,
            re.I,
        )
        if not match:
            return None
        return [
            f"{match.group('lemma')} {match.group('left').strip()}",
            f"{match.group('lemma')} {match.group('right').strip()}",
        ]

    def _split_entity_coordinated_clause(self, text: str, entities: list[Entity]) -> list[str] | None:
        disease_entities = [entity for entity in entities if entity.label == "DISEASE"]
        if len(disease_entities) != 2:
            return None

        for left, right in zip(disease_entities, disease_entities[1:]):
            connector = text[left.end:right.start]
            if not re.fullmatch(r"\s*(?:and/or|or)\s*", connector, re.I):
                continue
            prefix = text[:left.start]
            suffix = text[right.end:]
            left_clause = f"{prefix}{left.text}{suffix}".strip()
            right_clause = f"{prefix}{right.text}{suffix}".strip()
            if left_clause == text or right_clause == text:
                continue
            return [left_clause, right_clause]
        return None

    def _suppress_redundant_entities(self, entities: list[Entity]) -> list[Entity]:
        filtered: list[Entity] = []
        for entity in entities:
            if self._is_subsumed_entity(entity, entities):
                continue
            filtered.append(entity)
        return filtered

    def _is_subsumed_entity(self, entity: Entity, entities: list[Entity]) -> bool:
        entity_tokens = _entity_tokens(entity)
        if not entity_tokens:
            return False

        for other in entities:
            if other is entity:
                continue
            other_tokens = _entity_tokens(other)
            if len(other_tokens) <= len(entity_tokens):
                continue
            if not entity_tokens.issubset(other_tokens):
                continue
            if entity.label == "DISEASE" and other.label in {"DISEASE", "BIOMARKER"}:
                return True
            if entity.label == other.label and entity.label in {"BIOMARKER", "DRUG", "LAB_TEST"}:
                return True
        return False


def _entity_tokens(entity: Entity) -> set[str]:
    source = entity.expanded_text or entity.text
    normalized = "".join(char.lower() if char.isalnum() else " " for char in source)
    return {token for token in normalized.split() if token}
