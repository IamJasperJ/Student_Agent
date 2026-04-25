import requests
from ..Auth import read_cookie
from pathlib import Path
import re
import json
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv(override=True)

REQUEST_TIMEOUT = (5, 30)

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


def _current_academic_year_term(today=None):
    today = today or date.today()
    if today.month >= 9:
        return f"{today.year}-{today.year + 1}", "1"
    if today.month <= 1:
        return f"{today.year - 1}-{today.year}", "1"
    return f"{today.year - 1}-{today.year}", "2"


def _schedule_payload():
    default_year, default_term = _current_academic_year_term()
    return {
        'xn': os.getenv('SCHEDULE_YEAR', default_year),
        'xq': os.getenv('SCHEDULE_TERM', default_term),
    }


def getSchedule(update_force: bool = False):
    # 检查缓存
    if (update_force == False):
        path = Path(__file__).parent / "Schedule" / "user_1_Sche.json"
        if path.is_file():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        
    try:
        cookies = read_cookie()
        # 发送 POST 请求
        response = requests.post(
            url,
            headers=headers,
            cookies=cookies,
            data=_schedule_payload(),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        info = response.json()
        if not isinstance(info, list):
            return {"ok": False, "error": "课表接口返回格式不是列表", "raw": info}
        parse_sche = []
        def get_week_day(key):
            # 匹配 xq 后面的数字
            match = re.search(r"xq(\d+)", key)
            if match:
                num = match.group(1)
                week_dict = {
                    "1": "星期一", "2": "星期二", "3": "星期三", 
                    "4": "星期四", "5": "星期五", "6": "星期六", "7": "星期日"
                }
                return week_dict.get(num, "未知星期")
            return None
        for dic in info:
            raw_course = dic.get("SKSJ") if isinstance(dic, dict) else None
            if raw_course:
                parse_sche.append(parse_course_info(raw_course))
            if dic.get("KEY"):
                parse_sche[-1]["星期"] = get_week_day(dic["KEY"])
        writeSchedule(parse_sche)
        return parse_sche
    except requests.exceptions.HTTPError as err:
        return {"ok": False, "error": f"HTTP 错误: {err}"}
    except requests.exceptions.RequestException as err:
        return {"ok": False, "error": f"网络请求错误: {err}"}
    except Exception as e:
        return {"ok": False, "error": f"发生错误: {e}"}



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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(parse_sche, ensure_ascii=False, indent=4))


if __name__ == "__main__":
    getSchedule(True)
