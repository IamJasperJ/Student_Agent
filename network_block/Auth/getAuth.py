import requests
import re
import time
import json
from pathlib import Path
from html import unescape
from urllib.parse import unquote, urlparse, parse_qs

REQUEST_TIMEOUT = (5, 30)
POLL_TIMEOUT = 20
POLL_MAX_WAIT_SECONDS = 180


class USTBAuth:
    def __init__(self):
        self.session = requests.Session()
        # 基础 Headers 模拟
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://sso.ustb.edu.cn/'
        })

    def get_lck_from_entry(self, client_id):
        """
        可选：从认证入口获取 lck。
        """
        # 模拟访问入口
        entry_url = "https://sso.ustb.edu.cn/idp/authCenter/authenticate"
        params = {
            'client_id': client_id,
            'redirect_uri': 'https://byyt.ustb.edu.cn/oauth/login/code', 
            'response_type': 'code',
            'state': 'ustb',
            'login_return': 'true'
        }
        
        try:
            response = self.session.get(
                entry_url,
                params=params,
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            pattern = r'lck=([^&]+)'
            match = re.search(pattern, response.headers.get('Location', ''))
            if not match:
                raise RuntimeError("认证入口未返回 lck")
            return match.group(1)
        except Exception as e:
            raise RuntimeError(f"获取 lck 失败: {Path(__file__)}") from e



    def get_wechat_qr_data(self, entity_id, lck):
        """
        步骤 1: 获取微信二维码凭据 (appId, returnUrl, randomToken)
        对应文档: POST https://sso.ustb.edu.cn/idp/authn/getMicroQr
        """
        url = "https://sso.ustb.edu.cn/idp/authn/getMicroQr"
        payload = {
            "entityId": entity_id,
            "lck": lck
        }
        
        headers = {'Content-Type': 'application/json'}
        response = self.session.post(
            url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('code') == '200':
            return data['data']
        else:
            raise Exception(f"获取凭据失败: {data.get('message')}")

    def get_sid_from_qrpage(self, appid, return_url, rand_token):
        """
        步骤 2: 获取会话 ID (sid)
        对应文档: GET https://sis.ustb.edu.cn/connect/qrpage
        关键点：文档指出 sid 需要使用正则 `sid\s?=\s?(\w{32})` 从 HTML 中提取。
        """
        url = "https://sis.ustb.edu.cn/connect/qrpage"
        params = {
            "appid": appid,
            "return_url": return_url,
            "rand_token": rand_token,
            "embed_flag": "1"
        }
        
        response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        # 文档明确说明：使用正则提取 sid
        match = re.search(r'sid\s?=\s?(\w{32})', response.text)
        if match:
            return match.group(1)
        else:
            raise Exception("无法从页面提取 sid，请检查参数或网络连接")

    def get_qrcode_image(self, sid):
        """
        步骤 3: 下载二维码图片
        对应文档: GET https://sis.ustb.edu.cn/connect/qrimg
        """
        url = "https://sis.ustb.edu.cn/connect/qrimg"
        params = {'sid': sid}
        
        response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            path = Path(__file__).resolve().parent / 'ustb_qrcode.png'
            with open(path, 'wb') as f:
                f.write(response.content)
            # print("✅ 二维码已保存为 'ustb_qrcode.png'，请使用微信扫描")
        else:
            raise Exception("下载二维码失败")

    def wait_for_scan_and_confirm(self, sid):
        """
        步骤 4: 轮询状态，等待扫码和确认
        """
        url = "https://sis.ustb.edu.cn/connect/state"
        params = {'sid': sid}
        
        print("⏳ 正在轮询扫码状态，请在手机上确认...")
        
        deadline = time.monotonic() + POLL_MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            response = self.session.get(url, params=params, timeout=POLL_TIMEOUT) # 文档提到请求可能挂起约15秒
            response.raise_for_status()
            data = response.json()
            
            code = data.get('code')
            # 文档说明: code 1 表示成功，data 中包含通行码
            if code == 1:
                auth_code = data.get('data') # 通行码
                print("✅ 扫码确认成功！获取通行码")
                return auth_code
            elif code == 2:
                print("⏳ 已扫码，等待确认... (请在手机上点击确认)")
                time.sleep(2)
            elif code in [3, 202]:
                raise Exception("二维码已失效")
            elif code == 4:
                raise Exception("请求超时")
            else:
                print(f"状态异常: {data.get('message')}")
                time.sleep(5)
        raise TimeoutError("扫码确认超时")

    def final_authentication(self, auth_code, qr_data):
        base_return_url = qr_data.get('returnUrl')
        if not base_return_url:
            raise ValueError("认证返回数据缺少 returnUrl")
        
        # 移除 base_return_url 结尾可能存在的问号
        base_return_url = base_return_url.split('?')[0]

        params = {
            "appid": qr_data['appId'],
            "auth_code": auth_code,
            "rand_token": qr_data['randomToken'],
            "thirdPartyAuthCode": "microQr" # 告诉服务器这是微门户扫码
        }

        # 重新解析 returnUrl 中的原始参数（如 client_id, state）
        parsed_origin = urlparse(qr_data.get('returnUrl'))
        origin_params = parse_qs(parsed_origin.query)
        for k, v in origin_params.items():
            params[k] = v[0]

        # 重点：Referer 必须是 sis.ustb.edu.cn (二维码页面)
        headers = self.session.headers.copy()
        headers['Referer'] = "https://sis.ustb.edu.cn/"

        # 执行请求
        response = self.session.get(
            base_return_url, 
            params=params, 
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    
        text = response.text

        # 4. 解析 HTML 跳转目标
        # 加上更宽松的正则，防止空格影响
        loc_pattern = r'var\s+locationValue\s*=\s*"([^"]+)"'
        location_value_match = re.search(loc_pattern, text)

        if location_value_match:
            location_value = unescape(unquote(location_value_match.group(1)))
            
            # --- 关键修改点 2: 补全协议和域名 ---
            # 有时候返回的是相对路径，需要拼凑成完整 URL
            if location_value.startswith('/'):
                parsed_base = urlparse(base_return_url)
                location_value = f"{parsed_base.scheme}://{parsed_base.netloc}{location_value}"

            print(f"🚀 发现最终跳转地址: {location_value[:60]}...")
        
            # 5. 执行最后一次跳转，获取业务 Cookie
            # 这步完成后，session.cookies 应该会出现 'JSESSIONID' 或应用特有的 Cookie
            final_resp = self.session.get(
                location_value,
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            )
            final_resp.raise_for_status()
            
            # 打印调试信息：看看最后停在哪个 URL 了
            print(f"🏁 最终停留在: {final_resp.url}")
            
            return self.session.cookies.get_dict()
        else:
            # 打印返回的内容前 200 字，看看报错是什么
            print("❌ 未发现跳转脚本，服务器返回内容片段：")
            print(text[:300]) 
            return self.session.cookies.get_dict()
    def login_and_get_cookie(self, entity_id="YW2025006"):
        try:
            # 1. 获取 lck
            lck = self.get_lck_from_entry(entity_id)
            # 2. 获取微信凭据 (包含 appId, returnUrl, randomToken)
            qr_data = self.get_wechat_qr_data(entity_id, lck)
            # 3. 提取 sid
            sid = self.get_sid_from_qrpage(qr_data['appId'], qr_data['returnUrl'], qr_data['randomToken'])
            # 4. 下载二维码
            self.get_qrcode_image(sid)
            # 5. 轮询扫码结果，获取 auth_code
            auth_code = self.wait_for_scan_and_confirm(sid)
            # 6. 完成认证并拿 Cookie
            # 传递 qr_data 即可，里面已经有最终跳转所需的所有信息
            cookies = self.final_authentication(auth_code, qr_data)
            return cookies
        except Exception as e:
            print(f"❌ 流程出错: {e}")
            return None


def getAuth():
    auth = USTBAuth()
    return auth.login_and_get_cookie(entity_id="YW2025006")


if __name__ == "__main__":
    auth = USTBAuth()
    # entity_id 可以是 NS2022062 (教务) 或 YW2025007 (AI助手) 等 byyt YW2025006
    cookies = auth.login_and_get_cookie(entity_id="YW2025006")
    assert cookies, "没获取到cookies"
    print("\n--- 最终 Cookie ---")
    print(cookies)
