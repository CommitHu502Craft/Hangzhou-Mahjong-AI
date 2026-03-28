from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DEFAULT_LEAD_LOG_PATH = Path("logs/leads.ndjson")
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(..., min_length=3, max_length=160)
    company: str = Field(default="", max_length=120)
    goal: str = Field(..., min_length=1, max_length=1000)


class LeadSubmitResponse(BaseModel):
    status: str
    lead_id: str
    received_at: str
    message: str


def _resolve_log_path() -> Path:
    override = os.getenv("LEAD_LOG_PATH", "").strip()
    if override:
        return Path(override)
    return DEFAULT_LEAD_LOG_PATH


def _payload_from_model(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return]
    return model.dict()  # type: ignore[no-any-return]


def _clean_and_validate(payload: Dict[str, Any]) -> Dict[str, str]:
    cleaned = {
        "name": str(payload.get("name", "")).strip(),
        "email": str(payload.get("email", "")).strip(),
        "company": str(payload.get("company", "")).strip(),
        "goal": str(payload.get("goal", "")).strip(),
    }

    if not cleaned["name"]:
        raise HTTPException(status_code=422, detail="姓名不能为空")
    if not cleaned["goal"]:
        raise HTTPException(status_code=422, detail="业务目标不能为空")
    if not EMAIL_REGEX.match(cleaned["email"]):
        raise HTTPException(status_code=422, detail="邮箱格式无效")
    return cleaned


def create_app(lead_log_path: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="Hangzhou Mahjong API", version="0.1.0")
    app.state.lead_log_path = lead_log_path or _resolve_log_path()

    origins_env = os.getenv("FRONTEND_ORIGINS", "")
    if origins_env.strip():
        origins = [x.strip() for x in origins_env.split(",") if x.strip()]
    else:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/leads", response_model=LeadSubmitResponse)
    def submit_lead(lead: LeadCreate, request: Request) -> LeadSubmitResponse:
        payload = _payload_from_model(lead)
        cleaned = _clean_and_validate(payload)

        lead_id = uuid.uuid4().hex[:12]
        received_at = datetime.now(timezone.utc).isoformat()
        record = {
            "lead_id": lead_id,
            "received_at": received_at,
            "name": cleaned["name"],
            "email": cleaned["email"],
            "company": cleaned["company"],
            "goal": cleaned["goal"],
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
        }

        log_path: Path = request.app.state.lead_log_path
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"写入线索日志失败: {exc}") from exc

        return LeadSubmitResponse(
            status="ok",
            lead_id=lead_id,
            received_at=received_at,
            message="已提交成功",
        )

    return app


app = create_app()

