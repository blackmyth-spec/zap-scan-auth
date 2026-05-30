"""
main.py
FastAPI entrypoint — định nghĩa toàn bộ API endpoints.

Endpoints:
  POST   /scan              - Kích hoạt scan mới, trả về job_id
  GET    /status/{job_id}   - Lấy trạng thái + log tail của job
  GET    /report/{job_id}   - Tải xuống báo cáo HTML nếu scan thành công
  GET    /jobs              - Liệt kê tất cả jobs
  DELETE /jobs/{job_id}     - Xoá workspace của job đã xong
  GET    /health            - Health check (dùng cho Docker / K8s)
"""
import logging
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from app import config
from app.models import (
    JobStatus,
    JobStatusResponse,
    ScanAcceptedResponse,
    ScanRequest,
)
from app.runner import job_store, run_pipeline_async

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("zap_service")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ZAP DAST Service",
    description=(
        "REST API wrapping OWASP ZAP DAST pipeline. "
        "Jenkins (hoặc bất kỳ CI nào) có thể gọi POST /scan để kích hoạt "
        "quét bảo mật và polling GET /status/{job_id} để theo dõi kết quả."
    ),
    version="1.0.0",
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Kiểm tra service còn sống. Dùng cho Docker HEALTHCHECK / K8s liveness probe."""
    return {"status": "ok", "service": "zap-dast-service"}


@app.post(
    "/scan",
    response_model=ScanAcceptedResponse,
    status_code=202,
    tags=["Scan"],
    summary="Kích hoạt một ZAP DAST scan mới",
)
async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    """
    Nhận cấu hình scan, đăng ký job và chạy pipeline ở background.
    Trả về **job_id** để client dùng khi polling `/status/{job_id}`.
    """
    # Kiểm tra số lượng scan đang chạy
    running = [j for j in job_store.values() if j["status"] == "running"]
    if len(running) >= config.MAX_CONCURRENT_SCANS:
        raise HTTPException(
            status_code=429,
            detail=f"Đã đạt giới hạn {config.MAX_CONCURRENT_SCANS} concurrent scan. Thử lại sau.",
        )

    job_id = str(uuid.uuid4())
    job_store[job_id] = {
        "status":   JobStatus.PENDING,
        "stage":    None,
        "message":  "Queued.",
        "log_path": None,
        "request":  req.model_dump(),
    }

    background_tasks.add_task(run_pipeline_async, job_id, req)
    logger.info("New scan job accepted: %s | base_url=%s", job_id, req.base_url)

    return ScanAcceptedResponse(job_id=job_id)


@app.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    tags=["Scan"],
    summary="Lấy trạng thái của một scan job",
)
async def get_status(job_id: str):
    """
    Trả về trạng thái hiện tại + `log_tail` (50 dòng cuối) của pipeline log.
    Khi `status == success | failed`, scan đã hoàn tất.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' không tồn tại.")

    # Lấy log tail
    log_tail = None
    log_path = job.get("log_path")
    if log_path and Path(log_path).exists():
        lines = Path(log_path).read_text(errors="replace").splitlines()
        log_tail = "\n".join(lines[-config.LOG_TAIL_LINES :])

    # URL download report nếu đã xong
    report_url = None
    if job["status"] == JobStatus.SUCCESS:
        report_url = f"/report/{job_id}"

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        stage=job.get("stage"),
        message=job.get("message"),
        log_tail=log_tail,
        report_url=report_url,
    )


@app.get(
    "/report/{job_id}",
    tags=["Scan"],
    summary="Tải xuống báo cáo HTML của job đã hoàn thành",
)
async def download_report(job_id: str):
    """
    Trả về file báo cáo HTML đầu tiên tìm thấy trong `zap-out/` của job.
    Chỉ khả dụng khi `status == success`.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' không tồn tại.")
    if job["status"] != JobStatus.SUCCESS:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' chưa hoàn thành (status={job['status']}).",
        )

    ws = Path(config.ZAP_WORKSPACE_ROOT) / job_id / "zap-out"
    html_files = list(ws.glob("*.html"))
    if not html_files:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy báo cáo HTML trong zap-out/.",
        )

    return FileResponse(
        path=str(html_files[0]),
        media_type="text/html",
        filename=html_files[0].name,
    )


@app.get(
    "/logs/{job_id}",
    response_class=PlainTextResponse,
    tags=["Scan"],
    summary="Xem toàn bộ pipeline log của job",
)
async def get_full_log(job_id: str):
    """Trả về toàn bộ nội dung pipeline.log dưới dạng plain text."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' không tồn tại.")

    log_path = job.get("log_path")
    if not log_path or not Path(log_path).exists():
        return PlainTextResponse("(chưa có log)")

    return PlainTextResponse(Path(log_path).read_text(errors="replace"))


@app.get(
    "/jobs",
    tags=["Management"],
    summary="Liệt kê tất cả scan jobs",
)
async def list_jobs():
    """Trả về danh sách tóm tắt tất cả job (bao gồm cả đã xong)."""
    return [
        {
            "job_id": jid,
            "status": jdata["status"],
            "stage":  jdata.get("stage"),
        }
        for jid, jdata in job_store.items()
    ]


@app.delete(
    "/jobs/{job_id}",
    tags=["Management"],
    summary="Xoá workspace của một job đã xong",
)
async def delete_job(job_id: str):
    """Xoá workspace disk + xoá khỏi job_store. Chỉ cho phép khi job KHÔNG đang chạy."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' không tồn tại.")
    if job["status"] == JobStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail="Không thể xoá job đang chạy.",
        )

    ws = Path(config.ZAP_WORKSPACE_ROOT) / job_id
    if ws.exists():
        import shutil
        shutil.rmtree(ws, ignore_errors=True)

    del job_store[job_id]
    return {"message": f"Job '{job_id}' đã được xoá."}
