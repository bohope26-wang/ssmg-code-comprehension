# LLM Function Partition

A local research prototype for understanding individual Python functions through control-flow analysis and LLM-generated semantic modules. The tool builds a control-flow graph (CFG), assigns its nodes to modules, and displays a Structural-Semantic Module Graph (SSMG) linked to the source code.

The browser interface supports English and Chinese. Python source is parsed for analysis; the submitted function is not executed. LLM-assisted operations send source code and analysis context to the configured API provider.

## Features

- Construct a CFG with source-line locations and AST-derived calls, definitions, uses, and effect indicators.
- Compare single-stage (`one_shot`) and multi-stage (`multi_stage`) partitioning.
- Inspect module graphs, module sub-CFGs, source-code mappings, and module descriptions.
- Inspect evidence and verification/repair information produced by the multi-stage pipeline.
- Explore variable traces, request LLM explanations, and generate comprehension questions.
- Export intermediate and final results as JSON.

## Quick start

Use Python 3.11 for the setup below. Basic local checks were performed with Python 3.11.5; this repository does not currently pin an exact dependency environment.

Run the commands from the repository root.

### 1. Create an environment and install dependencies

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure the API key

Edit `.env` in the repository root:

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

The current implementation uses the OpenAI Python SDK to call the DeepSeek endpoint, with `https://api.deepseek.com` as the default base URL. Keep `.env` local; it is excluded by `.gitignore`.

The current client does not automatically read `DEEPSEEK_BASE_URL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, or `LLM_TIMEOUT_SECONDS` from `.env`. Configure the endpoint, key environment-variable name, and timeout through the API request's `llm` object instead. Existing environment variables take precedence over values loaded from `.env`.

### 3. Start the application

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe run.py
```

macOS / Linux:

```bash
.venv/bin/python run.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

- Interactive API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

Alternatively, run `launcher.py` with the same Python interpreter to open the browser automatically and choose another port if port 8000 is occupied. The launcher supports `LLM_PARTITION_HOST` and `LLM_PARTITION_PORT`; `run.py` uses `127.0.0.1:8000` directly. The default setup is intended for local use.

## Using the interface

1. Select English or Chinese in the interface.
2. Load the built-in example, paste Python source, or select a Python file.
3. Enter the target function name exactly as it appears in the source.
4. Select a pipeline mode and a model available through your API account.
5. Run partitioning and inspect the result page.

The built-in example is [`samples/demo.py`](samples/demo.py), containing `process_orders`. It demonstrates validation, iteration, computation, and external calls. It is a demonstration input, not an automatic declaration of membership in the paper's evaluation dataset.

Select modules to inspect their source statements, sub-CFGs, and details. Multi-stage results also include evidence and repair metadata. Variable explanation and question-generation features may issue additional LLM requests.

## Partitioning modes

| Mode | Processing |
| --- | --- |
| `one_shot` | Provides the function source, CFG nodes, and CFG edges in one partition-generation prompt, then normalizes the returned partition and builds the graphs. |
| `multi_stage` | Generates semantic hypotheses in Stage AB, generates candidate partitions in Stage C, and performs programmatic verification and repair in Stage D before building the graphs and evidence records. |

These descriptions refer to logical LLM stages, not a guaranteed number of network requests. Invalid JSON can trigger additional format-repair requests. In the multi-stage pipeline, a failed LLM stage can also fall back to deterministic data; inspect `debug.stage_debug` for the stage's `error` and `attempts` fields when checking a run.

### Current defaults

| Setting | Default / behavior |
| --- | --- |
| Model | `deepseek-chat`; this is a code default, not a guarantee of provider availability. |
| Temperature | `0.0` |
| Pipeline mode | The browser initially selects `multi_stage`; the API defaults to `one_shot` when `mode` is omitted. |
| Maximum modules | `7` in the browser and partition API; accepted API range: `6`–`9`. This is an upper bound on the generated count. |
| Repair | Enabled by default in the multi-stage pipeline. |
| Multiple-candidate debug mode | Disabled. Stage C requests and retains one candidate by default. |
| Maximum candidates | `3`. When debug mode is enabled, Stage C requests 2–3 candidates and retains at most `min(max_candidates, 3)`. This is not a guarantee of an exact candidate count. |
| LLM timeout | `120` seconds per configured client request. |

The browser's model field sets both stage models. For direct multi-stage API calls, set `llm.model_ab` and `llm.model_c` explicitly: changing only the top-level `model` does not override their non-empty defaults.

## API example

Run the following Python code from the repository root while the server is running. It uses Python's standard library and explicitly configures both multi-stage models.

```python
import json
from pathlib import Path
from urllib.request import Request, urlopen

model_name = "deepseek-chat"  # Replace with the model you intend to use.
payload = {
    "source_code": Path("samples/demo.py").read_text(encoding="utf-8"),
    "function_name": "process_orders",
    "language": "en",
    "mode": "multi_stage",
    "model": model_name,
    "temperature": 0.0,
    "max_modules": 7,
    "max_candidates": 3,
    "enable_repair": True,
    "multi_candidates_debug": False,
    "llm": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_ab": model_name,
        "model_c": model_name,
        "timeout_sec": 120,
        "max_format_retries": 1,
    },
}

request = Request(
    "http://127.0.0.1:8000/api/partition",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=900) as response:
    result = json.load(response)

print(json.dumps(result["partition"], indent=2))
print(json.dumps(result["debug"], ensure_ascii=False, indent=2))
```

To use the single-stage pipeline, change `mode` to `one_shot`. This mode uses the top-level `model` field.

Available endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Check that the local server is running; does not validate API credentials. |
| `GET /api/sample` | Retrieve the built-in example and its function name. |
| `POST /api/partition` | Build the CFG and partition the selected function. |
| `POST /api/variable-trace` | Build a variable trace from analysis results. |
| `POST /api/variable-trace-explain` | Request an explanation of a variable trace. |
| `POST /api/generate_tasks` | Generate comprehension questions from analysis results. |

See `/docs` for request and response schemas.

## Exported results

Results are written to `app/outputs/en/` or `app/outputs/zh/`, according to the result language.

| File | Contents |
| --- | --- |
| `CFG.json` | Function source, CFG nodes, and edges. |
| `partition.json` | Mapping from CFG node IDs to module IDs. |
| `module_graph.json` | Module graph and module information. |
| `cfg_by_module.json` | Module sub-CFGs. |
| `llm_debug.json` | Prompts, responses, warnings, and pipeline diagnostics. |
| `stage_ab_global_bb.json` | Multi-stage semantic hypotheses. |
| `stage_c_candidate_partition.json` | Multi-stage candidate partitions. |
| `stage_d_verification_and_repair.json` | Candidate reviews, repairs, and the final partition. |
| `module_evidence.json` | Multi-stage module explanations and supporting evidence. |

`app/outputs/latest_manifest.json` identifies the latest output language and directory. Stage files and evidence are written for multi-stage runs. Each run overwrites the files it produces for its language; this is not a run archive. Files from an earlier multi-stage run may remain after a single-stage run, so use the current response and its `mode` when interpreting results.

Outputs contain analyzed source code and LLM context. They are excluded from Git by default, except for `app/outputs/.gitkeep`.

## Project structure

```text
app/
  main.py                       FastAPI application and static file serving
  api.py                        API routes
  models.py                     Request and response models
  services/
    cfg_builder.py              CFG construction and AST metadata
    prompt_builder.py           Single-stage prompt
    pipeline_oneshot.py          Single-stage pipeline
    pipeline_multistage.py       Multi-stage pipeline
    stage_ab_global_bb.py        Semantic hypotheses
    stage_c_partition.py        Candidate synthesis
    postprocess.py              Verification and repair
    module_evidence.py          Evidence assembly
    graph_builder.py            Module graphs and sub-CFGs
    llm_json.py                 API calls and JSON parsing
    exporter.py                 JSON exports
    variable_trace.py           Variable tracing and explanations
    task_generator.py           Comprehension questions
    schemas.py                  Pipeline data models and configuration
  static/                       Browser interface and bundled graph library
  outputs/                      Local generated artifacts
samples/demo.py                 Demonstration function
run.py                         Fixed-port server entry point
launcher.py                    Browser-opening launcher
.env.example                   Configuration template
requirements.txt               Python dependencies
```

## Research use and reproducibility

Record the source revision, exact inputs, prompts, model identifiers for both stages, language, temperature, module limit, candidate settings, repair settings, and dependency versions for an experiment. Preserve individual run outputs separately because the interactive tool overwrites its output files.

This snapshot defaults to `deepseek-chat` and one Stage C candidate. A paper configuration using `deepseek-v4-flash` and two candidates requires separately verified settings and the matching experimental implementation. Enabling debug mode and setting a candidate limit does not by itself guarantee exactly two generated candidates. The current single-stage prompt includes the function source explicitly; use the prompt revision actually used for the reported experiments when reproducing earlier results.

The demo and interactive tool do not by themselves constitute the full RQ1/RQ2 replication package. Evaluation datasets, human reference partitions, study materials, and statistical analysis scripts should be supplied or linked separately.

## Scope and troubleshooting

- The CFG is built from Python's AST. Although internal identifiers use `BB`, nodes are largely statement-level or control-predicate nodes, not maximal compiler basic blocks.
- Exception handling and complex control flow are approximated. AST-derived metadata is not a complete interprocedural data-flow analysis.
- Analyze a named top-level function in the supplied source; cross-file dependencies are not resolved automatically.
- If authentication fails, check `DEEPSEEK_API_KEY` and restart the server after editing `.env`.
- If a model is rejected by the provider, select a model available to your account and configure both stage models for a multi-stage API call.
- A successful multi-stage response can include deterministic fallbacks. Check stage diagnostics before treating it as a successful LLM-generated result.
- If port 8000 is occupied, stop the other local service or use `launcher.py`.

The graph viewer bundles Cytoscape.js in `app/static/vendor/cytoscape.min.js`; its upstream copyright and license notice are retained in that file.
