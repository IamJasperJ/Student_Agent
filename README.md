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
- 支持启动 background 子 agent 执行独立任务，并通过任务 id 查询结果
- 支持 agent team：创建角色化子 agent、分配任务、查询/审核结果、停止子 agent 生命周期

首次获取课表时会生成 `network_block/Auth/ustb_qrcode.png`，需要用微信扫码确认。认证后的 Cookie 会缓存到 `network_block/Auth/cookie.json`。这两个文件都已加入 `.gitignore`。

## Background 子 Agent

主 agent 可以调用三个后台任务工具：

- `start_background_task`：启动后台子 agent，并立刻返回 `task_id`
- `get_background_task`：根据 `task_id` 查询状态、结果或错误
- `list_background_tasks`：列出当前进程内的后台任务

后台任务在独立线程里运行，使用独立上下文，不会阻塞主输入循环。当前任务状态只保存在当前进程内，重启程序后会清空。

## Agent Team

主 agent 可以通过 team 工具管理多个角色化子 agent：

- `create_team_agent`：创建子 agent，指定 `name`、`role` 和可选 `system_prompt`
- `list_team_agents`：查看所有子 agent 及生命周期状态
- `assign_team_task`：把任务派给指定子 agent，并在后台执行
- `list_team_tasks`：查看所有 team 任务、负责人、执行状态和审核状态
- `get_team_task`：查看单个任务的结果、错误、审核信息
- `review_team_task`：对已完成任务执行 `approved` 或 `rejected` 审核
- `cancel_team_task`：请求取消未完成任务
- `stop_team_agent`：停止子 agent，让它不再接受新任务

team 任务同样在当前进程的后台线程里运行。停止子 agent 会阻止新任务进入；已运行中的模型调用会自然结束，不会被强制中断。

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
- [ ] 添加background、agent team功能
  - [x] 添加background子agent执行任务功能
  - [x] 添加agent team 功能实现子agent创建，任务管理、审核，子进程生命周期管理
