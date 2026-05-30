"""
config.py
Cấu hình tập trung cho ZAP FastAPI Service.
Đọc từ biến môi trường (inject bởi docker-compose / Jenkins).
"""
import os

# ── Đường dẫn trong container ────────────────────────────────────────────────
# Thư mục chứa zap_pipeline.sh, zap_utils.py, templates, v.v.
ZAP_SCRIPTS_DIR: str = os.getenv("ZAP_SCRIPTS_DIR", "/app/zap-scripts")

# Workspace chứa zap-tmp/ và zap-out/ cho từng scan job
# Mỗi job sẽ được tạo thư mục con: {ZAP_WORKSPACE_ROOT}/{job_id}/
ZAP_WORKSPACE_ROOT: str = os.getenv("ZAP_WORKSPACE_ROOT", "/app/workspace")

# ── Cấu hình ZAP mặc định ────────────────────────────────────────────────────
ZAP_DEFAULT_DOCKER_IMAGE: str = os.getenv(
    "ZAP_DEFAULT_DOCKER_IMAGE",
    "ghcr.io/zaproxy/zaproxy:stable"
)

# ── Giới hạn concurrent scan ─────────────────────────────────────────────────
# Số lượng scan job chạy song song tối đa
MAX_CONCURRENT_SCANS: int = int(os.getenv("MAX_CONCURRENT_SCANS", "3"))

# ── Log ──────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── Số dòng log tail trả về khi query status ─────────────────────────────────
LOG_TAIL_LINES: int = int(os.getenv("LOG_TAIL_LINES", "50"))
