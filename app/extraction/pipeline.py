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

_LONG_FORM_DRUG_PATTERNS = (
    re.compile(
        r"programmed\s+death(?:-|\s+)ligand\s+1\s*\(\s*PD(?:-|\s*)L1\s*\)\s*therapy",
        re.I,
    ),
)
_PROGRESSION_AFTER_RECEIVING_PATTERN = re.compile(
    r"^(?P<prefix>.*?\b(?:documented\s+disease\s+progression|disease\s+progression|progression)\b.*?\bafter\b\s+\b(?:receiving|receipt\s+of)\b)\s+(?P<tail>.+)$",
    re.I,
)
_FOLLOWING_TYPES_PATTERN = re.compile(
    r"^(?P<prefix>.*?)(?P<intro>\b(?:of\s+the\s+following\s+types|following\s+types|following\s+histologies)\s*:)\s*"
    r"(?P<items>.+?)(?P<tail>,?\s*(?:who|that)\b.+)$",
    re.I | re.S,
)
_ENUMERATION_CONNECTOR_PATTERN = re.compile(r"\s*(?:,\s*|\bor\b\s*|\band/or\b\s*)", re.I)


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
        for ct in self._decompose_atomic_criteria(criterion_texts):
            criteria.extend(self._extract_criterion(ct))

        return PipelineResult(criteria=criteria, pipeline_version=settings.pipeline_version)

    def _extract_criterion(self, ct: CriterionText, *, allow_decompose: bool = True) -> list[ClassifiedCriterion]:
        entities = self._extract_entities(ct.text)
        classified = self._classifier.classify(ct.text, entities)
        classified = classified.model_copy(update={
            "source_sentence": ct.source_sentence or ct.text,
            "source_clause_text": ct.source_clause_text or ct.text,
            "type": ct.type,
            "review_required": classified.review_required or ct.review_required,
            "review_reason": classified.review_reason or ct.review_reason,
            "logic_group_id": ct.logic_group_id or classified.logic_group_id,
            "logic_operator": ct.logic_operator or classified.logic_operator,
        })

        if not allow_decompose:
            return [classified]

        split_result = self._split_compound_criterion(classified)
        if not split_result:
            return [classified]
        split_clauses, logic_operator = split_result

        shared_group_id = classified.logic_group_id or str(uuid.uuid4())
        split_criteria: list[ClassifiedCriterion] = []
        for clause in split_clauses:
            derived = self._extract_criterion(
                CriterionText(
                    text=clause,
                    type=ct.type,
                    review_required=ct.review_required,
                    review_reason=ct.review_reason,
                    source_sentence=ct.source_sentence or ct.text,
                    source_clause_text=clause,
                ),
                allow_decompose=False,
            )[0]
            derived = derived.model_copy(update={
                "logic_group_id": shared_group_id,
                "logic_operator": logic_operator,
            })
            split_criteria.append(derived)
        return split_criteria

    def _decompose_atomic_criteria(self, criterion_texts: list[CriterionText]) -> list[CriterionText]:
        decomposed: list[CriterionText] = []
        for criterion in criterion_texts:
            split = self._split_progression_after_receiving(criterion)
            if split:
                decomposed.extend(split)
                continue
            split = self._split_following_types_enumeration(criterion)
            if split:
                decomposed.extend(split)
                continue
            decomposed.append(
                criterion.model_copy(
                    update={"source_clause_text": criterion.source_clause_text or criterion.text}
                )
            )
        return decomposed

    def _extract_entities(self, criterion_text: str) -> list[Entity]:
        doc = self._nlp(criterion_text)
        entities = [
            Entity(text=ent.text, label=ent.label_, start=ent.start_char, end=ent.end_char)
            for ent in doc.ents
        ]
        entities = self._augment_missing_entities(criterion_text, entities)
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

    def _augment_missing_entities(self, criterion_text: str, entities: list[Entity]) -> list[Entity]:
        augmented = list(entities)
        for pattern in _LONG_FORM_DRUG_PATTERNS:
            for match in pattern.finditer(criterion_text):
                if self._has_overlapping_label(augmented, "DRUG", match.start(), match.end()):
                    continue
                augmented.append(
                    Entity(
                        text=match.group(0),
                        label="DRUG",
                        start=match.start(),
                        end=match.end(),
                    )
                )
        return augmented

    def _has_overlapping_label(self, entities: list[Entity], label: str, start: int, end: int) -> bool:
        for entity in entities:
            if entity.label != label:
                continue
            if max(start, entity.start) < min(end, entity.end):
                return True
        return False

    def _split_compound_criterion(self, criterion: ClassifiedCriterion) -> tuple[list[str], str] | None:
        if criterion.category not in {"diagnosis", "cns_metastases"}:
            return None

        previous_history_split = self._split_previous_history_clause(criterion.original_text)
        if previous_history_split:
            return previous_history_split, "OR"

        return self._split_entity_coordinated_clause(criterion.original_text, criterion.entities)

    def _split_progression_after_receiving(self, criterion: CriterionText) -> list[CriterionText] | None:
        match = _PROGRESSION_AFTER_RECEIVING_PATTERN.match(criterion.text.strip())
        if not match:
            return None
        tail_parts = _split_top_level_conjunctions(match.group("tail"))
        if len(tail_parts) < 2:
            return None

        prefix = match.group("prefix").strip()
        source_sentence = criterion.source_sentence or criterion.text
        logic_group_id = str(uuid.uuid4())
        split_criteria: list[CriterionText] = []
        for part in tail_parts:
            clause_text = f"{prefix} {part.strip()}".strip()
            split_criteria.append(
                CriterionText(
                    text=clause_text,
                    type=criterion.type,
                    review_required=criterion.review_required,
                    review_reason=criterion.review_reason,
                    source_sentence=source_sentence,
                    source_clause_text=clause_text,
                    logic_group_id=logic_group_id,
                    logic_operator="AND",
                )
            )
        return split_criteria

    def _split_following_types_enumeration(self, criterion: CriterionText) -> list[CriterionText] | None:
        match = _FOLLOWING_TYPES_PATTERN.match(criterion.text.strip())
        if not match:
            return None

        raw_prefix = match.group("prefix").strip().rstrip(":,")
        prefix = re.sub(
            r"\bsolid\s+tumou?rs?\b\s*$",
            "",
            raw_prefix,
            flags=re.I,
        ).strip(" ,:")
        items = _split_top_level_commas(match.group("items"))
        tail = match.group("tail").strip()

        if len(items) < 2:
            return None

        source_sentence = criterion.source_sentence or criterion.text
        logic_group_id = str(uuid.uuid4())
        split_criteria: list[CriterionText] = []
        for item in items:
            normalized_item = item.strip().lstrip("* ").strip()
            normalized_item = re.sub(r"^(?:and|or)\s+", "", normalized_item, flags=re.I)
            if not normalized_item:
                continue
            clause_parts = [prefix, normalized_item, tail]
            clause_text = " ".join(part for part in clause_parts if part).strip()
            split_criteria.append(
                CriterionText(
                    text=clause_text,
                    type=criterion.type,
                    review_required=criterion.review_required,
                    review_reason=criterion.review_reason,
                    source_sentence=source_sentence,
                    source_clause_text=clause_text,
                    logic_group_id=logic_group_id,
                    logic_operator="OR",
                )
            )

        return split_criteria if len(split_criteria) >= 2 else None

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

    def _split_entity_coordinated_clause(self, text: str, entities: list[Entity]) -> tuple[list[str], str] | None:
        disease_entities = [entity for entity in entities if entity.label == "DISEASE"]
        if len(disease_entities) < 2:
            return None
        if len(disease_entities) == 2:
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
                return [left_clause, right_clause], "OR"

        first = disease_entities[0]
        last = disease_entities[-1]
        connector_span = text[first.end:last.start]
        stripped = connector_span
        for entity in disease_entities[1:-1]:
            stripped = stripped.replace(entity.text, " ")
        if not _is_safe_enumeration_connector_span(connector_span, disease_entities[1:-1]):
            return None

        prefix = text[:first.start]
        suffix = text[last.end:]
        clauses = [f"{prefix}{entity.text}{suffix}".strip() for entity in disease_entities]
        unique_clauses = [clause for index, clause in enumerate(clauses) if clause and clause not in clauses[:index]]
        if len(unique_clauses) < 2:
            return None
        return unique_clauses, "OR"

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


def _split_top_level_conjunctions(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if depth == 0 and text[index:index + 5].casefold() == " and ":
            parts.append("".join(current).strip(" ,;"))
            current = []
            index += 5
            continue
        current.append(char)
        index += 1

    final = "".join(current).strip(" ,;")
    if final:
        parts.append(final)
    return [part for part in parts if part]


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0

    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if depth == 0 and char == ",":
            part = "".join(current).strip(" ,;")
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)

    final = "".join(current).strip(" ,;")
    if final:
        parts.append(final)
    return [part for part in parts if part]


def _is_safe_enumeration_connector_span(text: str, interior_entities: list[Entity]) -> bool:
    reduced = text
    for entity in interior_entities:
        reduced = reduced.replace(entity.text, " ")
    normalized = re.sub(r"\s+", " ", reduced).strip(" ,")
    if not normalized:
        return True
    fragments = [fragment for fragment in _ENUMERATION_CONNECTOR_PATTERN.split(normalized) if fragment]
    return not fragments
