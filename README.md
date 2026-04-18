### Agent for USTB students

## 快速开始

本项目推荐使用Python 3.10+

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
- 支持编辑文件：通过搜索-替换模式精确修改文件内容
- 支持通过 USTB 认证流程获取并缓存课表
- 支持启动 background 子 agent 执行独立任务，并通过任务 id 查询结果
- 支持 agent team：创建角色化子 agent、分配任务、查询/审核结果、停止子 agent 生命周期
- 支持 git worktree 隔离：为编程任务创建独立工作树，并可绑定给 team 子 agent
- 集成 MCP SDK (Model Context Protocol) 支持

首次获取课表时会生成 `network_block/Auth/ustb_qrcode.png`，需要用微信扫码确认。认证后的 Cookie 会缓存到 `network_block/Auth/cookie.json`。这两个文件都已加入 `.gitignore`。

## Background 子 Agent

主 agent 可以调用三个后台任务工具：

- `start_background_task`：启动后台子 agent，并立刻返回 `task_id`
- `get_background_task`：根据 `task_id` 查询状态、结果或错误
- `list_background_tasks`：列出当前进程内的后台任务

后台任务在独立线程里运行，使用独立上下文，不会阻塞主输入循环。当前任务状态只保存在当前进程内，重启程序后会清空。

## 能力边界

主循环 agent 使用 `main` 工具作用域，拥有基础执行工具和管理工具。只有主循环 agent 可以：

- 创建、查询、停止 background 任务
- 创建子 agent、分配/审核 team 任务、停止子 agent
- 创建、查询、删除 worktree，并把 worktree 绑定给子 agent

background 子 agent 和 team 子 agent 使用 `subagent` 工具作用域，只能使用基础执行工具，例如读取文件、执行受限检查命令、获取课表、压缩上下文。子 agent 不能再创建子 agent，也不能管理 worktree 或 team 生命周期。

## 文件编辑功能

agent 现在支持通过 `edit_file_block` 工具编辑文件。该工具使用搜索-替换模式，要求提供精确的原始文本（包括缩进）进行替换。主要特点：

- **精确匹配**：必须提供文件中完全相同的文本块
- **唯一性检查**：如果找到多个匹配项会报错，确保修改位置准确
- **安全路径**：所有文件操作都经过安全路径检查
- **编码支持**：使用 UTF-8 编码读写文件

使用示例：
```python
edit_file_block(
    path="README.md",
    old_str="## 功能\n\n- 通过兼容 OpenAI 的 Chat Completions API 运行命令行 agent",
    new_str="## 功能\n\n- 通过兼容 OpenAI 的 Chat Completions API 运行命令行 agent\n- 支持编辑文件功能"
)
```

## MCP SDK 集成

项目已集成 MCP SDK (Model Context Protocol)，支持：
- 标准化的模型上下文协议
- 增强的模型交互能力
- 更好的工具调用和管理
- 扩展的上下文处理

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

## Worktree 隔离

主 agent 可以通过 worktree 工具为编程任务创建隔离工作树：

- `create_worktree`：在 `.agent_worktrees/` 下创建 git worktree，默认新建 `agent/<name>-<id>` 分支
- `list_worktrees`：列出当前仓库 worktree，并标记哪些由 agent 管理
- `get_worktree`：查询指定受管 worktree 详情
- `remove_worktree`：删除 `.agent_worktrees/` 下的受管 worktree

`create_team_agent` 和 `assign_team_task` 都支持传入 `worktree_id`。绑定后，子 agent 的 `read_file`、`bash` 等工具会在对应 worktree 目录中执行，适合并行开发和隔离实验。`.agent_worktrees/` 已加入 `.gitignore`。

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
- [x] 文件编辑功能
  - [x] 添加edit_file_block工具
  - [x] 集成到主agent工具集
- [ ] MCP SDK集成
  - [x] 添加mcpsdk依赖
  - [ ] 环境配置支持
- [ ] 定时提醒，如上课前30分钟，前一天晚
  - [ ] 调用发送信息工具，工具具体实现暂时不写
    - [ ] 工具发送消息与小程序对接，实际编写
- [x] 添加background、agent team功能
  - [x] 添加background子agent执行任务功能
  - [x] 添加agent team 功能实现子agent创建，任务管理、审核，子进程生命周期管理
- [x] 为了辅助编程，增加工作树worktree隔离与管理
- [ ] 添加消息机制，让同一个组的子agent可以相互交流
