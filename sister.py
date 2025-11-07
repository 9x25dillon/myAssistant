from fastapi import FastAPI, Body, Depends, Header, HTTPException
from datetime import datetime, timedelta, timezone
import os
import uuid
from typing import Optional

from ds_adapter import simple_prefix_sql
from coach import coach_update
from rfv import make_rfv_snapshot

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from db import get_session, AALCQueue, RepoRML, RepoRFV, DSQueryLog, engine

app = FastAPI(title="AA/IA minimal surface", version="0.2.0")


# --- Simple API key auth (optional) ---
API_KEY = os.getenv("API_KEY")


def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")


@app.get("/healthz")
def healthz():
    # best-effort DB ping
    try:
        with engine.connect() as conn:
            conn.execute(select(1))
    except OperationalError:
        pass
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ---- AA: lease from PQ (real DB-backed)
@app.post("/pq/lease")
def lease_job(duration_minutes: int = 15, dep: None = Depends(require_api_key)):
    lease_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
    with get_session() as session:
        # Try to lease an existing queued job using SKIP LOCKED when available
        stmt = select(AALCQueue).where(AALCQueue.status == "queued").order_by(AALCQueue.priority.asc(), AALCQueue.created_at.asc())
        if engine.url.get_backend_name().startswith("postgresql"):
            stmt = stmt.with_for_update(skip_locked=True, nowait=False, of=AALCQueue)
        job = session.execute(stmt).scalars().first()
        if job is None:
            # Seed a placeholder job if queue is empty (demo convenience)
            job = AALCQueue(task_spec={"dataset": "speech_conv_v1", "objective": "ASR"}, ifv_spec={"features": ["mfcc", "prosody"]}, priority=100)
            session.add(job)
            session.flush()
        # Mark leased
        job.status = "leased"
        job.leased_until = lease_until
        session.add(job)
        session.flush()
        return {
            "job_id": str(job.id),
            "task_spec": job.task_spec,
            "ifv_spec": job.ifv_spec,
            "leased_until": lease_until.isoformat(),
        }


# ---- IA: publish RFV metadata and link to RML
@app.post("/rfv/publish")
def publish_rfv(payload: dict = Body(...), dep: None = Depends(require_api_key)):
    rml_name = payload.get("name") or payload.get("rml_name")
    rml_arch = payload.get("rml_meta", {}).get("arch") or payload.get("arch")
    rdata_uri = payload.get("rdata_uri")
    labels = payload.get("labels")

    with get_session() as session:
        rml = RepoRML(name=rml_name, arch=rml_arch)
        session.add(rml)
        session.flush()
        rfv = RepoRFV(rml_id=rml.id, rdata_uri=rdata_uri, labels=labels)
        session.add(rfv)
        session.flush()
        return {"rfv_id": str(rfv.id), "rml_id": str(rml.id)}


# ---- DS: RAG/SQL + entropy filter logging
@app.post("/ds/select")
def ds_select(payload: dict = Body(...), dep: None = Depends(require_api_key)):
    query_text = payload.get("query", "")
    top_k = int(payload.get("top_k", 50))
    sql = simple_prefix_sql(query_text, k=top_k)
    # Stub result handle
    result_uri = "s3://bucket/ds/123.parquet"
    # Optional entropy value provided by upstream selection; default None
    entropy_value = payload.get("entropy")

    with get_session() as session:
        log = DSQueryLog(aalc_id=payload.get("aalc_id"), query=query_text, sql_generated=sql, result_uri=result_uri, entropy=entropy_value)
        session.add(log)
        session.flush()
        return {"sql": sql, "result_uri": result_uri, "log_id": log.id}


# ---- ML2: training step stub with coach update
@app.post("/ml2/train_step")
def ml2_train_step(payload: dict = Body(...), dep: None = Depends(require_api_key)):
    metrics = {"loss": 0.231, "wer": 10.4}
    state = {"lr": 1e-3, "top_k": 50, "entropy_floor": 3.0}
    state = coach_update({"dev_loss_delta": 0.0}, {"avg_token_entropy": 2.7}, state)
    return {"metrics": metrics, "state": state, "snapshot_id": str(uuid.uuid4())}


# ---- RFV: directly snapshot and register features (demo)
@app.post("/rfv/snapshot")
def rfv_snapshot(payload: dict = Body(...), dep: None = Depends(require_api_key)):
    try:
        import torch
        dim = int(payload.get("dim", 16))
        batch = int(payload.get("batch", 4))
        # Simple identity feature extractor
        model = torch.nn.Identity()
        sample = torch.zeros((batch, dim))
        snap = make_rfv_snapshot(model, sample_batch=sample, label_map=payload.get("labels"))
        # Register
        with get_session() as session:
            rml = RepoRML(name=payload.get("name"), arch=snap.get("rml_meta"))
            session.add(rml)
            session.flush()
            rfv = RepoRFV(rml_id=rml.id, rdata_uri=snap.get("rdata_uri"), labels=payload.get("labels"))
            session.add(rfv)
            session.flush()
            return {"rfv_id": str(rfv.id), "rdata_uri": snap.get("rdata_uri")}
    except ImportError:
        raise HTTPException(status_code=400, detail="torch not installed; install -r requirements-ml.txt")