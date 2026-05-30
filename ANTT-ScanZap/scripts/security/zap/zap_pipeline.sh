#!/usr/bin/env bash
# =============================================================================
# zap_pipeline.sh
# Tập trung toàn bộ logic bash của Jenkins pipeline ZAP vào một file duy nhất.
#
# Cách dùng:
#   bash zap_pipeline.sh <tên_stage>
#
# Các stage hợp lệ:
#   preflight_debug       - In debug git state + proxy env
#   preflight_list_dirs   - Liệt kê cây thư mục ZAP
#   inspect_collection    - Kiểm tra auth requirements của Postman collection
#   prelogin              - Curl login + extract token
#   validate_token        - Kiểm tra auth_token.txt hợp lệ
#   prepare_zap_config    - Render automation.yaml, copy files, tạo renew_token.sh
#   run_zap_dast          - Chạy Docker ZAP + token auto-refresh nền
#   evaluate_result       - Đánh giá kết quả scan
# =============================================================================

set -eo pipefail
# Lưu ý: không dùng -u vì ZAP_EXTRA_DOCKER_ARGS có thể chưa được export từ Jenkins

# ---------------------------------------------------------------------------
# Stage 1: preflight_debug
# Biến cần có: (không)
# ---------------------------------------------------------------------------
preflight_debug() {
    echo "=== DEBUG CURRENT GIT STATE ==="
    pwd
    git rev-parse --short=8 HEAD
    git branch -a || true
    git show -s --decorate --oneline HEAD || true
    echo "=== DEBUG PROXY ENV ==="
    env | grep -i proxy || true
}

# ---------------------------------------------------------------------------
# Stage 2: preflight_list_dirs
# Biến cần có: REPO_ROOT, ZAP_DIR
# ---------------------------------------------------------------------------
preflight_list_dirs() {
    echo "=== DEBUG ZAP DIR ==="
    ls -lah "$REPO_ROOT"                                   || true
    ls -lah "$REPO_ROOT/nextgen"                           || true
    ls -lah "$REPO_ROOT/nextgen/nextgen-ebanking"          || true
    ls -lah "$REPO_ROOT/nextgen/nextgen-ebanking/security" || true
    ls -lah "$ZAP_DIR"                                     || true
}

# ---------------------------------------------------------------------------
# Stage 3: inspect_collection
# Biến cần có: ZAP_DIR
# ---------------------------------------------------------------------------
inspect_collection() {
    mkdir -p zap-tmp
    python3 "$ZAP_DIR/zap_utils.py" inspect_collection
}

# ---------------------------------------------------------------------------
# Stage 4: prelogin
# Biến cần có: ZAP_LOGIN_CURL_COMMAND, ZAP_DIR
# ---------------------------------------------------------------------------
prelogin() {
    unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    export NO_PROXY='*'
    export no_proxy='*'

    mkdir -p zap-tmp
    echo '[Pre-login] Authenticate payload via direct Curl'
    bash -c "$ZAP_LOGIN_CURL_COMMAND"
    python3 "$ZAP_DIR/zap_utils.py" extract_token
}

# ---------------------------------------------------------------------------
# Stage 5: validate_token
# Biến cần có: ZAP_DIR
# ---------------------------------------------------------------------------
validate_token() {
    test -f zap-tmp/auth_token.txt || {
        echo '[Validate Token] ERROR: missing zap-tmp/auth_token.txt'
        exit 1
    }

    TOKEN="$(cat zap-tmp/auth_token.txt)"
    [ -n "$TOKEN" ] || {
        echo '[Validate Token] ERROR: token empty'
        exit 1
    }

    python3 "$ZAP_DIR/zap_utils.py" validate_token
}

# ---------------------------------------------------------------------------
# Stage 6: prepare_zap_config
# Biến cần có: ZAP_DIR, ZAP_ENABLE_PRELOGIN, RESOLVED_ZAP_BASE_URL,
#              BUILD_NUMBER, ZAP_LOGIN_CURL_COMMAND
# ---------------------------------------------------------------------------
prepare_zap_config() {
    mkdir -p zap-out zap-tmp
    chmod 777 zap-out zap-tmp
    rm -rf zap-tmp/automation.yaml zap-tmp/postman_collection.json zap-tmp/zap_logger.js

    # Lấy token nếu pre-login bật
    TOKEN=""
    if [ "${ZAP_ENABLE_PRELOGIN}" = "true" ] && [ -f zap-tmp/auth_token.txt ]; then
        TOKEN="$(cat zap-tmp/auth_token.txt)"
    fi

    # Tạo transaction ID
    TRANS_ID="$(date +%Y%m%d-%H%M%S)-000000-123456"
    echo "$TRANS_ID" > zap-tmp/trans_id.txt

    # Render automation.yaml từ template
    sed \
        -e "s|{{BASE_URL}}|${RESOLVED_ZAP_BASE_URL}|g" \
        -e "s|{{REPORT_BASENAME}}|zap-report-${BUILD_NUMBER}|g" \
        -e "s|{{AUTH_TOKEN}}|${TOKEN}|g" \
        -e "s|{{TRANS_ID}}|${TRANS_ID}|g" \
        "${ZAP_DIR}/automation.yaml.tpl" > zap-tmp/automation.yaml

    # Copy Postman collection
    cp "${ZAP_DIR}/postman_collection.json" zap-tmp/postman_collection.json
    python3 "${ZAP_DIR}/zap_utils.py" inject_postman

    # Copy ZAP logger script
    cp "${ZAP_DIR}/zap_logger.js" zap-tmp/zap_logger.js

    # Sinh renew_token.sh để chạy BÊN TRONG container.
    # Dùng unquoted heredoc (EOF không có quotes) để $ZAP_LOGIN_CURL_COMMAND
    # được expand ngay lúc sinh file — container sẽ thấy giá trị cứng.
    cat << EOF > zap-tmp/renew_token.sh
#!/bin/bash
mkdir -p /zap/wrk/zap-tmp
cd /zap/wrk
bash -c "${ZAP_LOGIN_CURL_COMMAND}"
python3 zap_utils.py extract_token
EOF
    chmod +x zap-tmp/renew_token.sh

    echo '[Prepare ZAP Config] Generated files:'
    ls -lah zap-tmp
}

# ---------------------------------------------------------------------------
# Stage 7: run_zap_dast
# Biến cần có: ZAP_ENABLE_PRELOGIN, COLLECTION_REQUIRES_AUTH_COUNT,
#              ZAP_BASE_URL_ENV, ZAP_API_PATH_ENV, ZAP_LOGIN_CURL_COMMAND,
#              ZAP_DOCKER_IMAGE, ZAP_EXTRA_DOCKER_ARGS, ZAP_DIR, BUILD_NUMBER
# ---------------------------------------------------------------------------
run_zap_dast() {
    set -o pipefail

    echo "[Run ZAP DAST] Contents of zap-tmp:"
    ls -lah zap-tmp

    # Kiểm tra các file bắt buộc
    test -f zap-tmp/automation.yaml         || { echo '[Run ZAP] ERROR: missing file zap-tmp/automation.yaml'; exit 1; }
    test -f zap-tmp/postman_collection.json || { echo '[Run ZAP] ERROR: missing file zap-tmp/postman_collection.json'; ls -lah zap-tmp; exit 1; }
    test -f zap-tmp/zap_logger.js           || { echo '[Run ZAP] ERROR: missing file zap-tmp/zap_logger.js'; ls -lah zap-tmp; exit 1; }

    # Đọc token
    TOKEN=""
    if [ "${ZAP_ENABLE_PRELOGIN}" = "true" ] && [ -f zap-tmp/auth_token.txt ]; then
        TOKEN="$(cat zap-tmp/auth_token.txt)"
    fi

    if [ "${COLLECTION_REQUIRES_AUTH_COUNT}" != "0" ] && [ -z "$TOKEN" ]; then
        echo "[Run ZAP] ERROR: Collection có private APIs nhưng token runtime đang rỗng."
        exit 1
    fi

    echo '[Run ZAP] Starting ZAP container...'
    echo "[Run ZAP] Base URL = $ZAP_BASE_URL_ENV"
    echo "[Run ZAP] API path = $ZAP_API_PATH_ENV"
    echo "[Run ZAP] token_length = ${#TOKEN}"

    mkdir -p zap-out zap-tmp
    chmod -R 777 zap-out zap-tmp
    ls -ld zap-out zap-tmp

    # Khởi động Token Auto-Refresh nền
    echo '[Run ZAP] Starting Token Auto-Refresh Background Task...'
    if [ "${ZAP_ENABLE_PRELOGIN}" = "true" ]; then
        touch zap-tmp/auth_token.txt
        chmod -R 777 zap-tmp/auth_token.txt
        nohup bash -c '
            while true; do
                sleep 180
                bash -c "$ZAP_LOGIN_CURL_COMMAND > zap-tmp/auth_response_raw.json"
                python3 ms-gke-config-heml-main/nextgen/nextgen-ebanking/security/zap/zap_utils.py extract_token
            done
        ' > zap-tmp/refresh.log 2>&1 &
        echo $! > zap-tmp/refresh.pid
    fi

    chmod -R 777 zap-tmp zap-out

    echo '[Run ZAP] Starting ZAP container...'
    docker run --rm \
        --name "zap-dast-${BUILD_NUMBER}" \
        ${ZAP_EXTRA_DOCKER_ARGS:-} \
        -e HTTP_PROXY= -e HTTPS_PROXY= -e http_proxy= -e https_proxy= \
        -e NO_PROXY='*' -e no_proxy='*' \
        -e ZAP_LOGIN_CURL_COMMAND="$ZAP_LOGIN_CURL_COMMAND" \
        -v "$PWD/zap-tmp/automation.yaml:/zap/wrk/automation.yaml:ro" \
        -v "$PWD/zap-out:/zap/wrk/reports:rw" \
        -v "$PWD/zap-tmp/postman_collection.json:/zap/wrk/config/postman_collection.json:ro" \
        -v "$PWD/zap-tmp/zap_logger.js:/zap/wrk/scripts/zap_logger.js:ro" \
        -v "$PWD/zap-tmp:/zap/wrk/zap-tmp:rw" \
        -v "$PWD/zap-tmp/renew_token.sh:/zap/wrk/renew_token.sh:ro" \
        -v "$PWD/${ZAP_DIR}/zap_utils.py:/zap/wrk/zap_utils.py:ro" \
        "${ZAP_DOCKER_IMAGE}" \
        zap.sh -cmd -autorun /zap/wrk/automation.yaml | tee zap-out/zap-console.log

    # Dừng background refresh
    if [ -f zap-tmp/refresh.pid ]; then
        kill "$(cat zap-tmp/refresh.pid)" || true
    fi
}

# ---------------------------------------------------------------------------
# Stage 8: evaluate_result
# Biến cần có: ZAP_DIR
# ---------------------------------------------------------------------------
evaluate_result() {
    # Chạy trong subshell riêng để tắt -e cục bộ mà không ảnh hưởng script cha
    RC=0
    python3 "$ZAP_DIR/zap_utils.py" evaluate_result || RC=$?

    if [ "$RC" -eq 10 ]; then
        echo '[Evaluate ZAP Result] Gate failed due to High/Critical findings.'
        exit 1
    elif [ "$RC" -ne 0 ]; then
        echo "[Evaluate ZAP Result] ERROR: Could not parse report (RC=$RC)."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Dispatcher — gọi function tương ứng với tên stage truyền vào
# ---------------------------------------------------------------------------
STAGE="${1:-}"
if [ -z "$STAGE" ]; then
    echo "ERROR: Vui lòng truyền tên stage làm tham số đầu tiên." >&2
    echo "  Ví dụ: bash zap_pipeline.sh preflight_debug" >&2
    exit 1
fi

if declare -f "$STAGE" > /dev/null 2>&1; then
    "$STAGE"
else
    echo "ERROR: Stage '$STAGE' không tồn tại trong zap_pipeline.sh" >&2
    exit 1
fi
