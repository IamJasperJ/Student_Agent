import requests
import json
from pathlib import Path
from .getAuth import getAuth

# 设置请求头 (Headers)
headers = {
    # 'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'https://byyt.ustb.edu.cn',
    # 来源网站
    'Referer': 'https://byyt.ustb.edu.cn/authentication/main',
    # 'Sec-Fetch-Dest': 'empty',
    # 'Sec-Fetch-Mode': 'cors',
    # 'Sec-Fetch-Site': 'same-origin',
    # 浏览器数据
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    # 说明是ajax请求，返回json而不是整个文件
    'X-Requested-With': 'XMLHttpRequest',
    # 'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    # 'sec-ch-ua-mobile': '?0',
    # 'sec-ch-ua-platform': '"macOS"',
}

def write_cookie(cookie, path):
    with open(path, 'w') as f:
        f.write(json.dumps(cookie))

def read_cookie():
    path = Path(__file__).resolve().parent / 'cookie.json'
    data = {}
    
    # 1. 尝试读取缓存
    if path.exists():
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print("Cookie 文件格式损坏")

    # 2. 验证有效性
    if data:
        check_url = "https://byyt.ustb.edu.cn/authentication/main"
        try:
            response = requests.get(
                check_url, 
                headers=headers,
                cookies=data, 
                allow_redirects=False,
                timeout=5
            )
            if response.status_code == 200:
                print("✅ Cookie 验证成功，继续使用缓存")
                return data
            else:
                print(f"⚠️ Cookie 已失效 (Status: {response.status_code})，准备重新认证")
        except requests.RequestException as e:
            print(f"网络连接异常: {e}")

    # 3. 重新认证
    print("🚀 正在发起扫码认证...")
    try:
        cookie = getAuth()
        if cookie:
            write_cookie(cookie=cookie, path=path)
            return cookie
    except Exception as e:
        print(f"❌ 认证流程发生错误: {e}")
        # 抛出异常而不是静默失败，方便上层捕获
        raise 

    assert cookie, "身份认证失败：未能获取到有效的 Cookie"
    return cookie

if __name__ == "__main__":
    read_cookie()