import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models import (
    GenerateTasksRequest,
    GenerateTasksResponse,
    HealthResponse,
    PartitionRequest,
    PartitionResponse,
    SampleResponse,
    VariableTraceExplainRequest,
    VariableTraceExplainResponse,
    VariableTraceRequest,
    VariableTraceResponse,
)
from app.services.cfg_builder import build_cfg_for_function
from app.services.exporter import export_run_artifacts
from app.services.localization import normalize_language, tr
from app.services.pipeline_multistage import run_multistage_pipeline
from app.services.pipeline_oneshot import run_oneshot_pipeline
from app.services.schemas import CFGPayload, RuntimeConfig
from app.services.task_generator import generate_task_quiz
from app.services.variable_trace import build_variable_trace, explain_variable_trace


logger = logging.getLogger(__name__)
router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BASE_DIR / "samples"
OUTPUT_DIR = BASE_DIR / "app" / "outputs"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/sample", response_model=SampleResponse)
def sample() -> SampleResponse:
    sample_path = SAMPLES_DIR / "demo.py"
    source_code = sample_path.read_text(encoding="utf-8")
    return SampleResponse(
        source_code=source_code,
        function_name="process_orders",
        sample_path=str(sample_path),
    )


@router.post("/partition", response_model=PartitionResponse)
def partition_function(payload: PartitionRequest) -> PartitionResponse:
    language = normalize_language(payload.language)
    try:
        cfg_result = build_cfg_for_function(payload.source_code, payload.function_name, language=language)
        cfg = CFGPayload.model_validate(
            {
                "function_source": cfg_result.function_source,
                "bb_nodes": cfg_result.bb_nodes,
                "cfg_edges": cfg_result.cfg_edges,
            }
        )
        runtime_config = RuntimeConfig(
            function_name=cfg_result.function_name,
            language=language,
            max_modules=payload.max_modules,
            temperature=payload.temperature,
            model=payload.model,
            mode=payload.mode,
            max_candidates=payload.max_candidates,
            enable_repair=payload.enable_repair,
            multi_candidates_debug=payload.multi_candidates_debug,
            llm=payload.llm or {},
        )
        logger.info("Partition request function=%s mode=%s", runtime_config.function_name, runtime_config.mode)

        if runtime_config.mode == "multi_stage":
            result = run_multistage_pipeline(cfg, runtime_config)
        else:
            result = run_oneshot_pipeline(cfg, runtime_config)

        export_run_artifacts(
            output_dir=OUTPUT_DIR,
            cfg=result["cfg"],
            partition=result["partition"],
            module_graph=result["module_graph"],
            cfg_by_module=result["cfg_by_module"],
            llm_debug=result["debug"],
            module_evidence=result.get("module_evidence"),
            stage_artifacts=result.get("stage_outputs"),
            language=language,
        )
        return PartitionResponse(
            language=language,
            function_name=runtime_config.function_name,
            mode=runtime_config.mode,
            cfg=result["cfg"],
            partition=result["partition"],
            module_graph=result["module_graph"],
            cfg_by_module=result["cfg_by_module"],
            debug=result["debug"],
            stage_outputs=result.get("stage_outputs", {}),
            module_evidence=result.get("module_evidence"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=tr(language, "error.unexpected", error=exc)) from exc


@router.post("/generate_tasks", response_model=GenerateTasksResponse)
def generate_tasks(payload: GenerateTasksRequest) -> GenerateTasksResponse:
    language = normalize_language(payload.language)
    try:
        return generate_task_quiz(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=tr(language, "error.unexpected", error=exc)) from exc


@router.post("/variable-trace", response_model=VariableTraceResponse)
def variable_trace(payload: VariableTraceRequest) -> VariableTraceResponse:
    language = normalize_language(payload.language)
    try:
        return build_variable_trace(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=tr(language, "error.unexpected", error=exc)) from exc


@router.post("/variable-trace-explain", response_model=VariableTraceExplainResponse)
def variable_trace_explain(payload: VariableTraceExplainRequest) -> VariableTraceExplainResponse:
    language = normalize_language(payload.language)
    try:
        return explain_variable_trace(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=tr(language, "error.unexpected", error=exc)) from exc
