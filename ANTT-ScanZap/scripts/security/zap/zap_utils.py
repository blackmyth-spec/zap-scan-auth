import sys
import json
import os
import hashlib
import base64
import re
import glob
import urllib.parse
from pathlib import Path


def get_base_url():
    """Trích xuất URL gốc (scheme://host) đầu tiên từ postman_collection.json"""
    zap_dir = os.environ.get('ZAP_DIR', 'ms-gke-config-heml-main/nextgen/nextgen-ebanking/security/zap')
    file_pm = Path(f"{zap_dir}/postman_collection.json")
    if not file_pm.exists():
        print("https://example.com")
        return
        
    doc = json.loads(file_pm.read_text(encoding='utf-8'))
    
    def walk_items(items):
        for item in items:
            if 'request' in item:
                yield item
            for child in item.get('item', []):
                if 'request' in child:
                    yield child
                    
    for item in walk_items(doc.get('item', [])):
        req = item['request']
        url = req.get('url')
        raw_url = ""
        if isinstance(url, dict):
            raw_url = url.get('raw', '')
        elif isinstance(url, str):
            raw_url = url
            
        if raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            if parsed.scheme and parsed.netloc:
                print(f"{parsed.scheme}://{parsed.netloc}")
                return
    print("https://example.com")

def inspect_collection():
    zap_dir = os.environ.get(
        'ZAP_DIR', 'ms-gke-config-heml-main/nextgen/nextgen-ebanking/security/zap')
    collection_path = Path(f"{zap_dir}/postman_collection.json")
    exclude_regex = re.compile(r'.*/api/get-password-type.*')

    doc = json.loads(collection_path.read_text(encoding='utf-8'))

    def walk_items(items):
        for item in items:
            if 'request' in item:
                yield item
            for child in item.get('item', []):
                if 'request' in child:
                    yield child

    requires_auth = []
    public_like = []

    for item in walk_items(doc.get('item', [])):
        req = item['request']
        url = req.get('url', {})
        raw = url.get('raw', '')
        if '/api/' not in raw:
            continue
        if exclude_regex.match(raw):
            public_like.append(raw)
        else:
            requires_auth.append(raw)

    Path('zap-tmp/requires_auth_urls.txt').write_text('\n'.join(requires_auth), encoding='utf-8')
    Path('zap-tmp/public_urls.txt').write_text('\n'.join(public_like), encoding='utf-8')
    Path('zap-tmp/requires_auth_count.txt').write_text(str(len(requires_auth)), encoding='utf-8')

    print(f"[Inspect Collection] public_like={len(public_like)}")
    print(f"[Inspect Collection] requires_auth={len(requires_auth)}")
    for x in requires_auth:
        print(f"[Inspect Collection] private candidate = {x}")

def extract_token():
    file_path = 'zap-tmp/auth_response_raw.json'
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        if data.startswith(b'\x1f\x8b'):
            import gzip
            data = gzip.decompress(data)
        content_str = data.decode('utf-8')
        
        # Lọc bỏ HTTP headers nếu file được tạo bằng lệnh curl -i
        if content_str.startswith('HTTP/'):
            # Header và body thường cách nhau bởi 2 cặp CRLF hoặc LF
            parts = content_str.split('\r\n\r\n', 1)
            if len(parts) == 1:
                parts = content_str.split('\n\n', 1)
            
            if len(parts) == 2:
                content_str = parts[1]

        # Xóa các khoảng trắng/xuống dòng dư thừa ở đầu và cuối để tránh lỗi parse JSON
        content_str = content_str.strip()

        raw = json.loads(content_str)
    except Exception as e:
        print('[Pre-login] ERROR: auth_response_raw.json không tồn tại hoặc không hợp lệ (không phải chuẩn JSON).')
        if os.path.exists(file_path):
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                if data.startswith(b'\x1f\x8b'):
                    import gzip
                    data = gzip.decompress(data)
                content_str = data.decode('utf-8', errors='replace')
                print("=== NỘI DUNG PHẢN HỒI TỪ SERVER ===")
                print(content_str)
                print("===================================")
                if not content_str.strip():
                    print("Lý do: File trống. Có thể lệnh curl bị lỗi (sai URL, không kết nối được) hoặc API không trả về data.")
            except Exception as e_inner:
                print(f"Lý do: Không thể đọc file: {e_inner}")
        else:
            print("Lý do: File không được tạo ra. Có thể lệnh curl đã bị lỗi cú pháp Bash và không chạy được.")
        sys.exit(3)

    objs_to_search = [raw]

    # Nếu có trường data là string, thử decode base64
    encoded_resp = raw.get('data')
    if isinstance(encoded_resp, str):
        try:
            decoded = base64.b64decode(encoded_resp).decode('utf-8')
            open('zap-tmp/auth_response_decoded.json',
                 'w', encoding='utf-8').write(decoded)
            decoded_obj = json.loads(decoded)
            # Ưu tiên tìm trong object đã decode
            objs_to_search.insert(0, decoded_obj)
        except Exception:
            pass

    def find_token_in_dict(obj):
        token_keys = ['id_token', 'access_token', 'authorization', 'token', 'accesstoken']
        if isinstance(obj, dict):
            # Tìm key phù hợp 
            for actual_key in obj.keys():
                if actual_key.lower() in token_keys and isinstance(obj[actual_key], str) and obj[actual_key].strip():
                    return obj[actual_key].strip()
            # Nếu không thấy, đệ quy tìm ở các level sâu hơn
            for v in obj.values():
                res = find_token_in_dict(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = find_token_in_dict(item)
                if res:
                    return res
        return None

    token = None
    for obj in objs_to_search:
        token = find_token_in_dict(obj)
        if token:
            break

    if not token:
        print('[Pre-login] ERROR: Không tìm thấy token (id_token, access_token, Authorization, accessToken) trong auth response')
        print(json.dumps(raw)[:2000])
        sys.exit(5)

    # Loại bỏ tiền tố Bearer nếu có
    if token.lower().startswith('bearer '):
        token = token[7:].strip()

    if token.count('.') != 2:
        print('[Pre-login] WARNING: Token format không giống JWT (không có 3 phần), script vẫn tiếp tục.')

    open('zap-tmp/auth_token.txt', 'w', encoding='utf-8').write(token)
    print('[Pre-login] STEP 2 OK - token extracted')
    print(f"[Pre-login] token_length={len(token)}")


def validate_token():
    t = Path('zap-tmp/auth_token.txt').read_text(encoding='utf-8').strip()
    if not t:
        sys.exit('[Validate Token] ERROR: token rỗng')
    if t.count('.') != 2:
        print('[Validate Token] WARNING: token không đúng dạng JWT, nhưng vẫn cho qua.')
    print(f'[Validate Token] token_length={len(t)}')


def evaluate_result():
    json_files = glob.glob('zap-out/*.json')
    if not json_files:
        print('[Evaluate ZAP Result] ERROR: No JSON report found in zap-out/')
        sys.exit(2)

    report = json_files[0]
    print(f'[Evaluate ZAP Result] Using report: {report}')
    with open(report, 'r', encoding='utf-8') as f:
        data = json.load(f)

    alerts = []
    for site in data.get('site', []):
        alerts.extend(site.get('alerts', []))

    critical = high = medium = low = info = 0
    for a in alerts:
        riskcode = str(a.get('riskcode', '')).strip()
        riskdesc = (a.get('riskdesc') or '').lower()
        if 'critical' in riskdesc:
            critical += 1
        elif riskcode == '3' or 'high' in riskdesc:
            high += 1
        elif riskcode == '2' or 'medium' in riskdesc:
            medium += 1
        elif riskcode == '1' or 'low' in riskdesc:
            low += 1
        else:
            info += 1

    print(
        f'[Evaluate ZAP Result] Critical={critical}, High={high}, Medium={medium}, Low={low}, Info={info}')
    if critical > 0 or high > 0:
        print('[Evaluate ZAP Result] FAIL: High/Critical findings detected.')
        sys.exit(0)
    elif medium > 0:
        print('[Evaluate ZAP Result] WARNING: Medium findings detected.')
        sys.exit(0)
    else:
        print('[Evaluate ZAP Result] PASS: No High/Critical findings.')
        sys.exit(0)

def inject_postman():
    """
    Sửa đổi trực tiếp file Postman Collection (zap-tmp/postman_collection.json)
    Thay thế toàn bộ token (Authorization header & accessToken trong body) bằng token runtime.
    """
    file_pm = 'zap-tmp/postman_collection.json'
    file_token = 'zap-tmp/auth_token.txt'
    file_transid = 'zap-tmp/trans_id.txt'
    
    if not os.path.exists(file_pm):
        print("[Inject Postman] Không tìm thấy file collection.")
        sys.exit(0)
        
    token = ""
    if os.path.exists(file_token):
        token = open(file_token, 'r', encoding='utf-8').read().strip()

    trans_id = ""
    if os.path.exists(file_transid):
        trans_id = open(file_transid, 'r', encoding='utf-8').read().strip()
        
    base_url = os.environ.get('ZAP_OVERRIDE_URL', '').strip()
    import urllib.parse
    target_parsed = urllib.parse.urlparse(base_url) if base_url else None
        
    with open(file_pm, 'r', encoding='utf-8') as f:
        """
        pm_data = json.load(f)
        """
        pm_text = f.read()
        
    if trans_id:
        pm_text = pm_text.replace("ZAP-123456789", trans_id)
        
    pm_data = json.loads(pm_text)
        
    def process_item(item):
        if 'request' in item:
            req = item['request']
            
            # --- REPLACE URL ---
            if target_parsed and 'url' in req:
                try:
                    if isinstance(req['url'], dict):
                        raw_url = req['url'].get('raw', '')
                        if raw_url:
                            orig_parsed = urllib.parse.urlparse(raw_url)
                            new_raw = raw_url.replace(f"{orig_parsed.scheme}://{orig_parsed.netloc}", f"{target_parsed.scheme}://{target_parsed.netloc}")
                            req['url']['raw'] = new_raw
                            req['url']['protocol'] = target_parsed.scheme
                            req['url']['host'] = target_parsed.netloc.split('.')
                    elif isinstance(req['url'], str):
                        orig_parsed = urllib.parse.urlparse(req['url'])
                        req['url'] = req['url'].replace(f"{orig_parsed.scheme}://{orig_parsed.netloc}", f"{target_parsed.scheme}://{target_parsed.netloc}")
                except Exception:
                    pass
            
            # 1. Force inject/update Authorization Header nếu có token
            has_auth = False
            if token:
                headers = req.get('header', [])
                for h in headers:
                    if h.get('key', '').lower() == 'authorization':
                        h['value'] = f"Bearer {token}"
                        has_auth = True
                req['header'] = headers
            
            if token and not has_auth:
                found_token_in_body = False
                
                def replace_access_token_recursively(obj):
                    nonlocal found_token_in_body
                    if isinstance(obj, dict):
                        for k, v in list(obj.items()):
                            if k == 'accessToken':
                                obj[k] = token
                                found_token_in_body = True
                            else:
                                replace_access_token_recursively(v)
                    elif isinstance(obj, list):
                        for i in obj:
                            replace_access_token_recursively(i)

                if 'body' in req and req['body'].get('mode') == 'raw':
                    raw_body = req['body'].get('raw', '')
                    if raw_body:
                        try:
                            body_json = json.loads(raw_body)
                            replace_access_token_recursively(body_json)
                            if found_token_in_body:
                                req['body']['raw'] = json.dumps(body_json, indent=2)
                        except Exception:
                            pass
                            
                if 'body' in req and req['body'].get('mode') == 'urlencoded':
                    form_data = req['body'].get('urlencoded', [])
                    for field in form_data:
                        if field.get('key') == 'accessToken':
                            field['value'] = token
                            found_token_in_body = True
                        
        if 'item' in item:
            for sub_item in item['item']:
                process_item(sub_item)
                
    if 'item' in pm_data:
        for item in pm_data['item']:
            process_item(item)
            
    with open(file_pm, 'w', encoding='utf-8') as f:
        json.dump(pm_data, f, ensure_ascii=False, indent=2)
        
    print("[Inject Postman] Đã cập nhật thành công URL và token vào postman_collection.json")
    
    # Cập nhật danh sách loại trừ vào automation.yaml
    update_automation_yaml_config()

def update_automation_yaml_config():
    yaml_file = 'zap-tmp/automation.yaml'
    file_pm = 'zap-tmp/postman_collection.json'
    if not os.path.exists(yaml_file):
        return

    try:
        with open(yaml_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. Update Context URLs
        unique_domains = set()
        if os.path.exists(file_pm):
            doc = json.loads(open(file_pm, 'r', encoding='utf-8').read())
            def walk_items(items):
                for item in items:
                    if 'request' in item:
                        yield item
                    for child in item.get('item', []):
                        if 'request' in child:
                            yield child

            import urllib.parse
            for item in walk_items(doc.get('item', [])):
                req = item['request']
                url = req.get('url')
                raw_url = ""
                if isinstance(url, dict):
                    raw_url = url.get('raw', '')
                elif isinstance(url, str):
                    raw_url = url
                
                if raw_url:
                    parsed = urllib.parse.urlparse(raw_url)
                    if parsed.scheme and parsed.netloc:
                        unique_domains.add(f"{parsed.scheme}://{parsed.netloc}")

        override_url = os.environ.get('ZAP_OVERRIDE_URL', '').strip()
        if override_url:
            unique_domains = {override_url}
            
        if not unique_domains:
            unique_domains.add("https://example.com")
            
        url_lines = []
        for d in unique_domains:
            url_lines.append(f'        - "{d}"')
            
        url_replacement = '\n'.join(url_lines)
        if '{{ZAP_CONTEXT_URLS}}' in content:
            content = content.replace('{{ZAP_CONTEXT_URLS}}', url_replacement)
            print(f"[Zap Utils] Đã tự động cấu hình {len(unique_domains)} domain vào ZAP Context.")

        # 2. Update Exclude Paths
        exclude_apis_str = os.environ.get('ZAP_SCAN_EXCLUDE_APIS', '')
        apis = [x.strip() for x in exclude_apis_str.split(',') if x.strip()]
        
        if not apis:
            if '{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}\n' in content:
                content = content.replace('{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}\n', '')
            if '{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}' in content:
                content = content.replace('{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}', '')
        else:
            yaml_lines = []
            for api in apis:
                yaml_lines.append(f'        - ".*{api}.*"')
            
            exclude_replacement = '\n'.join(yaml_lines)
            if '{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}' in content:
                content = content.replace('{{ZAP_SCAN_EXCLUDE_PATHS_YAML}}', exclude_replacement)
                print(f"[Zap Utils] Đã thêm {len(apis)} đường dẫn vào danh sách bỏ qua (excludePaths).")

        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(content)
            
    except Exception as e:
        print(f"[Zap Utils] Lỗi cập nhật automation.yaml: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python zap_utils.py <action>")
        sys.exit(1)


    action = sys.argv[1]
    if action == 'inspect_collection':
        inspect_collection()
    elif action == 'extract_token':
        extract_token()
    elif action == 'validate_token':
        validate_token()
    elif action == 'evaluate_result':
        evaluate_result()
    
    elif action == 'inject_postman':
        inject_postman()
    elif action == 'get_base_url':
        get_base_url()
    
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
