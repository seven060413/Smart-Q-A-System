# src/captcha.py
import os
import json  # 👈 必须加上这个
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.captcha.v20190722 import captcha_client, models
from .errors import ApiError

# 读取环境变量
APP_ID = int(os.getenv("TENCENT_CAPTCHA_APP_ID", "0"))
APP_SECRET_KEY = os.getenv("TENCENT_CAPTCHA_SECRET_KEY", "")
SECRET_ID = os.getenv("TENCENT_SECRET_ID", "")
SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", "")

def verify_tencent_captcha(ticket: str, randstr: str, request=None) -> bool:
    if not all([APP_ID, APP_SECRET_KEY, SECRET_ID, SECRET_KEY, ticket, randstr]):
        raise ApiError(400, "CAPTCHA_CONFIG_ERROR", "验证码配置不完整，请检查 .env")

    try:
        # 1. 实例化认证对象
        cred = credential.Credential(SECRET_ID, SECRET_KEY)
        
        # 2. 实例化 HTTP 选项
        http_profile = HttpProfile()
        http_profile.endpoint = "captcha.tencentcloudapi.com"

        # 3. 实例化客户端配置
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile

        # 4. 实例化客户端
        client = captcha_client.CaptchaClient(cred, "", client_profile)

        # 5. 构造请求参数
        req = models.DescribeCaptchaResultRequest()
        params = {
            "CaptchaType": 9,
            "Ticket": ticket,
            "UserIp": "127.0.0.1", # 本地测试用 127.0.0.1 即可
            "Randstr": randstr,
            "CaptchaAppId": APP_ID,
            "AppSecretKey": APP_SECRET_KEY
        }
        req.from_json_string(json.dumps(params))

        # 6. 发起请求并解析结果
        resp = client.DescribeCaptchaResult(req)
        
        # 解析返回的 JSON
        result = json.loads(resp.to_json_string())
        print(f"\n【腾讯云 SDK 返回】: {result}")

        # CaptchaCode 为 1 时表示验证成功
        if result.get("CaptchaCode") != 1:
            raise ApiError(
                status_code=400,
                code="CAPTCHA_FAILED",
                message=f"验证码校验失败: {result.get('CaptchaMsg', '未知错误')}"
            )
        return True

    except Exception as e:
        print(f"【SDK调用异常】: {e}")
        raise ApiError(500, "CAPTCHA_SERVICE_ERROR", f"验证码服务请求异常: {str(e)}")