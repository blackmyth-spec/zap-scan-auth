"""
runner.py
Thực thi từng stage của zap_pipeline.sh theo thứ tự,
cập nhật trạng thái job vào job_store.
"""
import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any

from app import config

logger = logging.getLogger("zap_runner")

# ── In-memory job store ───────────────────────────────────────────────────────
# { job_id: { "status", "stage", "message", "log_path" } }
job_store: Dict[str, Any] = {}

# Thứ tự các stage sẽ chạy
PIPELINE_STAGES = [
    "preflight_debug",
    "preflight_list_dirs",
    "inspect_collection",
    "prelogin",          # bị bỏ qua nếu enable_prelogin=false
    "validate_token",    # bị bỏ qua nếu enable_prelogin=false
    "prepare_zap_config",
    "run_zap_dast",
    "evaluate_result",
]

SKIP_WHEN_NO_PRELOGIN = {"prelogin", "validate_token"}


def _workspace(job_id: str) -> Path:
    """Trả về thư mục workspace riêng cho mỗi job."""
    return Path(config.ZAP_WORKSPACE_ROOT) / job_id


def _build_env(job_id: str, req) -> dict:
    """Xây dựng environment variables truyền vào zap_pipeline.sh."""
    ws = _workspace(job_id)
    env = os.environ.copy()
    env.update(
        {
            # Đường dẫn
            "ZAP_DIR":       config.ZAP_SCRIPTS_DIR,
            "REPO_ROOT":     str(ws),
            "BUILD_NUMBER":  job_id,

            # Tham số scan
            "ZAP_BASE_URL":              req.base_url,
            "RESOLVED_ZAP_BASE_URL":     req.base_url,
            "ZAP_OVERRIDE_URL":          req.base_url,
            "ZAP_ENABLE_PRELOGIN":       "true" if req.enable_prelogin else "false",
            "ZAP_LOGIN_CURL_COMMAND":    req.login_curl_command,
            "ZAP_DOCKER_IMAGE":          req.docker_image,
            "ZAP_SCAN_EXCLUDE_APIS":     req.scan_exclude_apis,
            "ZAP_API_PATH":              req.api_path,
            "ZAP_EXTRA_DOCKER_ARGS":     req.extra_docker_args,
            "COLLECTION_REQUIRES_AUTH_COUNT": "0",  # sẽ được cập nhật sau inspect

            # Tắt proxy trong container
            "HTTP_PROXY": "", "HTTPS_PROXY": "", "http_proxy": "", "https_proxy": "",
            "NO_PROXY": "*", "no_proxy": "*",
        }
    )
    return env


def _run_stage(stage: str, env: dict, cwd: Path, log_path: Path) -> int:
    """
    Chạy một stage của zap_pipeline.sh.
    Ghi toàn bộ stdout+stderr vào log_path.
    Trả về returncode.
    """
    script = Path(config.ZAP_SCRIPTS_DIR) / "zap_pipeline.sh"
    cmd = ["bash", str(script), stage]

    with open(log_path, "a") as log_f:
        log_f.write(f"\n{'='*60}\n[STAGE] {stage}\n{'='*60}\n")
        log_f.flush()

        proc = subprocess.run(
            cmd,
            env=env,
            cwd=str(cwd),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
        )
    return proc.returncode


async def run_pipeline_async(job_id: str, req) -> None:
    """
    Coroutine chính: duyệt qua PIPELINE_STAGES, chạy từng stage.
    Được gọi bởi FastAPI BackgroundTasks.
    """
    ws = _workspace(job_id)
    ws.mkdir(parents=True, exist_ok=True)

    # Tạo zap-tmp/ và zap-out/ trong workspace job
    (ws / "zap-tmp").mkdir(exist_ok=True)
    (ws / "zap-out").mkdir(exist_ok=True)

    log_path = ws / "pipeline.log"
    env = _build_env(job_id, req)

    job_store[job_id]["status"]  = "running"
    job_store[job_id]["log_path"] = str(log_path)

    logger.info("[%s] Pipeline started. Workspace: %s", job_id, ws)

    for stage in PIPELINE_STAGES:
        # Bỏ qua các stage liên quan pre-login nếu tắt
        if stage in SKIP_WHEN_NO_PRELOGIN and not req.enable_prelogin:
            logger.info("[%s] Skipping stage '%s' (prelogin disabled).", job_id, stage)
            continue

        job_store[job_id]["stage"] = stage
        logger.info("[%s] Running stage: %s", job_id, stage)

        rc = await asyncio.get_event_loop().run_in_executor(
            None, _run_stage, stage, env, ws, log_path
        )

        # Sau inspect_collection: đọc requires_auth_count để cập nhật env
        if stage == "inspect_collection":
            auth_count_file = ws / "zap-tmp" / "requires_auth_count.txt"
            if auth_count_file.exists():
                count = auth_count_file.read_text().strip()
                env["COLLECTION_REQUIRES_AUTH_COUNT"] = count
                logger.info("[%s] requires_auth_count=%s", job_id, count)

        if rc != 0:
            msg = f"Stage '{stage}' failed with exit code {rc}."
            logger.error("[%s] %s", job_id, msg)
            job_store[job_id].update(
                {"status": "failed", "message": msg}
            )
            return

    job_store[job_id].update({"status": "success", "message": "Scan completed successfully."})
    logger.info("[%s] Pipeline finished successfully.", job_id)
