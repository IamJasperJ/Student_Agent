import requests
from ..Auth import read_cookie
from pathlib import Path
import re
import json

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
def getSchedule(update_force: bool = False):
    # 检查缓存
    if (update_force == False):
        path = Path(__file__).parent / "Schedule" / "user_1_Sche.json"
        if path.is_file():
            parse_sche = {}
            with open(path, 'r') as f:
                parse_sche = json.loads(f.read())
            return parse_sche
        
    try:
        cookies = read_cookie()
        # 发送 POST 请求
        response = requests.post(url, headers=headers, cookies=cookies, data=data)
        response.raise_for_status()
        info = response.json()
        parse_sche = []
        for dic in info:
            parse_sche.append(parse_course_info(dic["SKSJ"]))
        writeSchedule(parse_sche)
        return parse_sche
    except requests.exceptions.HTTPError as err:
        print(f"HTTP 错误: {err}")
    except Exception as e:
        print(f"发生错误: {e}")



def parse_course_info(raw_text):
    """
    解析排课信息字符串
    """
    # 1. 先按换行符切割并去除每行首尾空格
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # 初始化结果字典
    result = {
        "course_name": "未知课程",
        "teacher": "未知教师",
        "weeks": "未知周数",
        "location": "未知地点",
        "period": "未知节次",
        "remark": ""
    }

    # 2. 提取备注 (如果有 "备注:" 字样)
    if "备注:" in raw_text:
        remark_match = re.search(r"备注:(.*)", raw_text)
        if remark_match:
            result["remark"] = remark_match.group(1).strip()
            # 移除包含备注的部分，避免干扰后续解析
            raw_text = raw_text.split("备注:")[0]

    # 3. 使用正则提取关键信息（针对非换行情况的补救）
    # 提取周数 (如 9-16周 或 1-4,6,8周)
    week_match = re.search(r"(\d+[\d, \-]*周)", raw_text)
    if week_match:
        result["weeks"] = week_match.group(1)

    # 提取节次 (如 第3-4节 或 第11-12节)
    period_match = re.search(r"(第\d+-\d+节)", raw_text)
    if period_match:
        result["period"] = period_match.group(1)

    # 提取地点 (如 【校本部】...)
    location_match = re.search(r"(【.*?】[^ \n]*)", raw_text)
    if location_match:
        result["location"] = location_match.group(1)

    # 4. 根据处理后的行逻辑提取课程名和教师
    # 通常第一行是课程名，第二行是老师
    if len(lines) >= 1:
        # 如果第一行包含了节次，说明课程名可能和节次连在一起了
        # 例如 "第9-10节软件工程"
        first_line = lines[0]
        if "第" in first_line and "节" in first_line:
            result["course_name"] = re.sub(r"第\d+-\d+节", "", first_line)
        else:
            result["course_name"] = first_line

    if len(lines) >= 2:
        # 第二行通常是老师，但要排除掉那些已经是周数或地点的情况
        if "周" not in lines[1] and "【" not in lines[1]:
            result["teacher"] = lines[1]

    return result

def writeSchedule(parse_sche):
    path = Path(__file__).parent / "Schedule" / "user_1_Sche.json"
    with open(path, 'w') as f:
        f.write(json.dumps(parse_sche, ensure_ascii=False, indent=4))


if __name__ == "__main__":
    getSchedule()