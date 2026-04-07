import requests
from ..Auth import read_cookie

# 单模块正确，cookies只用session也可以工作，使用三个一起也可以工作

# 目标 URL
url = "https://byyt.ustb.edu.cn/xszykb/queryxszykbzong"
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

# # 设置表单数据 (Payload)
data = {
    # 学年
    'xn': '2025-2026',
    # 学期
    'xq': '2',
}
def getSchedule():
    try:
        cookies = read_cookie()
        # 发送 POST 请求
        response = requests.post(url, headers=headers, cookies=cookies, data=data)
        response.raise_for_status()
        info = response.json()
        classInfo = []
        for dic in info:
            classInfo.append(dic["SKSJ"])
            print(classInfo[-1])
        return classInfo
    except requests.exceptions.HTTPError as err:
        print(f"HTTP 错误: {err}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    getSchedule()