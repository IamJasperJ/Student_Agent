### Agent for USTB students

## 快速开始

本项目建议使用 Python 3.9+。

```bash
python3 -m venv .agent_env
source .agent_env/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中填写：

- `MODEL_BASE_URL`：兼容 OpenAI API 的模型服务地址
- `MODEL_ID`：模型名
- `API_KEY`：模型服务密钥
- `SCHEDULE_YEAR`：可选，学年，例如 `2025-2026`
- `SCHEDULE_TERM`：可选，学期，例如 `2`

启动：

```bash
.agent_env/bin/python my_agent.py
```

输入 `q`、`exit` 或空行退出。

## 功能

- 通过兼容 OpenAI 的 Chat Completions API 运行命令行 agent
- 支持读取工作区文件、执行受限检查命令、压缩上下文
- 支持通过 USTB 认证流程获取并缓存课表

首次获取课表时会生成 `network_block/Auth/ustb_qrcode.png`，需要用微信扫码确认。认证后的 Cookie 会缓存到 `network_block/Auth/cookie.json`。这两个文件都已加入 `.gitignore`。

## 安全说明

`bash` 工具已经限制为偏只读/检查类命令，例如 `ls`、`cat`、`rg`、`git status`、`git diff`、`python -m py_compile`、`python -m pytest`。如果后续要开放写文件或安装依赖，建议单独实现明确的工具，而不是放宽 shell。

## 欢迎一起参与本项目，接受PR
如果对本项目有任何建议，欢迎参与。

欢迎**技术大佬**们共同开发

## 进度
- [x] agent loop
- [x] 获取并组织课表
  - [x] 先不验证，直接获取课表
  - [x] 组织课表，使用jsonl保存
  - [x] 登入获取Cookies
  - [x] 从byyt.usrb.edu.cn获取课表
- [ ] agent响应展示(重定向到课表页面)
    - [ ] 课表页面编写    
- [x] 上下文压缩功能
- [ ] 定时提醒，如上课前30分钟，前一天晚
  - [ ] 调用发送信息工具，工具具体实现暂时不写
    - [ ] 工具发送消息与小程序对接，实际编写
