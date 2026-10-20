# 工位健康管家（deskpal）

桌面常驻的 AI 办公健康助手：监听键鼠活跃度，结合真实工作时长与健康数据，动态提醒休息、鉴别身体不适原因、生成健康报告。

## 特性

- **状态驱动的休息提醒**：不按固定闹钟，而是综合「真实工作时长 + 离开时长 + 实际休息时长」由 LLM 动态决定下一轮工作时长，异常时降级为默认建议
- **RAG 症状鉴别**：口语描述不适 → 语义检索健康知识库 → 追问/自测区分原因 → 分级建议（高危词表前置拦截 + 阈值过滤 + 分级就医三道防线）
- **健康报告 skill**：汇总本周数据 + 长期记忆 → 动态定位关注部位 → 信息不足则追问 → 生成含自测与建议的报告
- **记忆系统**：长期记忆（LLM 提取 + 部位归一化去重）+ 短期记忆（滑动窗口 + 滚动概况压缩）
- **可靠的工具调用**：副作用真实落地、参数防御性校验、LLM 输出多层解析兜底

## 系统架构

5 层架构，依赖方向唯一：只有协调层依赖其它层，其它层之间零互依赖。

```
                        main.py（装配 + 启动入口）
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────┐
│                    协调层  core/                            │
│   RuntimeManager     AppState      collect_daily_checkin   │
│   （监控线程主循环）   （共享状态+锁）  （每日签到）            │
└──────┬──────────────┬───────────────┬──────────────┬───────┘
       ▼              ▼               ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 采集层       │ │ 判断层       │ │ 呈现层       │ │ 存储层       │
│ monitor/    │ │ agent/ + rag/│ │ ui/         │ │ storage/    │
│ pynput 键鼠 │ │ 三条 LLM 链路 │ │ tkinter 弹窗│ │ SQLite 4表  │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

三条 LangGraph 链路：

- **监控**：`build_context → call_llm → parse_decision`（线性单轮）
- **对话**：`chatbot ⇄ tools`（图内工具循环，多轮）
- **报告**：`collect → analyze →(条件边) ask/recommend`（多轮由外层会话驱动）

线程模型（3 线程 + 三同步原语）：主线程 UI（mainloop）+ 监控线程（daemon）+ pynput 线程；`Queue` 传任务、`Event` 传信号、`Lock` 护状态。

## 快速开始

### 前置要求

- Windows（依赖 `tkinter` 与 `pynput`）
- Python 3.10+（开发环境实测 3.12）
- 一个 LLM 服务的 API Key（默认 DeepSeek：https://platform.deepseek.com）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> 首次安装会拉取 `torch` / `transformers`（`sentence-transformers` 的传递依赖），体积较大。

### 2. 配置

复制模板并填入密钥：

```bash
copy .env.example .env    # Windows cmd
# 或 Git Bash / Linux：cp .env.example .env
```

编辑 `.env`，将 `LLM_API_KEY` 换成你的真实 key。

### 3. 运行

```bash
python main.py
```

## 配置说明

| 环境变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_API_KEY` | 是 | - | API Key（对应 `LLM_PROVIDER` 的提供商） |
| `LLM_PROVIDER` | 否 | `deepseek` | 模型提供商：`deepseek` / `openai` / `google_genai` 等 |
| `LLM_MODEL_FLASH` | 否 | `deepseek-v4-flash` | 日常模型（模型名为 provider 专属） |
| `LLM_MODEL_PRO` | 否 | `deepseek-v4-pro` | 高精度模型 |
| `LLM_BASE_URL` | 否 | 空 | OpenAI 兼容端点地址（豆包/火山引擎等需填） |
| `DB_PATH` | 否 | `deskpal.db` | SQLite 数据库路径 |
| `LOG_FILE` | 否 | `deskpal.log` | 日志文件路径 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |

## 更换模型（统一接口）

内置基于 LangChain `init_chat_model` 的统一接口：改 `LLM_PROVIDER` + `LLM_MODEL_*` + `LLM_API_KEY` 即可切换提供商。

**依赖安装**：默认 DeepSeek 已包含在 `requirements.txt` 中，无需额外操作；使用其他提供商时，改好 `.env` 后执行 `python setup_llm.py`，脚本会读 `LLM_PROVIDER` 并**只安装对应的那一个包**（已安装则跳过），或手动 `pip install langchain-openai` 等对应包。

| 模型 | `LLM_PROVIDER` | 需要安装 |
|---|---|---|
| DeepSeek | `deepseek` | `langchain-deepseek` |
| OpenAI GPT | `openai` | `langchain-openai` |
| Google Gemini | `google_genai` | `langchain-google-genai` |
| Anthropic Claude | `anthropic` | `langchain-anthropic` |
| 豆包（火山引擎） | `openai` | `langchain-openai` |

> ⚠️ **两个注意事项**
>
> 1. **豆包等 OpenAI 兼容模型没有原生 provider**：需设 `LLM_PROVIDER=openai`，同时 `LLM_BASE_URL` 指向火山引擎的 OpenAI 兼容端点（如 `https://ark.cn-beijing.volces.com/api/v3`），且 `LLM_MODEL_*` 填「推理接入点 ID」而非模型名。
> 2. **所选模型必须支持 function calling（工具调用）**：本项目的对话/报告链路强依赖工具调用，换成不支持工具调用的模型会导致工具静默失效、对话异常。

## 技术栈

- **语言**：Python 3.12
- **LLM**：DeepSeek（默认 `deepseek-v4-flash` / `deepseek-v4-pro`），可切换 openai / google_genai / anthropic（统一接口）
- **Agent 框架**：LangChain + LangGraph（`StateGraph` / `ToolNode` / `tools_condition` / `add_messages`）
- **存储**：SQLite（WAL / 短连接）
- **外设监听**：pynput
- **并发**：threading（Queue / Event / Lock）
- **UI**：tkinter
- **Embedding**：本地 `bge-small-zh-v1.5`（sentence-transformers）

## 项目结构

```
deskpal/
├── config.py              # 配置中心（.env 读取 + 默认值）
├── core/                  # 协调层：编排、调度、线程管理
│   ├── runtime.py         # 监控线程主循环
│   ├── state.py           # AppState 共享状态（RLock 保护）
│   └── checkin.py         # 每日心情/睡眠签到
├── monitor/               # 采集层：键鼠监听
│   └── peripheral.py
├── agent/                 # 判断层：LLM 链路
│   ├── monitor_graph.py   # 定时判断链
│   ├── chat_graph.py      # 对话链（工具循环）
│   ├── report_graph.py    # 健康报告 skill
│   ├── tools.py           # 3 个工具
│   ├── memory.py          # 记忆系统（长期提取 + 短期窗口）
│   └── llm.py             # LLM 工厂
├── rag/                   # RAG 内核
│   ├── knowledge_base.json
│   ├── loader.py          # 检索坐标 / 载荷
│   ├── retriever.py       # 语义检索（余弦相似度）
│   └── safety.py          # 高危词表
├── storage/               # 存储层：SQLite（4 张表）
├── ui/                    # 呈现层：tkinter 弹窗
├── demo/                  # 各能力的演示脚本
└── tests/                 # 单元测试
```

## 运行测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## 免责声明

本工具提供的所有健康内容**仅供日常放松与保健参考，不构成医疗诊断或治疗建议**。如症状持续、加重，或出现胸闷、胸痛、单侧无力等高危信号，请立即就医。

## License

[MIT License](LICENSE)
