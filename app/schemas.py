import calendar
import uuid
from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from app.config import settings
from app.models import Event
from app.utils.logger import setup_logger

logger = setup_logger("schemas")


class KeywordExtractionResult(BaseModel):
    original_keywords: list[str] = Field(default_factory=list)
    english_keywords: list[str] = Field(default_factory=list)
    viewpoint_language: str = "und"
    translated_viewpoint: str | None = None
    error: str | None = None
    is_verified_existent: bool | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EntityServiceResponse(BaseModel):
    entity_id: str | None
    message: str
    disambiguation_options: list[str] | None = None
    status_code: int = 200
    is_verified_existent: bool | None = None

    @field_validator("entity_id", mode="before")
    @classmethod
    def convert_uuid_to_string(cls, v: Any) -> str | None:
        """Convert UUID to string for frontend compatibility"""
        if v is None:
            return None
        if isinstance(v, UUID):
            return str(v)
        return str(v) if v else None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class WikiPageInfoResponse(BaseModel):
    exists: bool = False
    is_redirect: bool = False
    wikibase_item: str | None = None  # global unique id for wikipedia entity
    pageid: int | None = None  # page id for wikipedia entity
    title: str | None = None  # title of the page
    pagelanguage: str | None = None  # language of the page
    extract: str | None = None  # extract of the page
    touched: str | None = None  # last modified time of the page
    fullurl: str | None = None
    is_disambiguation: bool | None = False
    disambiguation_options: list[str] | None = None

    @field_validator("is_disambiguation", mode="before")
    @classmethod
    def parse_disambiguation_flag(cls, v: Any) -> bool:
        """Handle various disambiguation flag values from Wikipedia API"""
        if v is None or v == "":
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    model_config = ConfigDict(from_attributes=True)


class UserRegister(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=50, description="Username for the new account"
    )
    password: str = Field(
        ..., min_length=6, max_length=100, description="Password for the new account"
    )


class UserLogin(BaseModel):
    username: str = Field(..., description="Username for login")
    password: str = Field(..., description="Password for login")


class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class UserInfo(BaseModel):
    id: UUID = Field(..., description="User unique identifier")
    username: str = Field(..., description="Username")
    created_at: str = Field(..., description="Account creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str = Field(..., description="Response message")


# Pydantic model for raw entity from LLM
class RawLLMEntity(BaseModel):
    name: str
    type: str
    language: str


# Pydantic model for a single event extracted by LLM
class RawLLMEvent(BaseModel):
    event_description: str = Field(
        ..., alias="event_description"
    )  # Keep original name from LLM for clarity
    event_date_str: str = Field(
        ...,
        alias="event_date_str",
        description="The original, verbatim date text from the source.",
    )
    enhanced_event_date_str: str | None = Field(
        None,
        alias="enhanced_event_date_str",
        description="When event_date_str is vague (e.g., 'recent years', 'within a few years'), provide a more specific time estimation based on surrounding context, historical background, or other temporal clues in the text. If event_date_str is already specific, this field should be null.",
    )
    main_entities: list[RawLLMEntity] = Field(
        default_factory=list, alias="main_entities"
    )
    source_text_snippet: str = Field(
        ...,
        alias="source_text_snippet",
        description="The original text snippet from the text that describes the event, for traceability.",
    )

    model_config = ConfigDict(populate_by_name=True)


class SourceArticle(BaseModel):
    source_name: (
        str  # e.g., "wikipedia_online", "wikipedia_local_semantic", "generic_web"
    )
    source_url: str | None = None
    source_identifier: str  # A unique identifier for the source. For Wikipedia, this MUST be the page_id.
    title: str | None = None
    text_content: str
    language: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )  # For any other source-specific info


class ArticleAcquisitionConfig(BaseModel):
    """
    Configuration for the article acquisition process, especially for hybrid search.
    """

    search_mode: Literal["semantic", "hybrid_title_search"] = Field(
        default="hybrid_title_search", description="The search strategy to use."
    )
    vector_weight: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Weight for vector search score (0.0 to 1.0).",
    )
    bm25_weight: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Weight for BM25 search score (0.0 to 1.0).",
    )
    article_limit: int = Field(
        default=settings.default_article_limit,
        gt=0,
        description="The maximum number of articles to return.",
    )

    @model_validator(mode="after")
    def check_weights_for_hybrid(self) -> "ArticleAcquisitionConfig":
        """Validate that for hybrid search, weights are not both zero."""
        if self.search_mode == "hybrid_title_search":
            if self.vector_weight == 0.0 and self.bm25_weight == 0.0:
                raise ValueError(
                    "For hybrid search, at least one of vector_weight or bm25_weight must be greater than 0."
                )
        return self


# Model for processed entity information, used after entity service processing.
class ProcessedEntityInfo(BaseModel):
    entity_id: str | None = Field(
        None, description="The unique identifier of the entity (UUID string) or None."
    )
    original_name: str = Field(
        ..., description="The original entity name extracted by the LLM."
    )
    entity_type: str = Field(..., description="The entity type extracted by the LLM.")
    is_verified_existent: bool | None = Field(
        None,
        description="True if verified to exist, False if verified not to exist, None if unknown/other error.",
    )


# Python's date object supports years from 1 to 9999.
MIN_YEAR = 1
MAX_YEAR = 9999


def get_last_day_of_month(year: int, month: int) -> int:
    """Helper to get the last day of a given month and year."""
    return calendar.monthrange(year, month)[1]


class DateRangeInfo(BaseModel):
    """
    A computational utility class that represents a date or a date range.

    It normalizes imprecise date information (from a ParsedDateInfo-like structure)
    into concrete Python `date` objects for start and end boundaries, enabling
    computations like overlap checks.
    """

    start_date: date = Field(..., description="The concrete start date of the range")
    end_date: date = Field(..., description="The concrete end date of the range")
    precision: str = Field(
        ...,
        description="The precision of the date range (e.g., 'day', 'month', 'year')",
    )
    original_details: dict[str, Any] = Field(
        default_factory=dict,
        description="The raw 'date_info' from LLM, for precision context",
    )
    original_text: str | None = Field(
        None, description="The original 'event_date_str' from LLM, for display context"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_serializer("start_date", "end_date")
    def serialize_date(self, dt: date, _info):
        return dt.isoformat()

    @model_validator(mode="after")
    def validate_date_order(self) -> "DateRangeInfo":
        """Ensure start_date is not after end_date, swap if necessary."""
        if self.start_date > self.end_date:
            logger.warning(
                f"DateRangeInfo: start_date {self.start_date} is after end_date {self.end_date}. "
                f"Swapping them. Original details: {self.original_details}, original_text: {self.original_text}"
            )
            self.start_date, self.end_date = self.end_date, self.start_date
        return self

    def overlaps(self, other: "DateRangeInfo") -> bool:
        """Checks if this date range overlaps with another DateRangeInfo."""
        if not isinstance(other, DateRangeInfo):  # Ensure type safety
            return False
        # Overlap condition: max(start1, start2) <= min(end1, end2)
        return max(self.start_date, other.start_date) <= min(
            self.end_date, other.end_date
        )

    def contains_date(self, specific_date: date) -> bool:
        """Checks if a specific date falls within this range (inclusive)."""
        return self.start_date <= specific_date <= self.end_date

    def is_single_day(self) -> bool:
        """Checks if the range represents a single day."""
        return self.start_date == self.end_date

    def to_tuple(self) -> tuple[date, date]:
        """Returns the date range as a (start_date, end_date) tuple."""
        return self.start_date, self.end_date

    def get_timestamp(self) -> float | None:
        """
        Returns a Unix timestamp for the start of the date range (at midnight UTC).
        Returns None if the date is outside the valid range for timestamp conversion.
        """
        if self.start_date:
            try:
                # Combine with min time (midnight) before getting timestamp
                dt_to_convert = datetime.combine(self.start_date, time.min)
                return dt_to_convert.timestamp()
            except OSError as e:
                logger.warning(
                    f"Could not convert date {self.start_date} to timestamp due to OSError: {e}. "
                    f"This usually means the date is outside the system's valid range (e.g., pre-1970 on Windows)."
                )
                return None
            except (
                ValueError
            ) as e:  # Python's date/datetime objects might raise ValueError for truly out-of-range dates (e.g. year 0)
                logger.warning(
                    f"Could not convert date {self.start_date} to timestamp due to ValueError: {e}."
                )
                return None
        return None

    def to_api_dict(self) -> dict[str, Any]:
        """Prepares the date information for API responses."""
        return {
            "start_date_iso": self.start_date.isoformat() if self.start_date else None,
            "end_date_iso": self.end_date.isoformat() if self.end_date else None,
            "display_text": self.original_text,
            "precision": self.precision,
        }

    def __repr__(self) -> str:
        return f"<DateRangeInfo start={self.start_date.isoformat() if self.start_date else 'N/A'} end={self.end_date.isoformat() if self.end_date else 'N/A'} precision='{self.precision}' str='{self.original_text}'>"


class ParsedDateInfo(BaseModel):
    """
    A sophisticated schema to hold structured date information parsed from a raw date string.
    It handles varying precisions, BCE/CE eras, and provides both raw data for computation
    and a display-ready text.
    """

    original_text: str = Field(
        ..., description="The original, verbatim date text that was parsed."
    )
    display_text: str = Field(
        ..., description="A clean, human-readable version of the date."
    )
    precision: Literal[
        "day", "month", "year", "decade", "century", "millennium", "era", "unknown"
    ] = Field(
        ..., description="The granularity of the date (e.g., 'year', 'century', 'era')."
    )
    start_year: int | None = Field(
        None, description="The start year as an integer. Negative for BCE."
    )
    start_month: int | None = Field(None, description="The start month (1-12).")
    start_day: int | None = Field(None, description="The start day (1-31).")
    end_year: int | None = Field(
        None, description="The end year as an integer. Negative for BCE."
    )
    end_month: int | None = Field(None, description="The end month (1-12).")
    end_day: int | None = Field(None, description="The end day (1-31).")
    is_bce: bool = Field(..., description="True if the date is in the BCE era.")

    def to_date_range(self) -> DateRangeInfo | None:
        """
        Converts this ParsedDateInfo into a computable DateRangeInfo object.
        """

        if self.start_year is None:
            logger.debug(
                f"Date info does not contain 'start_year'. "
                f"ParsedDateInfo: {self.model_dump()}"
            )
            return None

        try:
            s_year = int(self.start_year)
            # Use end_year if provided, otherwise default to start_year
            e_year = int(self.end_year or s_year)

            # Validate year ranges supported by Python's datetime.date
            if not (MIN_YEAR <= s_year <= MAX_YEAR and MIN_YEAR <= e_year <= MAX_YEAR):
                logger.warning(
                    f"Year out of supported range ({MIN_YEAR}-{MAX_YEAR}). "
                    f"Cannot create date object. s_year: {s_year}, e_year: {e_year}. "
                    f"Skipping date range creation for '{self.original_text}'."
                )
                return None

            # Determine start month/day based on precision
            s_month = int(self.start_month or 1)
            s_day = int(self.start_day or 1)

            # Determine end month/day based on precision and available data
            e_month = int(self.end_month or s_month)
            e_day = int(self.end_day or s_day)

            # If precision is broad, expand the end date to cover the full period
            if self.precision == "year":
                e_month = 12
                e_day = 31
            elif self.precision == "month":
                # If no end_month is specified, assume it's the same as start_month
                if self.end_month is None and self.start_month is not None:
                    e_month = s_month
                e_day = get_last_day_of_month(e_year, e_month)
            elif self.precision == "decade":
                e_year = s_year + 9
                e_month = 12
                e_day = 31

            # Final safety check for end_day if it's still just a copy of start_day
            if (
                self.end_day is None
                and self.end_month is not None
                and e_month != s_month
            ):
                e_day = get_last_day_of_month(e_year, e_month)

            start_date_obj = date(s_year, s_month, s_day)
            end_date_obj = date(e_year, e_month, e_day)

            return DateRangeInfo(
                start_date=start_date_obj,
                end_date=end_date_obj,
                precision=self.precision,
                original_details=self.model_dump(),
                original_text=self.original_text,
            )

        except (ValueError, TypeError) as e:
            logger.error(
                f"Failed to create date objects from ParsedDateInfo. "
                f"ParsedDateInfo: {self.model_dump()}. Error: {e}",
                exc_info=True,
            )
            return None


class MergedEventGroupSchema(BaseModel):
    is_merged: bool
    # if is_merged=True, description and date_info will be filled
    description: str | None = None
    date_info: ParsedDateInfo | None = None
    # Contains all original Event objects involved in this group
    source_events: list[Event]

    model_config = ConfigDict(arbitrary_types_allowed=True)  # Allow Event object


# Pydantic model for an event after LLM extraction and entity processing
class ProcessedEvent(BaseModel):
    description: str
    event_date_str: str  # The original string from RawLLMEvent
    date_info: ParsedDateInfo  # The new structured, parsed date info
    main_entities: list[Any] = Field(default_factory=list)
    source_text_snippet: str
    # other fields can be added as the event is processed further

    model_config = ConfigDict(from_attributes=True)


# --- START: Original Pydantic models for Merged Event API Response (will be modified) ---
class EventSourceInfoForAPI(BaseModel):
    source_language: str
    source_page_title: str | None = None
    source_url: str | None = None
    source_document_id: str | None = None

    @field_validator("source_language", mode="before")
    @classmethod
    def provide_str_defaults(cls, v: Any, info: ValidationInfo) -> str:
        """Provide default values for required string fields if input is None."""
        if v is None:
            if info.field_name == "source_language":
                return "unknown"
        return str(v)

    model_config = ConfigDict(from_attributes=True)


# --- END: Original Pydantic models for Merged Event API Response ---


class TimelineEventForAPI(BaseModel):
    id: str  # Convert UUID to string for frontend compatibility
    event_date_str: str
    description: str
    main_entities: list[ProcessedEntityInfo]
    date_info: ParsedDateInfo | None = None

    is_merged: bool
    source_snippets: dict[str, str | None]  # source_ref -> snippet mapping

    viewpoint_id: str | None = None  # Convert UUID to string for frontend compatibility
    relevance_score: float | None = None  # Relevance score for filtering and ranking

    @field_validator("id", mode="before")
    @classmethod
    def convert_id_to_string(cls, v: Any) -> str:
        """Convert UUID to string for frontend compatibility"""
        if isinstance(v, UUID):
            return str(v)
        return str(v)

    @field_validator("viewpoint_id", mode="before")
    @classmethod
    def convert_viewpoint_id_to_string(cls, v: Any) -> str | None:
        """Convert UUID to string for frontend compatibility"""
        if v is None:
            return None
        if isinstance(v, UUID):
            return str(v)
        return str(v) if v else None

    model_config = ConfigDict(from_attributes=True)


class TimelineResponse(BaseModel):
    events: list[TimelineEventForAPI] = Field(
        ..., description="List of extracted timeline events (merged)"
    )  # Changed from TimelineEvent


class TimelineGenerationResult:
    def __init__(
        self,
        events: list[TimelineEventForAPI],
        viewpoint_id: uuid.UUID | None = None,
        events_count: int = 0,
        keywords_extracted: list[str] | None = None,
        articles_processed: int = 0,
    ):
        self.events = events
        self.viewpoint_id = viewpoint_id
        self.events_count = events_count
        self.keywords_extracted = keywords_extracted or []
        self.articles_processed = articles_processed

    def to_timeline_response(self) -> TimelineResponse:
        return TimelineResponse(events=self.events)


class ViewpointRequest(BaseModel):
    viewpoint: str = Field(
        ..., min_length=1, description="User-provided research viewpoint or question"
    )


# Task-related API models
class CreateTaskRequest(BaseModel):
    topic_text: str = Field(
        ..., min_length=1, description="Research topic or viewpoint"
    )
    config: dict[str, Any] | None = Field(
        None, description="Task configuration, such as data source preferences"
    )
    is_public: bool | None = Field(
        None,
        description="Whether to make the task public, only effective when user is logged in",
    )


class CreateEntityCanonicalTaskRequest(BaseModel):
    entity_id: uuid.UUID = Field(
        ..., description="Entity ID to generate canonical timeline for"
    )
    config: dict[str, Any] | None = Field(
        None, description="Task configuration options"
    )
    is_public: bool | None = Field(
        None,
        description="Whether to make the task public, only effective when user is logged in",
    )


class CreateDocumentCanonicalTaskRequest(BaseModel):
    source_document_id: uuid.UUID = Field(
        ..., description="Source document ID to generate canonical timeline for"
    )
    config: dict[str, Any] | None = Field(
        None, description="Task configuration options"
    )
    is_public: bool | None = Field(
        None,
        description="Whether to make the task public, only effective when user is logged in",
    )


# New model for WebSocket status messages in API responses
class WebSocketStatusMessageForAPI(BaseModel):
    request_id: str  # Typically the task_id when returning historical steps
    step: str
    message: str
    timestamp: str  # ISO format string


class ViewpointProgressStepInfo(BaseModel):
    id: uuid.UUID
    step_name: str
    message: str
    event_timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ViewpointInfo(BaseModel):
    id: uuid.UUID
    status: str
    topic: str
    viewpoint_type: str
    data_source_preference: str
    canonical_source_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ViewpointDetailResponse(BaseModel):
    viewpoint: ViewpointInfo
    progress_steps: list[ViewpointProgressStepInfo]
    sources: dict[str, EventSourceInfoForAPI]  # Dictionary of source references
    timeline_events: list[TimelineEventForAPI]

    model_config = ConfigDict(from_attributes=True)


# --- Base model for Task data ---
class TaskBase(BaseModel):
    # Base model for task data, containing common fields
    id: uuid.UUID
    task_type: str = "synthetic_viewpoint"
    topic_text: str | None = None
    entity_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    owner: UserInfo | None = None
    is_public: bool
    status: str
    viewpoint_id: uuid.UUID | None = None
    processing_duration: float | None = None
    config: dict[str, Any] | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(TaskBase):
    # Includes formatted progress messages for direct task GET requests
    progress_messages: list[WebSocketStatusMessageForAPI] | None = Field(
        None,
        description="A formatted list of progress steps, available on direct task GET requests.",
    )

    @model_validator(mode="before")
    @classmethod
    def format_progress_messages(cls, data: Any) -> Any:
        """
        Automatically format progress steps from viewpoint_details into the
        expected WebSocketStatusMessageForAPI format.
        """
        if isinstance(data, dict) and (
            viewpoint_details := data.get("viewpoint_details")
        ):
            if progress_steps := viewpoint_details.get("progress_steps"):
                task_id = str(data.get("id"))
                formatted_messages = []
                for step in progress_steps:
                    timestamp = step.get("event_timestamp")
                    iso_timestamp = ""
                    if isinstance(timestamp, datetime):
                        iso_timestamp = timestamp.isoformat()
                    elif isinstance(timestamp, str):
                        iso_timestamp = timestamp

                    formatted_messages.append(
                        WebSocketStatusMessageForAPI(
                            request_id=task_id,
                            step=step.get("step_name") or "unknown_step",
                            message=step.get("message"),
                            timestamp=iso_timestamp,
                        )
                    )
                data["progress_messages"] = formatted_messages
        return data


class UpdateTaskStatusRequest(BaseModel):
    status: str = Field(
        ..., description="New status: pending|processing|completed|failed"
    )
    notes: str | None = Field(None, description="Status update notes")
    viewpoint_id: uuid.UUID | None = Field(None, description="Associated viewpoint_id")
    events_count: int | None = Field(None, description="Number of events")
    processing_duration: float | None = Field(
        None, description="Processing duration in seconds"
    )


class UpdateTaskSharingRequest(BaseModel):
    is_public: bool = Field(
        ...,
        description="Set to true to make the task public, false to make it private.",
    )


# --- START: Models for Event Merger Service ---


class EventEntityForMerger(BaseModel):
    entity_id: str | None = None
    original_name: str | None = None
    entity_type: str | None = None


class EventDataForMerger(BaseModel):
    id: str | None = None
    description: str = ""
    event_date_str: str | None = None
    date_info: ParsedDateInfo | None = None
    main_entities: list[EventEntityForMerger] = Field(default_factory=list)
    source_text_snippet: str | None = None
    main_entities_processed: list[Any] | None = None


class SourceInfoForMerger(BaseModel):
    language: str | None = None
    page_url: str | None = None
    page_title: str | None = None
    keyword_source: str | None = None


class RepresentativeEventInfo(BaseModel):
    event_date_str: str | None
    description: str
    main_entities: list[Any]  # Can contain ProcessedEntityInfo or EventEntityForMerger
    date_info: ParsedDateInfo | None = None  # Preserves the full ParsedDateInfo
    timestamp: datetime | None
    source_text_snippet: str | None
    source_url: str | None
    source_page_title: str | None
    source_language: str | None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SourceContributionInfo(BaseModel):
    event_data: EventDataForMerger
    source_info: SourceInfoForMerger


class MergedEventGroupOutput(BaseModel):
    representative_event: RepresentativeEventInfo
    source_contributions: list[SourceContributionInfo]
    original_id: str | None


# --- END: Models for Event Merger Service ---


# New model for the /tasks/{task_id}/result endpoint
class TaskResultDetailResponse(TaskBase):
    viewpoint_details: ViewpointDetailResponse | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Wiki API Response Models ---


class WikiPageTextResponse(BaseModel):
    """
    Schema for the response from get_wiki_page_text, representing a single Wikipedia page's content.
    """

    title: str
    url: str | None = None
    page_id: int | None = None
    text: str | None = None
    error: str | None = None
    redirect_info: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class InterlanguageLinkResponse(BaseModel):
    """
    Schema for the response from get_interlanguage_link, representing the result of a cross-lingual link search.
    """

    source_title: str
    source_url: str | None = None
    target_title: str | None = None
    target_url: str | None = None
    error: str | None = None
    source_redirect_info: dict[str, str] | None = None
    raw_response_data: dict[str, Any] | None = None  # For debugging

    model_config = ConfigDict(from_attributes=True)


class CrosslingualWikiTextResponse(BaseModel):
    """
    Schema for the response from get_wiki_page_text_for_target_lang.
    """

    link_search_outcome: InterlanguageLinkResponse
    text_extraction_outcome: WikiPageTextResponse | None = None
    overall_status: str
    text: str | None = None
    error: str | None = None
    url: str | None = None
    title: str | None = None
    page_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class WikinewsArticleCore(BaseModel):
    """
    Schema for a single article fetched from Wikinews.
    """

    text: str | None = None
    title: str | None = None
    url: str | None = None
    error: str | None = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class WikinewsSearchResponse(BaseModel):
    """
    Schema for the response from get_wikinews_page_text, containing search results.
    """

    articles: list[WikinewsArticleCore]
    search_query: str
    status: str
    error: str | None = None

    model_config = ConfigDict(from_attributes=True)
