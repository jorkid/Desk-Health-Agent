# 工位健康管家（deskpal）项目归档

> 本文档是项目设计过程与决策链的完整交接记录。任何新的 AI 模型/会话读完本文档后，应能了解项目全貌、已做决策及其理由，并沿当前思路继续推进。
> 维护约定：用户发送 **"归档"** 时，将本文档更新至最新对话状态。

---

## 1. 项目概述

**产品**：工位健康管家（deskpal）—— 桌面常驻的 AI 办公健康助手。

**核心能力**：
- 监听键鼠活跃度，判断疲劳/久坐/手腕劳损，弹窗提醒休息；
- 定时链路调用 LLM，结合真实工作时长 + 中途离开时长 + 实际休息时长，动态决定下一轮工作时长；
- 对话链路支持用户主动提问（查数据、改工作时长、问症状）；
- **RAG 症状鉴别**：用户说"眼睛/腰不舒服"时，检索知识库 + 追问 + 自测区分原因，给放松建议；
- **生成健康报告 skill**：收集本周数据 + 长期记忆 → 动态找部位 → 信息不够则追问/自测 → 给建议；
- **记忆系统**：长期记忆（LLM 提取 + 按部位去重）+ 短期记忆（滑动窗口 + 滚动概况）。

**价值主张（产品差异化）**：状态驱动（state-driven）而非时间驱动——不只按闹钟提醒，而是结合真实工作时长、离开时长、健康自评来动态判断。

---

## 2. 技术栈

- **语言**：Python 3
- **LLM**：统一接口 `init_chat_model`（`LLM_PROVIDER` 可配 deepseek / openai / google_genai / anthropic），默认 DeepSeek（`deepseek-v4-flash` / `deepseek-v4-pro`）；key 统一用 `LLM_API_KEY`，只放 `.env`（已 gitignore），**绝不硬编码进源码**
- **Agent 框架**：LangChain（`init_chat_model` 工厂）+ LangGraph（`StateGraph` / `ToolNode` / `tools_condition` / `add_messages`）
- **存储**：SQLite（WAL / 短连接 / busy_timeout / 写锁），4 张表
- **外设监听**：pynput（keyboard + mouse）
- **并发**：threading（主线程 mainloop + 监控线程 daemon + pynput 线程）
- **UI**：tkinter + 弹窗轮询（queue + after + threading.Event 跨线程）
- **Embedding**：本地 `bge-small-zh-v1.5`（sentence-transformers，CPU 推理，512 维）

---

## 3. 分层架构

5 层，依赖方向唯一：**只有协调层依赖其它层，其它层之间零互依赖**（按 import 判定，不是按数据流）。

| 层 | 目录 | 职责 |
|---|---|---|
| 采集层 | `deskpal/monitor/` | 键鼠监听、活跃度指标累计 |
| 判断层 | `deskpal/agent/` | LLM 链路（监控判断 / 对话 / RAG / 报告 / 记忆） |
| 呈现层 | `deskpal/ui/` | 弹窗、交互 |
| 存储层 | `deskpal/storage/` | SQLite 读写 |
| 协调层 | `deskpal/core/` | 编排、调度、装配、线程管理 |

**关键模块**：
- `core/runtime.py`：`RuntimeManager` —— 监控线程主循环、空闲处理、单次判断、休息倒计时、持久化
- `core/state.py`：`AppState` —— 工作时长等共享状态（RLock 保护）
- `core/checkin.py`：每日心情/睡眠收集（每天一次去重）
- `monitor/peripheral.py`：`PeripheralMonitor` —— `get_stats` / `mark_activity` / `reset`
- `ui/popup.py`：弹窗（选择弹窗 + 休息倒计时弹窗，跨线程用 queue+after 轮询）
- `agent/monitor_graph.py`：定时判断链（build_context → call_llm → parse_decision）
- `agent/chat_graph.py`：对话链（chatbot ⇄ tools 循环）
- `agent/report_graph.py`：**报告 skill 子图**（collect → analyze → 追问/给建议）
- `agent/memory.py`：**记忆系统**（长期提取 `extract_health_facts` + 短期窗口 `compress_window`/`summarize_conversation`）
- `agent/tools.py`：3 个工具（查周报 / 改工作时长 / 健康知识检索）
- `agent/schemas.py`：`MonitorState` / `ChatState`
- `rag/`：健康知识库 + 检索内核（loader / retriever / safety）
- `storage/schema.py` + `storage/models.py`：4 张表（daily_health / work_break_records / settings / **health_memory**）

**线程模型与三同步原语**：Queue 传任务 / Event 传信号 / Lock 护状态。锁的安全取决于临界区时长（本项目三把锁临界区都是微秒~毫秒级），不取决于锁的数量。

---

## 4. 已完成的功能与优化

1. **空闲判断实时化**：每 0.5s 分片醒来实时检测 idle；离开工位则暂停计时（`started += away` 扣掉离开时长）并累计 `away_total`。
2. **休息流程重构（三段式）**：① 到点弹窗「确认休息 | 继续工作 N 分钟」；② 确认休息 → 倒计时弹窗（默认 10 分钟，可「我已休息结束」提前结束）；③ 倒计时归零「延续休息 | 休息完毕」，休息完毕才调 LLM，传入 `actual_work_seconds`（真实工作时长）+ `away_seconds`（离开时长）+ `rest_seconds`（实际休息时长），模型**只输出下一轮工作时长**（不再输出休息时长，休息时长由用户自主倒计时决定）。
3. **降级与容错**：LLM 异常降级为默认建议，监控线程永不因 LLM 崩溃。
4. **RAG 症状鉴别**：检索 → 追问 → 自测 → 建议，三道防线（高危词表 / 阈值 / 分级就医），见 §5。
5. **生成健康报告 skill**：数据+记忆 → 动态找部位 → 信息不够追问/自测 → 给建议，见 §6。
6. **记忆系统**：长期记忆（提取归一化 + 去重）+ 短期记忆（滑动窗口 + 滚动概况），见 §7。
7. **测试**：22 个单元测试（`unittest discover`），覆盖工具副作用、解析兜底、存储、checkin、窗口治理。

---

## 5. RAG 功能设计

### 5.1 需求：两种交互模式

| 模式 | 触发 | 行为 |
|---|---|---|
| ① 主动提问（症状鉴别） | 用户在交互窗口说"眼睛/腰不舒服" | 追问缩小范围 → 定位可能原因 → 给放松/预防建议 |
| ② 主动关心 | 久坐后 / 睡眠差后 / 工作一段时间后 | 弹窗问"某部位有不适吗"，有则转入模式①深聊 |

两者共享同一个 **RAG 内核**（健康知识库），模式②只是模式①的"引流入口"。（模式②尚未接入，见 §9）

### 5.2 关键设计决策（含理由）

| 决策点 | 决策 | 理由 |
|---|---|---|
| 安全边界 | 只做放松/缓解，**不做诊断治疗**；按**严重程度分级**（轻/中/重），重度或反复不缓解才提示就医 | 健康领域错误代价高；避免"狼来了" |
| 追问上限 | 4-5 轮；**三段式**：对话追问 → 动作自测 → 通用放松兜底 | 追问必须收敛；自测兜底是"体格检查引导"的工位简化版 |
| 主动关心选题 | 上下文选题 + **时间衰减去重** + 频率下限 | 疲劳随时间累积，去重不能一刀切 |
| 知识库粒度 | **部位级条目**，条内做**症状→原因结构化映射** | 检索只干"定位部位"，精确推理靠结构化数据 |
| 严重程度判定 | 三条固定客观信号（持续时间/缓解情况/功能影响）+ 三级条件描述 | 判定标准外置成数据，模型只"对照匹配" |
| 检索 vs 载荷 | 只把**部位+别名+症状标签**做 embedding（检索坐标），其余字段原样存 payload | 检索精准 + 命中后整条载荷喂 LLM |
| 召回失败 vs 覆盖缺口 | 召回失败靠语义检索补；覆盖缺口靠补知识补 | 阈值只管"低分硬答"，管不了"没这个词" |
| 三道防线 | ①高危词表前置拦截 → ②阈值 0.5 → ③重度转就医 | 安全 > 召回 > 精确；模型只路由，防呆靠代码 |

### 5.3 知识库 schema（`deskpal/rag/knowledge_base.json`）

```jsonc
{
  "id": "eye_strain",
  "部位": "眼睛",
  "部位别名": ["眼", "双眼"],
  "鉴别问题": "…干涩、酸胀，还是视物模糊？",
  "症状": [
    {
      "标签": ["干涩", "干", "眼干"],
      "可能原因": ["干眼", "用眼过度"],
      "自测": "用力眨眼10次：缓解→干眼；不缓解→用眼过度"  // 判别式，结果直接映射原因
    }
  ],
  "严重程度判定": { "信号": ["持续时间","缓解情况","功能影响"], "轻度":"…","中度":"…","重度":"…" },
  "分级建议": { "轻度":[…], "中度":[…], "重度":[…] },
  "预防建议": […]
}
```

**判断链**：检索定位部位 → 鉴别问题问出症状 → 症状块自测区分原因 → 对照严重程度判定定级 → 按级给建议。

### 5.4 技术选型

- **Embedding**：生产用国内 API bge-m3；手搓阶段用本地 `bge-small-zh-v1.5`（免费离线、能直观看向量）。两者通过统一 `encode` 接口解耦。DeepSeek 不提供 embedding 接口。
- **向量库**：暂用纯 numpy 内积（20 条规模，`vectors @ q` 直接算余弦相似度）。条目多了再上 Chroma。

### 5.5 检索内核实现

**文件**：`deskpal/rag/` 下 `loader.py`、`retriever.py`、`safety.py`、`knowledge_base.json`（20 条部位）。

**语义检索三件事**：加载模型 + 编码检索文本（启动一次）→ 编码 query → `vectors @ q` 算余弦（`normalize_embeddings=True` 后点积=余弦）→ `argsort()[::-1][:top_k]`。

**踩过的坑**：
1. **关键词检索漏召回**：`眼睛难受` 因"难受"不在文本里而全空 → 语义检索补上。
2. **HuggingFace 直连超时**：设 `HF_ENDPOINT=https://hf-mirror.com` 走镜像。
3. **召回失败（覆盖缺口）**：`膝盖疼` 误中"臀部"，根因腿部条目缺"膝盖" → 单独成条 `knee_pain`。教训：覆盖缺口靠补知识，不靠调阈值。
4. **高分方向错**：`胸闷 0.62` 被"圆肩驼背"命中，方向错 → 高危词表前置拦截。
5. **口语缺词**：`弓背` 只 0.51 硬猜 → 补别名 `弓背`/`弓着`。
6. **长句噪声稀释（病二，暂不治）**：完整口语长句被"肌肉/拉长"等噪声词拽偏；`体态` 上位词无区分度。候选解法：LLM 提纯 query / 分词去停用词 / 混合检索 / 换 bge-m3。

**三道防线**（`safety.py` + `retriever.search(threshold=0.5)`）：
- ① 高危词表前置（胸闷/胸痛/心慌/呼吸困难/单侧无力/半身麻木/口角歪斜/单侧小腿肿痛…）命中直接转就医，不进检索；
- ② 阈值 0.5：低于返回"未覆盖"走兜底（由真实 query 分数分布定：正常命中 ≥0.6，唯一该拒的"耳鸣"0.43）；
- ③ 安全边界：重度或反复不缓解才提示就医。

**接入方式**：RAG 检索做成 `search_health_knowledge_tool(query)` 挂进 `make_tools`，由 `llm.bind_tools` 让模型决定是否调用。**分工**：模型只判断"是不是健康问题"（意图路由），三道防线在工具函数内部代码层强制。工程 4 点：`rag/` 包化 / sentence_transformers **延迟导入** / `get_retriever()` **懒加载单例** / `search` 返回完整条目 dict。

---

## 6. 报告 skill（生成健康报告）

### 6.1 Skill 是什么（与工具的区别）

- **Tool（工具）= 动作/函数**：模型决定"要不要调、传什么参"，执行完返回结果。无状态、单次。
- **Skill = 流程/手册**：一段固化的多步流程。在 LangGraph 环境落地为 **subgraph（子图）**——用节点/边把流程固定下来（DeepSeek 不消费 SKILL.md，所以用代码图落地）。

### 6.2 流程设计

```
用户说"报告/体检" → 进入报告会话（main.py 意图路由）
  → collect  读 SQL 周报 + 长期记忆
  → analyze  动态判断关注部位 + 信息是否足够（不够则生成追问）
      ├─ 信息不够 → ask 追问 → 等用户回答 → 回到 analyze
      └─ 信息够   → recommend 检索知识库 + LLM 生成报告（含自测区分原因）
```

**两个关键设计**：
1. **追问循环**：`ReportState.messages` 用 `add_messages` 累积；`analyze` 后条件边分流（`needs_clarify → ask`，否则 `→ recommend`）。不依赖 checkpoint——第二轮 `invoke` 重跑 `collect→analyze`（幂等），真正变化的是 `messages` 里多了用户回答。
2. **无数据主动追问**：首轮 `parts` 为空（无数据参考）→ 主动追问"哪里不舒服"；追问过仍无部位（用户说"没有"）→ 结束给健康报告。避免死循环。

### 6.3 自测区分原因

`recommend` 从"代码拼建议"升级为"检索知识库载荷 → LLM 综合生成"：LLM 根据用户症状描述，从该部位「症状」块里选最贴切的「自测」字段（如「用力眨眼10次：缓解→干眼；不缓解→用眼过度」）区分原因，再给建议/预防。用户没描述症状时，退回「鉴别问题」引导补充。

### 6.4 触发与生命周期

- **触发**：main.py 关键词路由（"报告"/"体检"）→ 进入报告会话（`report_session` 状态机），之后的输入走 `report_graph`（多轮），报告完成退出。
- **退出**：用户说"取消/算了/结束"等退出报告会话。
- **单一入口**：早期做过一个 `generate_health_report_tool`（工具触发），因工具是"一次性调用"无法中途追问，与多轮追问矛盾，**已移除**。报告只有"路由 → 报告会话 → report_graph"一条路径。

---

## 7. 记忆系统

### 7.1 概念划分（工作台 vs 仓库）

| | 短期记忆 | 长期记忆 |
|---|---|---|
| 载体 | 对话窗口内的消息历史（chat_graph 的 history） | SQLite `health_memory` 表 |
| 比喻 | 工作台（当前任务的上下文） | 仓库（跨会话沉淀的事实） |
| 治理 | **滑动窗口 + 滚动概况** | **LLM 提取 + 按部位去重** |

### 7.2 长期记忆（写路径：宁滥勿缺）

- **提取**：`extract_health_facts(llm, text)` 用 LLM 从用户输入提取健康事实 `[{body_part, fact}]`，失败静默降级（不阻塞对话）。
- **归一化**：EXTRACT_PROMPT 要求部位用标准名（"腰部/腰背/下背"→"腰"），保证去重有效。
- **去重**：`HealthMemoryRepo.add_fact` 按 `body_part` **upsert**（同部位更新而非追加），避免反复记录越堆越多。
- **存储选型**：用 SQL 而非向量库——因为报告场景是**主动全量汇总**（`get_all_facts` 一次读全），不是**被动语义召回**。

### 7.3 短期记忆（窗口治理）

- **问题**：对话 history 无界增长会撑爆 LLM 上下文窗口。
- **方案**：`compress_window(messages, summary, llm, window_size=10)` —— 保留最近 10 条消息；超出时把最老一批用 `summarize_conversation` 滚动压缩成概况（≤3 句），概况注入 system prompt。
- **降级**：压缩失败（LLM 异常）保留旧概况，窗口仍收缩，不崩溃。
- **效果**（demo 实测）：窗口=4 时，最老"眼睛干"被压成「用户最近眼睛有点干。建议其每20分钟远眺20秒并多眨眼」，最近 4 条保留。

### 7.4 尚未做的长期记忆召回

当前长期记忆只在**报告 skill**（主动全量汇总）使用。对话链路里还没有"被动语义召回"（新对话里模型何时、如何主动去长期记忆找相关事实）。这需要给长期记忆加 embedding 检索 + 一个召回工具，属于 §9 待办。

---

## 8. 设计决策总表（面试速查）

| 主题 | 决策 | 一句话理由 / 面试话术 |
|---|---|---|
| 架构 | 分层而非单体 | 依赖方向单一，可独立替换呈现/存储 |
| 判定 | 状态驱动而非时间驱动 | 产品差异化，结合真实工作+离开+自评 |
| 推理 | 规则判定 + LLM 推理分工 | "不确定性在哪，LLM 用在哪" |
| 调度 vs 编排 | 调度管"钟"、编排管"线" | 定时器只负责触发，业务线由状态机串联 |
| 并发 | 双线程 + 三同步原语 | 阻塞 ≠ 忙等；主线程阻塞=UI 假死 |
| 容错 | 降级（非熔断） | 循环任务自带重试，降级更简 |
| LLM 接入 | LangChain `init_chat_model` 工厂 | 改 `LLM_PROVIDER` 换模型、不改调用方、无 key 自动降级 mock |
| 模型依赖安装 | `setup_llm.py` 按 provider 只装对应包 | 拒绝"一次装齐所有厂商"，只装用户选中的那一个 |
| RAG vs 工具 | 非结构化文本→RAG，结构化数值→SQL/工具 | 历史数据查询用 `get_weekly_summary_tool` |
| 抗幻觉 | Tool Calling / Grounding | 判断依据外置成可检索可审核的数据 |
| 语义检索 vs 关键词 | embedding 余弦相似度 | 没见过说法也能命中 |
| 安全防线 | 高危词表前置 + 阈值 + 分级就医 | 安全 > 召回 > 精确 |
| Skill vs Tool | Skill=流程/手册，Tool=动作/函数 | 报告 skill 落地为 LangGraph 子图 |
| 追问循环 | add_messages 累积 + 条件边 + 幂等重跑 | 不用 checkpoint 也能多轮 |
| 长期记忆 | SQL（主动全量汇总）非向量库 | 报告是"全量读"，不是"语义召回" |
| 记忆去重 | 提取归一化 + 按部位 upsert | 同部位更新而非追加 |
| 短期记忆 | 滑动窗口 + 滚动概况 | 无界 history → 有界窗口 + LLM 压缩 |

---

## 9. 当前进度与下一步

**已完成**：
- RAG 检索内核 + 三道防线 + 症状鉴别闭环（§5）
- **报告 skill** 完整闭环（§6）：找部位 → 追问/自测 → 给建议，含无数据主动追问、报告会话
- **记忆系统**（§7）：长期记忆（提取归一化 + 去重）+ 短期记忆（滑动窗口 + 滚动概况）
- 休息流程三段式重构（§4.2）
- 22 个单元测试全绿
- **统一 LLM 接口**（§10）：`LLM_PROVIDER` 可配多厂商，默认 DeepSeek，`setup_llm.py` 按 provider 只装对应依赖
- **开源准备**（§10.4）：requirements.txt / .gitignore / .env.example / README.md / setup_llm.py / LICENSE 就绪，待 git init + commit + push

**下一步（待做，按优先级）**：
1. **模式②"弹窗→深聊"引流**：RAG 主动关心（久坐后弹窗问"某部位不适吗"，有则转症状鉴别）。涉及弹窗同步阻塞 vs 深聊异步的线程衔接。
2. **长期记忆被动召回**：给长期记忆加 embedding 检索 + 召回工具，让对话链路能主动从长期记忆找相关事实（当前只有报告 skill 的全量汇总）。
3. **评测召回率**（RAGAS 或自建评测集），验证阈值 0.5 与高危词表的误拦率。
4. **开源发布**：git init → 首次提交 → GitHub 远程 push（README / LICENSE 已就绪）。

**未决/待观察**：
- 知识库覆盖过广（皮肤/代谢/睡眠/情绪超出"工位健康"核心）——先留着看是否抢相似度。
- 向量库最终选型（暂 numpy 内积，条目多了上 Chroma）。
- 高危词表是否误拦"心慌/心悸"（当前倾向保守宁误拦）。
- **长句噪声稀释（病二）**：完整口语长句被噪声词拽偏。候选：LLM 提纯 query / 分词去停用词 / 混合检索 / 换 bge-m3。

---

## 10. 统一 LLM 接口与开源准备

### 10.1 统一 LLM 接入（硬编码 deepseek → 可配 provider）

- **改动**：`config.py` 新增 `llm_provider` / `llm_model_flash` / `llm_model_pro` / `llm_base_url`；`api_key` 统一为 `LLM_API_KEY`；`llm.py` 的 `model_provider` 从硬编码 `"deepseek"` 改为 `settings.llm_provider`。
- **换模型**：改 `.env` 三个变量（`LLM_PROVIDER` + `LLM_MODEL_*` + `LLM_API_KEY`）+ 装对应 `langchain-<provider>` 包。
- **为何保留 LangChain 工厂**：参考 browser-use，但它后来（v0.3.3+）从 LangChain 迁出、自建 Protocol + 每 provider class，是为控制结构化输出/消息/tool-call 格式，**不是因为 `init_chat_model` 不存在**。本项目要的是"换模型不改调用方"，`init_chat_model` 够用。
- **两个坑（README 已提醒）**：① 豆包等 OpenAI 兼容模型无原生 provider → `LLM_PROVIDER=openai` + `LLM_BASE_URL` + 模型名填"接入点 ID"；② 模型必须支持 function calling，否则工具调用静默失效。

### 10.2 key 优先级 bug（已修）

- **现象**：新 key 不生效，日志仍报旧 key `****d06d is invalid`。
- **根因**：`_load_dotenv()` 用 `os.environ.setdefault`，Windows **系统环境变量**残留的旧 `DEEPSEEK_API_KEY` 优先于 `.env`。
- **修复**：删除 User/Machine 两处系统变量 + 统一 key 名为 `LLM_API_KEY`（不留 `DEEPSEEK_API_KEY` 兜底，避免双名混淆）。

### 10.3 模型依赖安装（setup_llm.py）

- **决策**：拒绝"一次装齐所有厂商"，改为 `python setup_llm.py` 读 `LLM_PROVIDER` **只 pip install 对应那一个包**（已装则跳过）。
- **理由**：运行时偷偷 `pip install` 是反模式（权限/网络/可复现）；用户显式跑一条命令装自己选中的包最干净。

### 10.4 开源准备进度

- 已就绪：`requirements.txt`（6 直接依赖）、`.gitignore`、`.env.example`、`README.md`（10 节）、`setup_llm.py`、`LICENSE`（MIT）。
- 待做：`git init` → 首次提交 → GitHub 远程 push。
- 安全：key 只放 `.env`（gitignore），上传前建议注销本地真实 key。

---

## 11. 协作约定

- **分步迭代**：每个模块先讲决策（问题→方案≥2→优缺点→决策→选错会怎样→面试话术），确认后再实现；每步验证。
- **手搓踩坑**：给脚手架+提示让用户自行测试真实撞坑，再一起定位——踩坑比看十遍记得牢。
- **归档**：用户发"归档"→ 更新本文档至最新。
- **安全**：API key 只放 `.env`。
- **Windows 环境**：控制台 GBK 会乱码，日志/输出用 UTF-8。
