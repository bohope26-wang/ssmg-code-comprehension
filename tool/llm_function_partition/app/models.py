from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.localization import LanguageCode, normalize_language


class LanguageAwareModel(BaseModel):
    language: LanguageCode = Field(default="en")
    locale: str | None = Field(default=None, exclude=True)

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, value: Any) -> LanguageCode:
        return normalize_language(value)

    @model_validator(mode="after")
    def apply_locale_alias(self) -> "LanguageAwareModel":
        if self.locale:
            self.language = normalize_language(self.locale)
        return self


class PartitionRequest(LanguageAwareModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(..., min_length=1)
    function_name: str = Field(..., min_length=1)
    max_modules: int = Field(default=7, ge=6, le=9)
    model: str = Field(default="deepseek-chat")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    mode: Literal["one_shot", "multi_stage"] = Field(default="one_shot")
    max_candidates: int = Field(default=3, ge=1, le=5)
    enable_repair: bool = Field(default=True)
    multi_candidates_debug: bool = Field(default=False)
    llm: dict[str, Any] | None = Field(default=None)


class PartitionResponse(LanguageAwareModel):
    function_name: str
    mode: Literal["one_shot", "multi_stage"]
    cfg: dict[str, Any]
    partition: dict[str, str]
    module_graph: dict[str, Any]
    cfg_by_module: dict[str, Any]
    debug: dict[str, Any]
    stage_outputs: dict[str, Any] = Field(default_factory=dict)
    module_evidence: dict[str, Any] | None = None


class TaskQuizOption(BaseModel):
    id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)


class TaskQuizEvidence(BaseModel):
    modules: list[str] = Field(default_factory=list)
    bb_ids: list[str] = Field(default_factory=list)
    line_spans: list[list[int | None]] = Field(default_factory=list)


class TaskQuizQuestion(BaseModel):
    id: str = Field(..., min_length=1)
    type: Literal["single_choice"] = "single_choice"
    question: str = Field(..., min_length=1)
    options: list[TaskQuizOption] = Field(default_factory=list, min_length=2, max_length=5)
    answer: str = Field(..., min_length=1)
    explanation: str = Field(..., min_length=1)
    evidence: TaskQuizEvidence = Field(default_factory=TaskQuizEvidence)


class GenerateTasksRequest(LanguageAwareModel):
    model_config = ConfigDict(extra="forbid")

    function_name: str = Field(..., min_length=1)
    mode: Literal["one_shot", "multi_stage"] = "multi_stage"
    cfg: dict[str, Any]
    partition: dict[str, str]
    module_graph: dict[str, Any]
    cfg_by_module: dict[str, Any]
    stage_outputs: dict[str, Any] = Field(default_factory=dict)
    module_evidence: dict[str, Any] | None = None
    model: str = Field(default="deepseek-chat")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    question_count: int = Field(default=4, ge=3, le=5)
    llm: dict[str, Any] | None = Field(default=None)


class GenerateTasksResponse(LanguageAwareModel):
    function_name: str
    generation_mode: Literal["llm", "fallback"] = "llm"
    warning: str | None = None
    questions: list[TaskQuizQuestion] = Field(default_factory=list)


class VariableTraceRequest(LanguageAwareModel):
    model_config = ConfigDict(extra="forbid")

    function_name: str = Field(..., min_length=1)
    variable_query: str = Field(..., min_length=1)
    cfg: dict[str, Any] | None = None
    partition: dict[str, str] | None = None
    module_graph: dict[str, Any] | None = None
    cfg_by_module: dict[str, Any] | None = None
    stage_outputs: dict[str, Any] | None = None
    module_evidence: dict[str, Any] | None = None


class VariableTraceEvent(BaseModel):
    module_id: str | None = None
    module_name: str | None = None
    bb_id: str
    line_span: list[int | None] = Field(default_factory=list, min_length=2, max_length=2)
    event_type: Literal["def", "update", "use", "condition", "output"]
    code_snippet: str = ""
    reason: str = ""


class VariableTraceStats(BaseModel):
    def_count: int = 0
    update_count: int = 0
    use_count: int = 0
    condition_count: int = 0
    output_count: int = 0
    matched_bb_count: int = 0
    related_module_count: int = 0


class VariableTraceResponse(LanguageAwareModel):
    function_name: str
    query: str
    resolved_variable: str
    matches: list[str] = Field(default_factory=list)
    role_hint: str = "working_state"
    timeline: list[VariableTraceEvent] = Field(default_factory=list)
    related_modules: list[str] = Field(default_factory=list)
    line_spans: list[list[int | None]] = Field(default_factory=list)
    bb_ids: list[str] = Field(default_factory=list)
    trace_stats: VariableTraceStats = Field(default_factory=VariableTraceStats)


class VariableTraceExplainRequest(LanguageAwareModel):
    model_config = ConfigDict(extra="forbid")

    function_name: str = Field(..., min_length=1)
    variable_query: str = Field(..., min_length=1)
    trace: VariableTraceResponse | dict[str, Any]
    cfg: dict[str, Any] | None = None
    partition: dict[str, str] | None = None
    module_graph: dict[str, Any] | None = None
    cfg_by_module: dict[str, Any] | None = None
    stage_outputs: dict[str, Any] | None = None
    module_evidence: dict[str, Any] | None = None
    model: str = Field(default="deepseek-chat")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm: dict[str, Any] | None = Field(default=None)


class VariableTraceExplainResponse(LanguageAwareModel):
    function_name: str
    query: str
    resolved_variable: str
    generation_mode: Literal["llm", "fallback"] = "llm"
    warning: str | None = None
    role: str = "working_state"
    summary: str = ""
    key_transitions: list[str] = Field(default_factory=list)
    impact: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class SampleResponse(BaseModel):
    source_code: str
    function_name: str
    sample_path: str
