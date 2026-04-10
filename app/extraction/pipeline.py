import spacy
from spacy.language import Language

from app.config import settings
from app.extraction.abbreviation_resolver import AbbreviationResolver
from app.extraction.criteria_classifier import RuleBasedClassifier
from app.extraction.entity_ruler import load_entity_ruler
from app.extraction.section_splitter import SectionSplitter
from app.extraction.types import ClassifiedCriterion, Entity, PipelineResult


class ExtractionPipeline:
    """Orchestrates the 6-stage NLP extraction pipeline."""

    def __init__(self):
        self._nlp = self._load_nlp()
        self._splitter = SectionSplitter()
        self._abbreviation_resolver = AbbreviationResolver(settings.abbreviation_dict_path)
        self._classifier = RuleBasedClassifier()

    def _load_nlp(self) -> Language:
        try:
            nlp = spacy.load(settings.spacy_model)
        except OSError:
            nlp = spacy.load("en_core_web_sm")
        nlp = load_entity_ruler(nlp, settings.patterns_dir)
        return nlp

    def extract(self, eligibility_text: str) -> PipelineResult:
        # Stage 1: Section Splitter
        criterion_texts = self._splitter.split(eligibility_text)

        criteria: list[ClassifiedCriterion] = []
        for ct in criterion_texts:
            # Stage 2: spaCy NER
            doc = self._nlp(ct.text)
            entities = [
                Entity(text=ent.text, label=ent.label_, start=ent.start_char, end=ent.end_char)
                for ent in doc.ents
            ]

            # Stage 2.5: Abbreviation Resolver
            entities = self._abbreviation_resolver.resolve(entities, ct.text)

            # Stage 3: Criteria Classifier
            classified = self._classifier.classify(ct.text, entities)
            # Override type from Stage 1
            classified = classified.model_copy(update={
                "type": ct.type,
                "review_required": classified.review_required or ct.review_required,
                "review_reason": classified.review_reason or ct.review_reason,
            })

            criteria.append(classified)

        return PipelineResult(criteria=criteria, pipeline_version=settings.pipeline_version)
