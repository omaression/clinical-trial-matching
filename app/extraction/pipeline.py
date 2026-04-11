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
            dynamic_abbreviations = {}
            doc_extensions = getattr(doc._, "abbreviations", None)
            if doc_extensions:
                dynamic_abbreviations = {
                    abbreviation.text.lower(): str(abbreviation._.long_form)
                    for abbreviation in doc._.abbreviations
                    if getattr(abbreviation._, "long_form", None)
                }

            # Stage 2.5: Abbreviation Resolver
            entities = self._abbreviation_resolver.resolve(
                entities,
                ct.text,
                dynamic_abbreviations=dynamic_abbreviations,
            )

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
