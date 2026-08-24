"""Local Stable Diffusion image microservice.

Runs as a separate native process (so it uses the M4 GPU via MPS and keeps the
heavy diffusers/model memory out of the main backend). The backend's ``local``
image provider calls this over HTTP.

Run it:
    python sd_server.py            # serves on http://127.0.0.1:8001

Endpoints:
    GET  /health    -> model + device info (does not load the model)
    POST /warmup    -> load the model now (first call downloads it)
    POST /generate  -> {prompt, width, height, steps?, guidance?} -> image/png bytes
"""
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

import local_sd

app = FastAPI(title="Local SD Image Server", version="1.0.0")


class GenerateRequest(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    steps: Optional[int] = None
    guidance: Optional[float] = None
    negative_prompt: Optional[str] = None


@app.get("/health")
def health():
    model_id = local_sd.resolve_model()
    spec = local_sd.model_spec(model_id)
    return {
        "status": "ok",
        "model": model_id,
        "device": local_sd.resolve_device(),
        "loaded": local_sd._PIPE is not None,
        "native": spec["native"],
        "steps": spec["steps"],
        "guidance": spec["guidance"],
    }


@app.get("/models")
def models():
    """Catalog the UI renders, so the model list lives in one place."""
    return {
        "catalog": [
            {"name": name, **entry} for name, entry in local_sd.MODEL_CATALOG.items()
        ],
        "current": local_sd.resolve_model(),
    }


class SelectModelRequest(BaseModel):
    model: str


@app.post("/models/select")
def select_model(req: SelectModelRequest):
    """Switch the active model.

    The pipeline cache is dropped rather than reloaded here: a first use of an
    uncached model downloads several GB, which would time out this request. The
    next /generate (or /warmup) pays that cost instead.
    """
    model_id = local_sd.resolve_model(req.model)
    os.environ["LOCAL_SD_MODEL"] = model_id
    local_sd._PIPE = None
    local_sd._PIPE_KEY = None
    spec = local_sd.model_spec(model_id)
    return {"status": "selected", "model": model_id,
            "steps": spec["steps"], "guidance": spec["guidance"],
            "download_gb": spec.get("download_gb"), "note": spec.get("note", "")}


@app.post("/warmup")
def warmup():
    """Load the pipeline (downloads the model on first run)."""
    local_sd.get_pipeline()
    return {"status": "warmed", "device": local_sd.resolve_device(),
            "model": local_sd.resolve_model()}


@app.post("/generate")
def generate(req: GenerateRequest):
    try:
        png = local_sd.render_to_bytes(
            req.prompt, req.width, req.height, req.steps, req.guidance,
            negative_prompt=req.negative_prompt
        )
    except Exception as e:  # noqa: BLE001 - report the real reason to the caller
        raise HTTPException(status_code=500, detail=f"Local SD generation failed: {e}")
    return Response(content=png, media_type="image/png")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SD_SERVER_PORT", "8001"))
    uvicorn.run("sd_server:app", host="127.0.0.1", port=port, reload=False)
