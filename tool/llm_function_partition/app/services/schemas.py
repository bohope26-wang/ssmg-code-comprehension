from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.localization import LanguageCode, normalize_language


class CFGNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    code: str = ""
    calls: list[str] = Field(default_factory=list)
    defs: list[str] = Field(default_factory=list)
    uses: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    kind: str = "statement"
    intent: str = ""
    start_line: int | None = None
    end_line: int | None = None


class CFGEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_: str = Field(alias="from")
    to: str
    type: str = "main"


class CFGPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    function_source: str
    bb_nodes: list[CFGNode]
    cfg_edges: list[CFGEdge]

    @field_validator("bb_nodes")
    @classmethod
    def validate_unique_bb_ids(cls, value: list[CFGNode]) -> list[CFGNode]:
        ids = [node.id for node in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate BB ids detected in cfg.bb_nodes.")
        return value


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["deepseek"] = "deepseek"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    model_ab: str = "deepseek-chat"
    model_c: str = "deepseek-chat"
    timeout_sec: int = 120
    max_format_retries: int = Field(default=1, ge=0, le=2)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function_name: str
    language: LanguageCode = "en"
    max_modules: int = Field(default=6, ge=2, le=12)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    model: str = Field(default="deepseek-chat")  # legacy + one-shot compatibility
    mode: Literal["one_shot", "multi_stage"] = "one_shot"
    max_candidates: int = Field(default=3, ge=1, le=5)
    enable_repair: bool = True
    multi_candidates_debug: bool = False
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, value: Any) -> LanguageCode:
        return normalize_language(value)

    def model_for_stage(self, stage_name: Literal["ab", "c"]) -> str:
        if stage_name == "ab":
            return self.llm.model_ab or self.model
        return self.llm.model_c or self.model


class ABGlobalBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")

    function_summary_candidates: list[list[Any]] = Field(default_factory=list)
    workflow_hypotheses: list[list[Any]] = Field(default_factory=list)
    coarse_boundary_hints: list[list[Any]] = Field(default_factory=list)
    uncertain_regions: list[list[Any]] = Field(default_factory=list)


class ABBasicBlockSemantics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    cr: str = "unknown"
    rc: list[list[Any]] = Field(default_factory=list)
    u: Literal["L", "M", "H"] = "M"


class StageABOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage_ab_global_bb_v1"
    function_name: str
    global_: ABGlobalBlock = Field(default_factory=ABGlobalBlock, alias="global")
    bb: list[ABBasicBlockSemantics] = Field(default_factory=list)

    def global_dict(self) -> dict[str, Any]:
        return self.global_.model_dump(mode="json")


class StageCModule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    desc: str
    more_specific_desc: str = ""
    bbs: list[str] = Field(default_factory=list)
    evi: list[str] = Field(default_factory=list)
    conf: int = Field(default=50, ge=0, le=100)


class StageCCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    mods: list[StageCModule] = Field(default_factory=list)


class StageCOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage_c_candidate_partition_v1"
    function_name: str
    candidates: list[StageCCandidate] = Field(default_factory=list)


class StageDRepairRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    from_module: str | None = None
    to_module: str | None = None
    bb_id: str | None = None
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class StageDCandidateReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    hard_valid: bool
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    violations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class StageDModuleMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    module_id: str
    source_temp_module_id: str
    label: str
    desc: str
    more_specific_desc: str = ""
    desc_status: Literal["inherited", "weakly_inherited", "invalidated"] = "invalidated"
    overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    bb_ids: list[str] = Field(default_factory=list)
    evidence_bb_ids: list[str] = Field(default_factory=list)
    confidence: int = Field(default=50, ge=0, le=100)
    risk: Literal["L", "M", "H"] = "M"


class StageDQualityMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coverage_ratio: float = 0.0
    duplicate_assignment_count: int = 0
    unknown_bb_count: int = 0
    module_count: int = 0
    singleton_module_count: int = 0
    disconnected_module_count: int = 0


class StageDOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage_d_verification_and_repair_v1"
    function_name: str
    selected_candidate_id: str
    candidate_reviews: list[StageDCandidateReview] = Field(default_factory=list)
    repairs: list[StageDRepairRecord] = Field(default_factory=list)
    final_partition: dict[str, str] = Field(default_factory=dict)
    module_metadata: list[StageDModuleMetadata] = Field(default_factory=list)
    quality_metrics: StageDQualityMetrics = Field(default_factory=StageDQualityMetrics)
    warnings: list[str] = Field(default_factory=list)


class ModuleEvidenceSignals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    calls: list[str] = Field(default_factory=list)
    defs: list[str] = Field(default_factory=list)
    uses: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    kind: str = "statement"


class ModuleEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bb_id: str
    line_span: list[int | None] = Field(default_factory=list, min_length=2, max_length=2)
    signals: ModuleEvidenceSignals = Field(default_factory=ModuleEvidenceSignals)


class ModuleEvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    desc: str
    desc_status: Literal["inherited", "weakly_inherited", "invalidated"] = "invalidated"
    confidence: int = Field(default=50, ge=0, le=100)
    risk: Literal["L", "M", "H"] = "M"


class ModuleEvidenceFlag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["weak_desc_inheritance", "high_uncertainty_evidence", "module_repair_heavy"]
    severity: Literal["L", "M", "H"] = "M"


class ModuleEvidenceModule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    module_id: str
    claim: ModuleEvidenceClaim
    evidence: list[ModuleEvidenceItem] = Field(default_factory=list)
    review_flags: list[ModuleEvidenceFlag] = Field(default_factory=list)


class ModuleEvidenceOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "module_evidence_v1"
    function_name: str
    module_evidence: list[ModuleEvidenceModule] = Field(default_factory=list)


class Stage1FunctionSummaryCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Stage1WorkflowHypothesis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hypothesis_id: str
    phases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Stage1CoarseBoundaryHint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    between: list[str] = Field(default_factory=list, min_length=2, max_length=2)
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Stage1UncertainRegion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bb_ids: list[str] = Field(default_factory=list)
    reason: str
    severity: Literal["low", "medium", "high"] = "medium"


class Stage1GlobalOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage1_global_hypotheses_v1"
    function_name: str
    function_summary_candidates: list[Stage1FunctionSummaryCandidate] = Field(default_factory=list)
    workflow_hypotheses: list[Stage1WorkflowHypothesis] = Field(default_factory=list)
    coarse_boundary_hints: list[Stage1CoarseBoundaryHint] = Field(default_factory=list)
    uncertain_regions: list[Stage1UncertainRegion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Stage2EffectProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    has_io: bool = False
    has_state_update: bool = False
    has_return: bool = False
    has_exception: bool = False
    has_external_call: bool = False


class Stage2RoleCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    score: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class Stage2BBSemantics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bb_id: str
    local_semantics: str
    control_role: Literal[
        "setup",
        "guard",
        "branch_body",
        "loop_header",
        "loop_body",
        "compute",
        "side_effect",
        "return",
        "exception",
        "cleanup",
        "unknown",
    ] = "unknown"
    effect_profile: Stage2EffectProfile
    role_candidates: list[Stage2RoleCandidate] = Field(default_factory=list)
    uncertainty: Literal["low", "medium", "high"] = "medium"
    conflicts_with_stage1: bool = False
    notes: str = ""

    @field_validator("role_candidates")
    @classmethod
    def validate_role_candidates(cls, value: list[Stage2RoleCandidate]) -> list[Stage2RoleCandidate]:
        if not (2 <= len(value) <= 4):
            raise ValueError("Each BB must have between 2 and 4 role candidates.")
        return value


class Stage2Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage2_bb_semantics_v1"
    function_name: str
    bb_semantics: list[Stage2BBSemantics]


class Stage3PairRelation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pair_id: str
    bb1: str
    bb2: str
    flow_relation: str
    same_module_score: float = Field(ge=0.0, le=1.0)
    boundary_score: float = Field(ge=0.0, le=1.0)
    relation_label: Literal["same_module", "boundary", "uncertain"]
    evidence: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "medium"
    conflicts_with_stage1: bool = False


class Stage3Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage3_pairwise_analysis_v1"
    function_name: str
    pair_relations: list[Stage3PairRelation]
    global_consistency_notes: list[str] = Field(default_factory=list)


class CandidateEstimatedQuality(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cohesion_score: float = Field(ge=0.0, le=1.0, default=0.5)
    boundary_clarity_score: float = Field(ge=0.0, le=1.0, default=0.5)
    fragmentation_risk: Literal["low", "medium", "high"] = "medium"


class CandidateModule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    temp_module_id: str
    label: str
    description: str
    bb_ids: list[str] = Field(default_factory=list)
    evidence_bb_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CandidateBoundaryDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_bb: str
    to_bb: str
    keep_boundary: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CandidatePartition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    rank: int = Field(ge=1, default=1)
    global_rationale: str
    estimated_quality: CandidateEstimatedQuality = Field(default_factory=CandidateEstimatedQuality)
    modules: list[CandidateModule] = Field(default_factory=list)
    boundary_decisions: list[CandidateBoundaryDecision] = Field(default_factory=list)


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    bb_id: str | None = None
    module_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CandidateReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    hard_valid: bool
    quality_score: float = Field(ge=0.0, le=1.0, default=0.0)
    violations: list[ReviewIssue] = Field(default_factory=list)
    warnings: list[ReviewIssue] = Field(default_factory=list)


class RepairRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    bb_id: str | None = None
    from_modules: list[str] = Field(default_factory=list)
    to_module: str | None = None
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


class Stage4ModuleMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    module_id: str
    label: str
    description: str
    bb_ids: list[str]
    evidence_bb_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    risk: Literal["low", "medium", "high"] = "medium"


class Stage4QualityMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coverage_ratio: float = 0.0
    duplicate_assignment_count: int = 0
    unknown_bb_count: int = 0
    module_count: int = 0
    singleton_module_count: int = 0
    disconnected_module_count: int = 0


class Stage4Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage4_verification_and_repair_v1"
    function_name: str
    candidate_partitions: list[CandidatePartition]
    selected_candidate_id: str
    candidate_reviews: list[CandidateReview]
    repairs: list[RepairRecord]
    final_partition: dict[str, str]
    module_metadata: list[Stage4ModuleMetadata]
    quality_metrics: Stage4QualityMetrics
    warnings: list[str] = Field(default_factory=list)


class Stage5EvidencePairScores(BaseModel):
    model_config = ConfigDict(extra="ignore")

    same_module_score: float = Field(ge=0.0, le=1.0, default=0.5)
    boundary_score: float = Field(ge=0.0, le=1.0, default=0.5)


class Stage5EvidenceBB(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bb_id: str
    local_semantics: str
    role_candidates: list[dict[str, Any]] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class Stage5BoundaryRationale(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_bb: str
    to_bb: str
    reason: str
    pairwise_scores: Stage5EvidencePairScores


class Stage5ModuleEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    module_id: str
    label: str
    claim: str
    evidence_bbs: list[Stage5EvidenceBB] = Field(default_factory=list)
    boundary_rationale: list[Stage5BoundaryRationale] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_spans: list[list[int]] = Field(default_factory=list)


class Stage5GlobalRiskSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    high_risk_modules: list[dict[str, Any]] = Field(default_factory=list)
    high_risk_boundaries: list[dict[str, Any]] = Field(default_factory=list)


class Stage5Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stage: str = "stage5_evidence_pack_v1"
    function_name: str
    module_evidence: list[Stage5ModuleEvidence] = Field(default_factory=list)
    global_risk_summary: Stage5GlobalRiskSummary = Field(default_factory=Stage5GlobalRiskSummary)


def cfg_payload_from_dict(cfg: dict[str, Any]) -> CFGPayload:
    return CFGPayload.model_validate(cfg)


def cfg_payload_to_dict(cfg: CFGPayload) -> dict[str, Any]:
    return cfg.model_dump(mode="json", by_alias=True)


# Legacy aliases for backward-compatible imports in experimental modules.
Stage1Output = Stage2Output
Stage2PairwiseOutput = Stage3Output
