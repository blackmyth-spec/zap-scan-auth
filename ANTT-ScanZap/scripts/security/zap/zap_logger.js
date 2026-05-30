function sendingRequest(msg, initiator, helper) {
    var url = msg.getRequestHeader().getURI().toString();
    var method = msg.getRequestHeader().getMethod();
    
    /*
    print('================ ZAP REQUEST ================');
    print('[ZAP-Log] -> ' + method + ' ' + url);
    //Log request
    */
    

    // Đọc token mới nhất từ file (được Jenkins update liên tục ở background)
    var token = "";
    try {
        var Files = Java.type("java.nio.file.Files");
        var Paths = Java.type("java.nio.file.Paths");
        var String = Java.type("java.lang.String");
        token = new String(Files.readAllBytes(Paths.get("/zap/wrk/zap-tmp/auth_token.txt"))).trim();
    } catch (e) {
        // Fallback or ignore if file not found
    }
    var reqBody = msg.getRequestBody().toString();
    var bodyInjected = false;

    // Tự động tìm và thay thế accessToken trong Body nếu có (phù hợp mọi Postman file)
    if (reqBody && reqBody.length > 0 && token && token !== "" && token !== "{{AUTH_TOKEN}}") {
        var newBody = reqBody;

        // Thay thế định dạng JSON: "accessToken": "giá_trị_bất_kỳ"
        newBody = newBody.replace(/"accessToken"\s*:\s*"[^"]*"/g, '"accessToken":"' + token + '"');

        // Thay thế định dạng Form/URL-encoded: accessToken=giá_trị_bất_kỳ
        newBody = newBody.replace(/accessToken=[^&]*/g, 'accessToken=' + token);

        // Thay thế ZAP_DYNAMIC_TOKEN trong body (đã được Python inject)
        newBody = newBody.replace(/ZAP_DYNAMIC_TOKEN/g, token);

        if (newBody !== reqBody) {
            msg.setRequestBody(newBody);
            msg.getRequestHeader().setContentLength(msg.getRequestBody().length());
            reqBody = newBody;
            bodyInjected = true;
            print('    [Auth] Injected accessToken into Body');
        }
    }

    var authHeader = msg.getRequestHeader().getHeader('Authorization');
    if (authHeader) {
        // Replace dynamic token in Authorization header
        if (authHeader.indexOf('ZAP_DYNAMIC_TOKEN') > -1 && token !== "") {
            authHeader = authHeader.replace('ZAP_DYNAMIC_TOKEN', token);
            msg.getRequestHeader().setHeader('Authorization', authHeader);
        }
    } else {
        // Chỉ thêm Authorization Header nếu CHƯA inject token vào body
        if (!bodyInjected && token && token !== "" && token !== "{{AUTH_TOKEN}}") {
            msg.getRequestHeader().setHeader('Authorization', 'Bearer ' + token);
            print('    [Auth] Added missing Authorization header');
        }
    }
    /*
    print('    [Req Headers]:');
    print(msg.getRequestHeader().getHeadersAsString());

    var reqBody = msg.getRequestBody().toString();
    if (reqBody && reqBody.length > 0) {
        print('    [Req Body]:\n' + reqBody);
    }
    print('---------------------------------------------');
    //Log request header và request body
    */
    
}


function responseReceived(msg, initiator, helper) {
    var url = msg.getRequestHeader().getURI().toString();
    var method = msg.getRequestHeader().getMethod();
    var status = msg.getResponseHeader().getStatusCode();
    /*
    print('================ ZAP RESPONSE ===============');
    print('[ZAP-Log] <- ' + status + ' ' + method + ' ' + url);

    print('    [Res Headers]:');
    print(msg.getResponseHeader().getHeadersAsString())
    //Log response header 
    */
    var resBody = msg.getResponseBody().toString();
    /*
    if (resBody && resBody.length > 0) {
        print('    [Res Body]:\n' + resBody);
    }
    print('=============================================');
    //Log response body
    */
    

    // --- Xử lý tự động Renew Token & Retry ---

    var resBodyLower = resBody ? resBody.toLowerCase() : "";
    var isAuthError = false;

    if (status === 401 || status === 403) {
        isAuthError = true;
    } else if (resBodyLower !== "") {
        if (resBodyLower.indexOf("invalid token") !== -1 ||
            resBodyLower.indexOf("token invalid") !== -1 ||
            resBodyLower.indexOf("token expired") !== -1 ||
            resBodyLower.indexOf("unauthorized") !== -1) {
            isAuthError = true;
        }
    }

    var ScriptVars = Java.type("org.zaproxy.zap.extension.script.ScriptVars");
    var JString = Java.type("java.lang.String");
    var urlHash = Math.abs(new JString(url).hashCode());
    var retryKey = "r_" + urlHash;

    if (!isAuthError) {
        // Reset counter về 0 nếu request thành công để tính "liên tiếp" thay vì "tổng số"
        ScriptVars.setGlobalVar(retryKey, "0");
    }


    if (isAuthError) {
        var retryCount = ScriptVars.getGlobalVar(retryKey);
        retryCount = retryCount ? parseInt(retryCount) : 0;

        if (retryCount >= 3) {
            print('[Retry] Vượt quá 3 lần retry cho: ' + url + '. Ngừng retry, tiếp tục scan request này với token hiện tại (miss author)!');
            return;
        }

        retryCount++;
        ScriptVars.setGlobalVar(retryKey, retryCount.toString());
        print('[Retry] Lỗi xác thực phát hiện (Lần ' + retryCount + '/3). Đang renew token...');

        // Gọi OS command để chạy file renew_token.sh
        try {
            var Runtime = Java.type("java.lang.Runtime");
            //var process = Runtime.getRuntime().exec("/bin/sh /zap/wrk/renew_token.sh");
            var StringArray = Java.type("java.lang.String[]");
            var cmd = new StringArray(3);
            cmd[0] = "/bin/sh";
            cmd[1] = "-c";
            cmd[2] = "/zap/wrk/renew_token.sh 2>&1";
            var process = Runtime.getRuntime().exec(cmd);
            
            var BufferedReader = Java.type("java.io.BufferedReader");
            var InputStreamReader = Java.type("java.io.InputStreamReader");
            var reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            var line;
            while ((line = reader.readLine()) != null) {
                print('[Renew-Token-Log] ' + line);
            }

            process.waitFor();
            if (process.exitValue() !== 0) {
                print('[Retry-Error] renew_token.sh chạy thất bại với exit code: ' + process.exitValue());
            }
        } catch (e) {
            //print('[Retry-Error] Lỗi khi renew token: ' + e);
            print('[Retry-Error] Lỗi khi thực thi renew token.sh: ' + e);
        }

        // Đọc lại token mới
        var newToken = "";
        try {
            var Files = Java.type("java.nio.file.Files");
            var Paths = Java.type("java.nio.file.Paths");
            var String = Java.type("java.lang.String");
            newToken = new String(Files.readAllBytes(Paths.get("/zap/wrk/zap-tmp/auth_token.txt"))).trim();
        } catch (e) { }

        if (newToken && newToken !== "") {
            // Check xem token có thực sự mới không
            var oldAuth = msg.getRequestHeader().getHeader('Authorization');
            var oldBody = msg.getRequestBody().toString();
            if ((oldAuth && oldAuth.indexOf(newToken) !== -1) || (oldBody && oldBody.indexOf(newToken) !== -1)) {
                print('[Retry] CẢNH BÁO: Token mới đọc được GIỐNG HỆT token cũ! (Do API trả về token không đổi hoặc Curl bị lỗi)');
            } else {
                print('[Retry] Đã lấy được token MỚI (độ dài: ' + newToken.length + ')');
            }

            var tokenInjected = false;

            // Cập nhật token trong Body nếu có
            var reqBody = msg.getRequestBody().toString();
            if (reqBody && reqBody.length > 0) {
                var newBody = reqBody;
                newBody = newBody.replace(/"accessToken"\s*:\s*"[^"]*"/g, '"accessToken":"' + newToken + '"');
                newBody = newBody.replace(/accessToken=[^&]*/g, 'accessToken=' + newToken);
                newBody = newBody.replace(/ZAP_DYNAMIC_TOKEN/g, newToken);

                if (newBody !== reqBody) {
                    msg.setRequestBody(newBody);
                    msg.getRequestHeader().setContentLength(msg.getRequestBody().length());
                    print('    [Retry-Auth] Đã cập nhật accessToken vào Body');
                    tokenInjected = true;
                }
            }

            // Cập nhật Authorization header
            var authHeader = msg.getRequestHeader().getHeader('Authorization');
            if (authHeader) {
                // Nếu đã có header Authorization, cập nhật lại token
                msg.getRequestHeader().setHeader('Authorization', 'Bearer ' + newToken);
            } else if (!tokenInjected) {
                // Chỉ tự động thêm header Authorization nếu chưa inject token vào body
                msg.getRequestHeader().setHeader('Authorization', 'Bearer ' + newToken);
                print('    [Retry-Auth] Đã thêm missing Authorization header');
            }

            print('[Retry] Đã gắn token mới, tiến hành gửi lại request...');
            var HttpSender = Java.type("org.parosproxy.paros.network.HttpSender");
            var sender = new HttpSender(initiator);
            sender.sendAndReceive(msg);
            print('[Retry] Kết quả sau khi thử lại: ' + msg.getResponseHeader().getStatusCode());
        }
    }
}
