<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# agent harness 和 langchain langgraph 和 deep agent 之间的关系

这三者是 **LangChain 官方生态中同一技术栈的三个分层组件**，关系是"层层叠加"而非竞争。

***

## 三层架构定位

LangChain 团队明确将这三个工具定位为不同抽象层级 ：[^1_1]


| 工具 | 定位 | 核心职责 |
| :-- | :-- | :-- |
| **LangGraph** | Agent Runtime（运行时） | 底层图编排、状态管理、流式响应、线程持久化、HITL |
| **LangChain** | Agent Framework（框架） | 中层抽象，提供模型接口、Prompt模板、工具调用、RAG 等积木 |
| **DeepAgents** | Agent Harness（挂载工具） | 高层开箱即用，内置规划、文件系统、子 Agent、默认 Prompt |


***

## 依赖与调用关系

三者是**累积式依赖**，自下而上构建 ：[^1_2][^1_3]

```
+---------------------------+
|      DeepAgents           |  ← 开箱即用，建在 LangChain 之上
+---------------------------+
         ↑ Built on
+---------------------------+
|       LangChain           |  ← Agent 框架，建在 LangGraph 之上
+---------------------------+
         ↑ Built on
+---------------------------+
|       LangGraph           |  ← Agent 运行时，最底层基础设施
+---------------------------+
```

LangChain 1.0 本身就是构建在 LangGraph 之上的；DeepAgents SDK 则在 LangGraph 之上再叠加了规划能力、虚拟文件系统和子 Agent 机制 。[^1_4][^1_5]

***

## "Agent Harness" 是什么意思

"Harness"（挂载/驾驭工具）这个词的意思是：**你不需要从零搭建 Agent 的每一块，它已经把常见能力预配好了**，你只需接入自定义工具和 Prompt 。官方将 DeepAgents 类比为 "a general purpose version of Claude Code"——一个开箱即用但可定制的自主 Agent 环境 。[^1_6]

DeepAgents 在 0.2 版本引入了"可插拔后端（Backend）"，允许用任意存储方式替换原来依赖 LangGraph State 的虚拟文件系统 。[^1_2]

***

## 如何选型

- **快速原型 / 刚入门**：用 LangChain，快速组合 LLM + 工具[^1_5]
- **进入生产 / 需要并发与状态持久化**：用 LangGraph[^1_5]
- **复杂长任务 / 希望 Agent 更自主、少写代码**：用 DeepAgents[^1_1]

三者并不互斥，复杂项目完全可以同时用到三层：用 LangChain 搭逻辑 → 用 LangGraph 保证生产稳定性 → 用 DeepAgents 赋予更强自主能力 。[^1_5]
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://juejin.cn/post/7568527869187751979

[^1_2]: https://blog.csdn.net/YoungOne2333/article/details/154781447

[^1_3]: https://www.cnblogs.com/itech/p/19189589

[^1_4]: https://docs.langchain.com/oss/python/concepts/products

[^1_5]: https://devpress.csdn.net/xclaw/69c0f4b954b52172bc6395cd.html

[^1_6]: https://x.com/frxiaobei/status/1982270058861830276

[^1_7]: https://www.cnblogs.com/aimagician/p/19954466

[^1_8]: https://modelengine.csdn.net/690b1f175511483559e27808.html

[^1_9]: https://www.cnblogs.com/crazymakercircle/p/19893711

[^1_10]: https://juejin.cn/post/7599579865608208426

[^1_11]: https://gitcode.csdn.net/69d76adb0a2f6a37c59e0a70.html

[^1_12]: https://developer.aliyun.com/article/1728503

[^1_13]: https://juejin.cn/post/7629231480154816553

[^1_14]: https://blog.csdn.net/m0_59162559/article/details/154082203

[^1_15]: https://juejin.cn/post/7626988865536507944


---

# 那我们可以自定义其中每一个部分吗

**可以，三个层次都支持自定义，而且官方明确设计为"可插拔"架构。** 以下逐层说明。

***

## LangGraph — 最高自由度

LangGraph 是纯低层运行时，**几乎每个组件都可以替换** ：

- **Graph 结构**：自定义节点（Node）和边（Edge），包括条件分支
- **State 设计**：完全由你定义状态 Schema（用 TypedDict / Pydantic）
- **Persistence Backend**：内置 Memory Saver，也可接入 PostgreSQL、Redis 等
- **Streaming 方式**：token 级、节点级、事件级均可定制
- **Human-in-the-loop（HITL）**：可在任意节点插入中断等待人工审批

***

## LangChain — 积木式替换

LangChain 以"接口统一"为核心，所有积木均可替换 ：

- **模型层**：任意切换 OpenAI、Claude、Gemini、本地 Ollama 模型
- **工具（Tools）**：内置 200+ 工具，也可用 `@tool` 装饰器自定义
- **Prompt 模板**：自定义 SystemMessage / HumanMessage / ChatPromptTemplate
- **Memory / RAG**：自定义向量库（FAISS、Chroma、Weaviate）和检索逻辑
- **Agent 循环**：可替换 ReAct、OpenAI Functions 等不同推理策略

***

## Deep Agents — 配置式自定义

Deep Agents 是"电池已装好"的高层框架，通过**配置而非底层编码**实现自定义 ：


| 能力 | 自定义方式 |
| :-- | :-- |
| **文件系统后端** | 可插拔 `StateBackend`，替换为 S3、本地磁盘等 |
| **子 Agent** | 可定义新的子 Agent，调整其 Prompt 和工具集 |
| **Planning 逻辑** | 可修改任务拆解的默认 Prompt |
| **HITL** | 通过 `interrupt_on` 参数配置需要审批的节点 |
| **Token 管理** | 对话历史摘要与工具结果裁剪策略均可调整 |


***

## 核心原则

三者的自由度是"越底层越自由，越高层越省事" ：

- 如果你想**精细控制**每一步 → 从 LangGraph 入手
- 如果你想**快速组合工具和模型** → 用 LangChain 的积木
- 如果你想**专注于 Agent 逻辑**，不想自己搭基础设施 → 用 Deep Agents，但接受它的约定

由于三层是叠加关系，你完全可以在 Deep Agents 之上的任务层做配置，同时在下面的 LangGraph 层做更底层的自定义，两者并不冲突 。

---

# 那比如说现在市面上的这个 deeptutor，还有这个 onyx，还有这个 Claude Code, 还有这个 Gemini c I Kimi c I 它的这些。就是底层原理是不是跟这个 Lang chain 是差不多的，就是或者是他们是不是基于这个 longain 开发

这是一个很好的问题，答案是**不完全一样，要分两个维度来看**：底层原理相似，但是否基于 LangChain 开发则因产品而异。

***

## 底层原理：大家都在用同一套逻辑

无论是 Claude Code、Gemini CLI、Kimi、Onyx 还是 DeepTutor，**核心架构原理基本一致** ：[^3_1][^3_2]

- **LLM + Tool Calling**：让模型决定什么时候调用什么工具
- **ReAct 模式**（Reasoning → Acting → Observing 循环）：模型思考 → 执行操作 → 看结果 → 再思考
- **持久化状态管理**：记住上下文和历史
- **RAG**（检索增强生成）：结合外部知识库

这套逻辑并不是 LangChain 发明的，而是 AI Agent 领域的通用范式。LangChain 只是把这套逻辑**封装成了好用的工具库**。

***

## 是否基于 LangChain：因产品而异

| 产品 | 是否基于 LangChain | 说明 |
| :-- | :-- | :-- |
| **DeepTutor** | 不是 | 自研 `nanobot` 引擎，底层自己写的心跳调度机制和状态机 [^3_3] |
| **Onyx** | 不是 | 自研 Agent 编排，LangChain 技术路线之外 |
| **Claude Code** | **不是** | Anthropic 自研，源码未开源，完全独立于 LangChain [^3_4] |
| **Gemini CLI** | **不是** | Google 自研，集成 Veo/Imagen 等 Google 模态工具链 [^3_1] |
| **Kimi** | **可以接入 LangChain**，但本身不基于它 | Kimi API 兼容 OpenAI 接口规范，所以可以通过 LangChain 调用 Kimi 作为 LLM backend，但 Kimi 自己的产品不依赖 LangChain [^3_5][^3_6] |


***

## 关键区别

**大厂（Anthropic、Google、Moonshot）自研产品几乎从不用 LangChain**，原因是 ：[^3_4][^3_1]

- 他们有专属的推理基础设施 and 优化需求
- LangChain 的抽象层会引入额外延迟和依赖
- 自研能做更深度的模型-工具协同优化

**LangChain/LangGraph 的主要用户群**是独立开发者、中小型团队、企业内部工具，用它快速搭建 Agent 应用，而不是头部大模型厂商。大厂通常只会将自家模型**作为 LLM provider 接入** LangChain 生态，供别人调用。
<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15][^3_7][^3_8][^3_9]</span>

<div align="center">⁂</div>

[^3_1]: https://masterconcept.ai/zh-hant/blog/gemini-cli-vs-claude-code-workflow-era/

[^3_2]: https://blog.csdn.net/RickyIT/article/details/160418032

[^3_3]: https://www.h3blog.com/article/809/

[^3_4]: https://www.facebook.com/groups/aigctw/posts/2993322857518273/

[^3_5]: https://docs.feishu.cn/v/wiki/E4plwzra9itRBJksuQ6cUQpenie/a6

[^3_6]: https://blog.csdn.net/lonely__snow/article/details/143579550

[^3_7]: https://blog.csdn.net/u014390502/article/details/160234236

[^3_8]: https://github.com/superiorlu/AiTreasureBox/blob/main/README.zh-CN.md

[^3_9]: https://x.com/search?q=GitHub\&src=trend_click\&pt=1467933794699259908\&vertical=trends

[^3_10]: https://blog.csdn.net/u014390502/article/details/160526123

[^3_11]: https://github.com/zamalali/langchain-code

[^3_12]: https://blog.csdn.net/u014390502/article/details/160496768

[^3_13]: https://time.geekbang.org/course/detail/100625601-711805

[^3_14]: https://github.com/felixlu/awesome-stars

[^3_15]: https://www.reddit.com/r/LangChain/comments/1mr1y18/i_graduated_from_langgraph/


---

# 那你看，他们是不是能够实现和 Lang chain 差不多的功能吗？那他们具体是如何实现的呢？就是说，不用这个 Lang chain 的话，他们怎么自己写那些函数啊？怎么自己写那些玩意儿啊？是不是有一套更加底层的那那个方法可以做到这一

**完全可以自己实现，而且底层其实很简单。** LangChain 本质上只是对几个基础模式的封装，不用它照样能做一模一样的事。下面从"原理层"到"代码层"分别解释。

***

## AI Agent 的五大核心模块

所有这些产品，不管用不用 LangChain，都是围绕同一套底层模块构建的 ：[^4_1][^4_2]


| 模块 | 职责 | 不用 LangChain 怎么实现 |
| :-- | :-- | :-- |
| **LLM 核心** | 理解+生成语言 | 直接调用 OpenAI / Claude / Gemini API |
| **Memory 记忆** | 保存上下文历史 | 维护一个 `messages[]` 列表，控制长度 |
| **Planning 规划** | 把大任务拆解成子任务 | 写一段特殊 Prompt 让模型输出步骤列表 |
| **Tool-use 工具调用** | 让模型能执行外部操作 | 用 `function_calling` 或解析模型 JSON 输出 |
| **Reflection 反思** | 自我检查输出质量 | 让模型再调用一次，评估上一步结果 |


***

## 最底层实现：就是三件事

LangChain 源码剥开来，核心就是这三件事 ：[^4_3]

### 1. 调用 LLM API（最底层）

```python
import openai

response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "帮我查一下天气"}
    ]
)
print(response.choices[^4_0].message.content)
```

这就是一切的基础。LangChain 的 `ChatOpenAI` 类，本质上就是对这几行代码的封装。

### 2. 自己实现 Tool Calling（工具调用）

模型原生支持 `function_calling`，不需要任何框架 ：[^4_3]

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询城市天气",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}}
        }
    }
}]

response = openai.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools
)
# 模型返回要调用哪个工具 → 你执行 → 把结果塞回 messages → 再调用模型
```


### 3. 自己实现 ReAct 循环（Agent 主循环）

Claude Code、Gemini CLI 的核心就是这个 while 循环 ：[^4_2]

```python
while True:
    response = call_llm(messages)          # 让模型思考
    if response.tool_calls:
        result = execute_tool(response)    # 执行工具
        messages.append(result)            # 把结果放回去
    else:
        print(response.content)            # 输出最终答案
        break
```


***

## 大厂为什么不用 LangChain

Claude Code 这类产品自研的原因不是"LangChain 做不到"，而是 ：[^4_4][^4_5]

- **性能**：LangChain 多了一层抽象，每次调用多几毫秒延迟，百万用户规模会放大
- **可控性**：自研可以对 token 计数、错误重试、流式输出做深度定制
- **依赖风险**：LangChain 版本更新频繁，大型产品不愿被第三方库绑架
- **专属优化**：比如 Claude Code 可以深度利用 Claude 的 `extended thinking` 特性，这在通用框架里很难实现

***

## 一句话总结

> LangChain 是把"三行代码能写的事"包装成"一行代码"的工具库，大厂有能力也有理由自己写那三行，而个人开发者和中小团队用 LangChain 省时间。本质都是：**Prompt + API 调用 + while 循环**。[^4_1][^4_3]
<span style="display:none">[^4_10][^4_11][^4_12][^4_13][^4_14][^4_15][^4_6][^4_7][^4_8][^4_9]</span>

<div align="center">⁂</div>

[^4_1]: https://developer.aliyun.com/article/1679198

[^4_2]: https://cloud.tencent.com/developer/article/2579281

[^4_3]: https://qiankunli.github.io/2023/08/29/langchain_source.html

[^4_4]: https://www.ibm.com/cn-zh/think/topics/langchain

[^4_5]: https://github.com/WGrape/Blog/issues/276

[^4_6]: https://www.youtube.com/watch?v=-5w9TQN0iO4

[^4_7]: https://blog.csdn.net/AWsggdrg/article/details/144971732

[^4_8]: https://cloud.google.com/use-cases/langchain?hl=zh-CN

[^4_9]: https://developer.aliyun.com/article/1394391

[^4_10]: https://langchain.ichuangpai.com/langchain/tutorial/Run-the-agent.html

[^4_11]: https://www.cnblogs.com/crazymakercircle/p/19087400

[^4_12]: https://cloud.tencent.com/developer/article/2579281?policyId=1003

[^4_13]: https://modelengine.csdn.net/690b1b915511483559e26729.html

[^4_14]: https://blog.csdn.net/Z987421/article/details/146333797

[^4_15]: https://aws.amazon.com/cn/blogs/china/enterprise-level-agentic-ai-architecture-design/


---

# 手写 Agent 的工具调用解析器有哪些常见坑

最常见的坑，其实不是“解析 JSON”本身，而是**模型输出不稳定 + 工具协议设计不严谨 + 执行与回传链路不健壮**这三类问题叠加。手写 Agent 时，工具调用解析器最容易在这些地方翻车 。[^5_1][^5_2]

## 常见坑

- **输出格式不稳定。** 模型有时返回纯自然语言，有时夹杂 JSON，有时外面再套一层代码块，导致解析器要兼容很多变体 。[^5_3][^5_4]
- **JSON 不合法。** 常见问题包括单引号、尾逗号、缺引号、转义字符错误、代码块没闭合，直接 `json.loads()` 就炸掉 。[^5_2][^5_4]
- **工具 schema 写得太随意。** 工具名、参数名、参数类型、必填项、description 不清楚，模型就会乱填参数或根本不调用工具 。[^5_5][^5_1]
- **只会“抓字符串”，不会“确认意图”。** 你解析到一个 JSON，不代表它真的是工具调用；要先判断是否包含合法的 `name`、`arguments` 和可执行目标 。[^5_4]
- **错误处理太粗暴。** 解析失败、工具超时、外部 API 报错、权限不足，如果都直接抛异常，Agent 很快就会中断或进入死循环 。[^5_5][^5_2]
- **无限循环。** 模型一直认为“还要继续调用工具”，但你没有 `max_iterations`、终止条件或重复调用检测，就会卡死 。[^5_1]
- **工具返回值格式不统一。** 有的工具返回字符串，有的返回 dict，有的返回 float，回传给模型时如果没有统一序列化，下一轮上下文就乱了 。[^5_1]
- **上下文污染。** 你把太长的工具输出原样塞回 messages，后面 token 爆掉，模型又开始误判、漏判工具调用 。[^5_1]
- **参数校验缺失。** 模型填了 `"city": 123` 或漏了必填字段，如果你没做 Pydantic/自定义校验，工具层会报更隐蔽的错 。[^5_2]
- **工具选择过多。** 工具一多，模型容易选错；很多失败不是“不会解析”，而是“工具命名和描述没有区分度” 。[^5_6][^5_5]


## 解析器该怎么写

手写时，最好把解析器拆成三步：**识别格式 → 提取结构 → 校验语义** 。[^5_4][^5_2]

1. 先从原始文本里提取候选 JSON。
2. 再判断它是不是合法的工具调用结构。
3. 最后校验 `name`、`arguments`、参数类型、必填字段。

这样比“直接正则抓 JSON 然后执行”稳得多 。[^5_4]

## 一个实用原则

你可以把它理解成：**解析器不是用来“猜”模型想干什么，而是用来“验证”模型已经明确表达了什么。**
所以工具调用协议要尽量短、清晰、强约束，错误要可恢复，失败要能重试 。[^5_5][^5_2]

## 最该优先补的三件事

- **严格 schema。** 工具定义要写清楚“什么时候用、什么时候不用、参数怎么填” 。[^5_5][^5_1]
- **稳健解析。** 支持代码块、裸 JSON、夹杂自然语言的情况，同时做合法性校验 。[^5_4]
- **循环控制。** 加 `max_iterations`、重复调用检测、失败退回自然语言回答 。[^5_2][^5_1]

如果你愿意，我可以下一条直接给你画一个“手写 Agent 工具调用解析器”的标准流程图，或者直接给你一份 Python 版的最小可用实现。
<span style="display:none">[^5_10][^5_7][^5_8][^5_9]</span>

<div align="center">⁂</div>

[^5_1]: https://www.cnblogs.com/qiniushanghai/p/19906043

[^5_2]: https://blog.gitcode.com/a4c7ca086b8ab3ed470150b334145e2b.html

[^5_3]: https://juejin.cn/post/7602800677712019490

[^5_4]: https://blog.csdn.net/pythonhy/article/details/153683151

[^5_5]: https://www.waylandz.com/ai-agent-book/第03章-工具调用基础/

[^5_6]: https://blog.csdn.net/m0_59164520/article/details/156146369

[^5_7]: https://blog.csdn.net/weixin_44919384/article/details/155192909

[^5_8]: https://blog.csdn.net/yangshangwei/article/details/152783885

[^5_9]: https://juejin.cn/post/7563332279889985576

[^5_10]: https://juejin.cn/post/7623663779579428927


---

# 比如说我现在有一个工作流程，就是主要是说我有一个 PDF，然后我首先第一步要把它转录成 markdown，使用这个 mind u 的 API。然后第二步是要用 Agent 去把它划分章节，然后每个 sub agent 去读指定章节的内容。第三步是这 Agent 要根据我自己的喜欢的这种写作风格，就是把这个 Agent 这个分别按照每一个章节写作，增量式的这种反复阅读反复写作，然后加入 remark 或者是怎么样的，根据我自己的 knowledge base, 就是根据我自己的知识基础知识储备去。然后还有我容易忘记的一些东西，然后去按照我自己的风格习惯去写作一个新的拉泰克的这种。笔记或者是重新组织这个书籍编排的方式然后，我想把这样一个流程呢，封装成一个完整的，可以确切运行的流程然后，这个东西的话，我感觉像是 skill，或者是 cloud code 的 agent team, 或者是 sub agents, 好像并不能够完美的这种精准的，很精准的实现，所所以说我在想，我是不是要搭一个 long chain, 就是这样一套流程下来搞搞定

你描述的这个流程非常清晰，而且**完全值得用 LangGraph 来搭**，而不是依赖 Claude Code 的 Agent Team 或者通用 Skill——因为你的流程有几个关键特征使它需要精确编排 。下面我帮你把整个架构梳理清楚。[^6_1]

***

## 为什么 Claude Code / 通用 Skill 不够用

你的流程本质是一个**有状态的、多阶段的、需要并行 sub-agent 的流水线** ，这几点决定了 Claude Code 不够用：[^6_2][^6_1]

- Claude Code 的 Agent Team 没有**持久化状态**，中间步骤结果无法稳定传递
- 通用 Skill 无法保证**章节并行处理后的合并顺序**
- 你的"增量式反复阅读写作 + 个人 knowledge base 融入"需要**自定义 Prompt + 循环控制**，这是 LangGraph 的强项

***

## 推荐架构：LangGraph + MinerU API

你的流程对应一个四层 Graph ：[^6_1][^6_2]

```
PDF 文件
  │
  ▼
[Node 1] MinerU API → 输出完整 Markdown
  │
  ▼
[Node 2] Supervisor Agent → 解析章节结构，分配任务
  │
  ├─► [Sub-Agent Ch.1] 并行
  ├─► [Sub-Agent Ch.2] 并行   ← 每个读指定章节，带你的 KB 和写作风格 Prompt
  ├─► [Sub-Agent Ch.3] 并行
  │      ↑ 增量反思循环 (Reflection Node)
  ▼
[Node 3] Merger Agent → 合并各章节输出，维护前后连贯
  │
  ▼
[Node 4] LaTeX Formatter → 输出 .tex 笔记
```


***

## 每个节点具体怎么实现

**Node 1：MinerU 转录**[^6_3]

```python
import requests

def mineru_convert(pdf_path):
    # 调用 mineru.net API
    response = requests.post(
        "https://mineru.net/api/v4/extract/task",
        headers={"Authorization": f"Bearer {MINERU_API_KEY}"},
        files={"file": open(pdf_path, "rb")},
        data={"output_format": "markdown"}
    )
    return response.json()["markdown"]
```

**Node 2：Supervisor 章节划分**

让模型分析 Markdown 的标题结构，输出 `[{"chapter": 1, "title": "...", "content": "..."}]`，这是一个纯结构提取任务，不需要复杂推理。

**Node 3：并行 Sub-Agent（核心）**[^6_4][^6_2]

每个 Sub-Agent 的 Prompt 包含三层注入：

- **原始章节内容**（来自 Node 2）
- **你的 knowledge base**（RAG 检索相关片段）
- **你的写作风格 Prompt**（固定的 System Prompt，描述你偏好的结构、术语、Remark 插入逻辑）

增量反思循环：

```
初稿 → Reflection Prompt（"检查：是否有你容易忘的概念？是否插入了 Remark？"）→ 修改稿 → 输出
```

**Node 4：LaTeX 输出**

用 Merger Agent 把各章节按顺序合并，然后用 LaTeX 模板格式化（`\section`、`\begin{remark}`、`\begin{theorem}` 等）。

***

## 几个关键设计决策

| 问题 | 推荐方案 |
| :-- | :-- |
| Knowledge Base 怎么存？ | 用 FAISS 或 Chroma 本地向量库，启动时一次性嵌入你的笔记 |
| 写作风格怎么定义？ | 用 5-10 个你自己写的笔记段落做 few-shot 示例放进 System Prompt |
| 并行 sub-agent 失败怎么办？ | LangGraph 支持单个 sub-agent 失败重试，不影响其他章节 [^6_5] |
| 增量反思循环几次？ | 建议 `max_iterations=2`，防止无限循环，2 轮反思已经够用 |
| LaTeX 模板 | 先用 `\documentclass{article}` + `amsthm` 包固定 Remark/Proof 环境 |


***

## 结论

**LangGraph 是目前最合适这个流程的选择**，理由是 ：[^6_2][^6_1]

1. 原生支持 **并行 sub-agent**（Send API）
2. **状态持久化**，中途失败可以从断点恢复
3. 支持**循环 + 条件边**（反思 → 修改 → 再检查的循环）
4. 和 MinerU、OpenAI/Claude API 都可以直接对接，不需要任何中间胶水

如果你想，我可以直接给你生成这个完整流程的 **可运行 Python 代码骨架**，包括 MinerU 调用、LangGraph 状态定义、并行 sub-agent、LaTeX 输出这几块。
<span style="display:none">[^6_10][^6_11][^6_12][^6_13][^6_14][^6_15][^6_6][^6_7][^6_8][^6_9]</span>

<div align="center">⁂</div>

[^6_1]: https://www.langchain.com/blog/langgraph-multi-agent-workflows

[^6_2]: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents

[^6_3]: https://mineru.net

[^6_4]: https://www.reddit.com/r/LangChain/comments/1cthrqz/agents_working_in_parallel_with_langgraph/

[^6_5]: https://github.com/langchain-ai/deepagents/issues/694

[^6_6]: https://github.com/opendatalab/MinerU

[^6_7]: https://community.openai.com/t/converting-pdf-to-markdown-with-ocr/762476

[^6_8]: https://jimmysong.io/blog/pdf-to-markdown-open-source-deep-dive/

[^6_9]: https://developer.adobe.com/document-services/docs/overview/pdf-extract-api/howtos/pdf-to-markdown-api/

[^6_10]: https://ai.gopubby.com/benchmarking-pdf-to-markdown-document-converters-part-2-0439867a3676

[^6_11]: https://www.reddit.com/r/LangChain/comments/1ilnftx/best_nonpaid_way_to_turn_complex_pdfs_into/

[^6_12]: https://www.scribd.com/document/868911275/Slides

[^6_13]: https://launchdarkly.com/docs/tutorials/agents-langgraph

[^6_14]: https://www.linkedin.com/posts/aloycwl_openclaw-master-pdf-to-markdown-conversion-activity-7438626656434491392-yhqe

[^6_15]: https://www.youtube.com/watch?v=E0fQWFNqGgg


---

# 这是我希望我的这个，呃，我希望我的这个，呃，就是说第一步是用这个 minor u 的 API，然后第二步是使用这个，呃，使用这个 mini max 的这些模型，然后呢可以建立很多个 sub agent，就我希望你转录之后呢你有一个 agent 可以去读一下这个文件的结构，然后去看把它划分一下，然后再派任务，像是一个 agent team 一样派任务给到这个其他的 agent，就像那个 Claude Code 里面的 agent team 一样，然后呢最后每个 agent 输出一段东西，然后可能是反复的这个样子输出一些东西，然后 呃，然后最后再拼接到各分分装成各个小的子 sub latec 的这种文件里面去，然后呢最后再拼接成一个完整的，就是一个 man 点 tech，然后可以把这些东西都给囊括起来，然后这些 sub agent 呢都有一段提示词，知道我自己喜欢的写作风格是什么样子，然后知道我自己的习惯，然后呢可能你写完了之后还有一个 retrieve 这种功能，就是 retriever，就是再再反复去检查一下是否按照我喜欢的风格去进行一个编排

代码包已经生成，包含三个文件：`main.py`、`requirements.txt`、`README.md`。下面是整体结构说明。

***

## 完整流程图

```
PDF
 │
 ▼ Step 1: MinerU API
[转录节点] ──────────────→ converted.md
 │
 ▼ Step 2: Supervisor Agent
[章节划分] ──────────────→ [{index, title, content}, ...]
 │
 │  Send API（并行分发）
 ├──→ [Sub-Agent 第1章] ──┐
 ├──→ [Sub-Agent 第2章] ──┤  每章独立，带你的写作风格 Prompt
 ├──→ [Sub-Agent 第3章] ──┤
 │                        │
 ▼ Step 4（汇聚）         │
[Retriever Agent] ←───────┘
 │  逐章审查核查清单，修正不符合风格的地方
 ▼ Step 5: Assembler
[拼接] ──→ chapter_01.tex / chapter_02.tex / ... / main.tex
```


***

## 三个关键设计点

**并行 Sub-Agent 用 LangGraph 的 `Send` API 实现** ，每章独立运行互不阻塞，章节越多效率提升越明显。`chapter_outputs` 用 `operator.add` 做并发安全的累积写入。[^7_1]

**Retriever 是独立的审查节点**，不在 Sub-Agent 内部做反思，而是所有章节完成后统一走一遍核查清单。这样风格标准是全局一致的，不会因模型随机性产生章节间的风格漂移。

**输出结构是 `main.tex` + 多个子文件**，通过 `\input{}` 引用。好处是每章可以单独编译调试，最后拼成完整文档。

***

## 快速启动

```bash
pip install -r requirements.txt
export MINERU_API_KEY="你的 Key"
export MINIMAX_API_KEY="你的 Key"
python main.py 你的书.pdf
```

最需要你自定义的部分是 `main.py` 里的 `MY_STYLE_PROMPT`——把你的知识背景、LaTeX 习惯、容易忘的概念领域填进去，越具体效果越好。

<div align="center">⁂</div>

[^7_1]: https://www.reddit.com/r/LangChain/comments/1cthrqz/agents_working_in_parallel_with_langgraph/


---

# 比如说我现在主要想要实现的，就是我现在主要想实现的一个功能是说，呃，首先我有任意给定一个PDF嘛，我想要把它转化成一些标准的LaTeX的这种格式，然后可以，呃，我可以指定一些模板，就是比如说AMS Art或者是Article或者是这个CTeX Art，或者就是各种指定的模板我可能存了一些这些模板怎么样去使用的这样一些信息进去，然后呢它就可以把任意一个像教材这样子的PDF转化成这种，呃，LaTeX，就是说，呃，按照我刚才说的流程啊，像这种分章节啊怎么怎么样啊，然后转化成一个很标准的LaTeX，然后方便我去阅读，然后并且去修改这些内容，然后想建立这样的一个流程，这样子可不可以完全从一个代码直接实现，就是像这种Longchain啊或者是Longgraph这种东西用这种比较底层的东西然后来建立这样的一个流程，呃，可能跑一下这个Python程序或者是什么程序就可以把它搞定了，就是可以联合调用我的一些API这样子

代码已打包好，三个文件：`main.py` / `requirements.txt` / `README.md`。下面是完整说明。

***

## 使用方式（三步搞定）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Key
export MINERU_API_KEY="你的 Key"
export MINIMAX_API_KEY="你的 Key"

# 3. 运行
python main.py 你的书.pdf --template amsart
```

查看所有模板：

```bash
python main.py --list-templates
```


***

## 内置四套模板

| 命令参数 | 适用场景 |
| :-- | :-- |
| `amsart` | 数学论文/笔记，自带 theorem/lemma/definition/remark |
| `article` | 通用教材，中文环境名（定理/引理/定义） |
| `ctexart` | 中文教材，中文排版优先 |
| `beamer` | 把教材内容转成幻灯片 |


***

## 输出文件

```
output/
├── converted.md          # MinerU 转录结果（自动缓存，不重复调用）
├── ch01_xxx.tex          # 各章节初稿
├── ch01_xxx_reviewed.tex # 经 Retriever 检查后的版本
├── main.tex              # 完整合并文件（直接 xelatex 编译）
└── main_modular.tex      # 模块版（\input 引用各章）
```


***

## 添加你自己的模板

只需在 `main.py` 的 `TEMPLATES` 字典里加一个 key，填三个字段：`preamble`（导言区）、`body_wrapper`（document 环境）、`style_hint`（告诉 AI 用什么环境和风格）。比如你有自己的 `mytemplate.cls` 文件，直接套进去就行。

`converted.md` 有缓存机制——同一个 PDF 第二次跑不会重复调用 MinerU，直接从缓存读，节省 API 费用。