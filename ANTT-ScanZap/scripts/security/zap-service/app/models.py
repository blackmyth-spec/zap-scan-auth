"""
models.py
Định nghĩa schema Request/Response cho ZAP FastAPI Service.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"


class ScanRequest(BaseModel):
    base_url: str = Field(
        default="",
        description="Base URL cần scan. Để trống để tự động lấy từ Postman Collection."
    )
    enable_prelogin: bool = Field(
        default=True,
        description="Bật/tắt pre-login trước khi scan."
    )
    login_curl_command: str = Field(
        default="",
        description=(
            "Lệnh curl login đầy đủ. Bắt buộc phải có '> zap-tmp/auth_response_raw.json' ở cuối."
        )
    )
    docker_image: str = Field(
        default="ghcr.io/zaproxy/zaproxy:stable",
        description="Docker image ZAP sẽ được dùng để scan."
    )
    scan_exclude_apis: str = Field(
        default="",
        description="Danh sách API ngăn cách bằng dấu phẩy cần bỏ qua (VD: /api/logout,/api/test)."
    )
    api_path: str = Field(
        default="/api/",
        description="Prefix path API để script xem xét inject token."
    )
    extra_docker_args: str = Field(
        default="",
        description="Tham số docker run bổ sung (VD: --add-host, --network)."
    )


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: Optional[str]    = None
    message: Optional[str]  = None
    log_tail: Optional[str] = None
    report_url: Optional[str] = None


class ScanAcceptedResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    message: str = "Scan job accepted."
