<p align="center">
  <strong>User Insights</strong><br/>
  <sub>Stop guessing what users want. Read what they actually say.</sub>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#how-it-works">How It Works</a> ·
  <a href="#report-structure">Report Structure</a> ·
  <a href="#prerequisites">Prerequisites</a> ·
  <a href="#before-you-use-this">Before you use this</a>
</p>

---

User Insights is a dual-platform market intelligence pipeline that scrapes YouTube and Reddit, filters out ads and noise, and extracts structured signals from real user conversations — every claim backed by a verbatim quote and source URL. Built to surface both the loud patterns and the quiet, high-value insights that volume-based tools miss.

**English** · [中文](#中文)

## Quick Start

### Install as a Claude Code skill

```bash
cp SKILL.md ~/.claude/skills/user-insights/SKILL.md
```

Say **"run user-insights"**. On first run, the agent checks your setup and asks you to paste your API keys into chat — one-time setup. After that, just tell it what to research and it handles the rest. Keys are saved to `~/.user-insights.env`.

### Run from CLI

```bash
pip install -e .
export ANTHROPIC_API_KEY="your-key-here"
export YOUTUBE_API_KEY="your-key-here"
export REDDIT_CLIENT_ID="your-id"
export REDDIT_CLIENT_SECRET="your-secret"
user-insights run --question "What do users think about AI coding assistants?"
```

## Prerequisites

**You need to bring your own — this project provides no API keys.**

| Service | What you need | Where to get it |
|---|---|---|
| LLM provider | API key | Anthropic Console, OpenAI Platform, or compatible provider |
| YouTube Data API v3 | API key | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| Reddit API | Client ID + Client Secret | [Reddit App Preferences](https://www.reddit.com/prefs/apps) |

Set them as environment variables (defaults to `ANTHROPIC_API_KEY`). For OpenAI-compatible providers, run `user-insights config` to set provider, base URL, and model.

You are responsible for complying with the terms of service and data policies of each platform you connect to.

## What Is This?

User Insights doesn't just count mentions. It separates signal from noise at multiple layers:

- **Filters out ads, sponsored reviews, and off-topic noise** before they reach extraction — sovereignty boundaries block adjacent-but-irrelevant discussions, and the quality engine weeds out empty emotional rants and low-effort comments.
- **Catches thin-but-valuable signals** that volume-based tools would miss. A single Reddit comment from a practitioner describing their exact workflow breakdown is worth more than fifty "this is great" replies. The pipeline preserves these.
- **Surfaces what users actually say**, not what influencers or marketers claim. Verbatim quotes with source URLs — raw frontline feedback on pain points, feature gaps, and willingness to pay.
- **Avoids the mediocre-consensus trap.** When the loudest voices drown out the sharpest observations, the stats layer (Python-computed frequency and sentiment) keeps the narrative honest.

The pipeline runs in ~10–25 minutes. You get a report you can scan in 60 seconds and drill into when something matters.

### What kind of questions work best

This pipeline reads what real users post on social platforms — not what analysts write in reports. It works best with **specific, concrete questions** that match how people actually talk:

| Good (specific) | Not a fit (too broad) |
|---|---|
| "What do users hate about Notion's pricing?" | "What's the future of productivity software?" |
| "Why are people switching from Ender to Bambu Lab?" | "How big is the 3D printing market?" |
| "Do users trust AI coding assistants enough to pay?" | "What's the state of AI in 2026?" |

A good question names a product, a user behavior, or a pain point. If your question sounds like something you'd ask a market analyst rather than a Reddit thread, try ChatGPT or Gemini instead — they're better at synthesizing broad industry narratives. This tool is for catching what users actually say when no one's asking them.

## How It Works

```
Question → Sovereignty Init → Brain Planner → Scout → Dual Scrape
                                                          ├─ Reddit (PRAW)
                                                          └─ YouTube (Data API + yt-dlp)
→ Quality Gate → 3D Anchor Extraction → Stats → Synthesis → Report
```

**Sovereignty Init** defines semantic boundaries before any data is fetched — preventing adjacent-but-irrelevant content from polluting results.

**Platform asymmetry is a feature.** YouTube captures buyer expectations and hype. Reddit captures practitioner friction and operational reality. The gap between them is the product opportunity space.

**Python computes the facts. LLM writes the narrative.** Sentiment distribution, platform voice share, and top tags are deterministic. The LLM synthesizes them into readable analysis but cannot invent numbers — the Execution Manifest locks the data.

## Report Structure

Every report follows a four-part format designed for fast reading:

```
# Executive Answer           ← 60-second grasp of key findings
# Detailed Analysis          ← Market Landscape · Pulse · Expectation vs Reality
# Strategic Recommendations  ← Prioritized suggestions with rationale and risk
# Evidence & Methodology     ← Verbatim source table · Execution Manifest
```

The **Executive Answer** leads with bold topic sentences — one key finding per paragraph. Skip the rest if you only need the headline.

## What Makes This Different

- **Noise-resistant.** Ads, sponsored content, and adjacent-topic noise are filtered at multiple stages — sovereignty boundaries, quality heuristics, and LLM self-gating. You read signals, not clutter.
- **Thin-signal aware.** Volume-based tools chase the loudest crowd. This pipeline keeps the one Reddit comment where someone describes exactly why they cancelled their subscription — because that's where the insight lives.
- **Sourced, not hallucinated.** Every claim links to a Reddit comment or YouTube timestamp. Raw frontline feedback on pain points, feature gaps, and willingness to pay.
- **Platform asymmetry is a feature.** YouTube ≠ Reddit. The pipeline reads YouTube for expectations and Reddit for operational reality — the gap between them is the opportunity.
- **Auditable.** The Execution Manifest is Python-generated — if the LLM fabricates a number, the Manifest contradicts it.
- **Domain-agnostic.** Works for SaaS, hardware, consumer apps, devtools. Only the anchors and subreddits change.
- **English only, for now.** The pipeline targets international social platforms (YouTube, Reddit) and works with English-language queries and output. Multilingual support is on the roadmap but not available yet.

## Before you use this

**This tool is for reference and research purposes only.** The reports it generates are automated syntheses of public online discussions and do not constitute professional market research, legal advice, or investment guidance. Findings may be incomplete, biased by platform demographics, or influenced by the LLM's interpretation. Always validate insights against primary sources and your own judgment before making product or business decisions.

By using this tool, you agree to respect the terms of service and rate limits of YouTube, Reddit, and your LLM provider. The authors assume no liability for decisions made based on the output.

## License

MIT.

---

## 中文

User Insights 是一个跨平台市场情报流水线。输入一个研究问题，自动抓取 YouTube 和 Reddit，过滤广告和噪音，提取结构化信号，生成一份每条结论都有原句引用的分析报告——既捕捉那些声量大的模式，也不漏掉音量小但价值高的洞察。

### 快速开始

#### 安装为 Claude Code skill

```bash
cp SKILL.md ~/.claude/skills/user-insights/SKILL.md
```

说 **"run user-insights"**。首次运行时 agent 会检查环境，让你在对话里粘贴 API 密钥——一次性设置，密钥保存在 `~/.user-insights.env`。之后只需告诉它研究什么，全自动运行。

#### 命令行运行

```bash
pip install -e .
export ANTHROPIC_API_KEY="your-key-here"
export YOUTUBE_API_KEY="your-key-here"
export REDDIT_CLIENT_ID="your-id"
export REDDIT_CLIENT_SECRET="your-secret"
user-insights run --question "用户怎么看 AI 编程助手？"
```

### 前置条件

**本项目不提供任何 API 密钥，使用前需自行准备：**

| 服务 | 需要 | 获取方式 |
|---|---|---|
| LLM 供应商 | API key | Anthropic Console、OpenAI Platform 或兼容供应商 |
| YouTube Data API v3 | API key | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| Reddit API | Client ID + Client Secret | [Reddit App Preferences](https://www.reddit.com/prefs/apps) |

通过环境变量设置（默认读取 `ANTHROPIC_API_KEY`）。使用 OpenAI-compatible 供应商时，运行 `user-insights config` 配置 provider、base URL 和 model。

使用者须自行遵守所连接平台的用户协议和数据政策。

### 解决什么问题

User Insights 不只是"提到多少次"，它在每一层都做信号和噪音的分离：

- **过滤广告、软文和无关讨论**：语义主权边界在抓取前就拦截相邻但无关的话题，质量引擎再筛掉纯情绪发泄和低信息量的评论。
- **捕捉小而珍贵的信号**：那些音量型工具会漏掉的东西。一条从业者描述自己工作流断裂的 Reddit 评论，比五十条"好棒"更有价值。Pipeline 会保留这些 thin but valuable 的信号。
- **呈现用户真正在说的**，不是 KOL 或营销文案在说的。每一条结论都有原句引用和来源链接——来自一线用户对痛点、功能缺失、付费意愿的真实反馈。
- **避免被平庸共识淹没**。当最大声的声音盖过最敏锐的观察，Python 计算的频次和情感分布会让叙事保持诚实。

10–25 分钟出结果，60 秒扫完核心结论，有需要再往下钻。

### 什么问题最适合

这个工具读的是真实用户在社交平台上的发言，不是分析师的行业报告。**具体、有产品指向的问题**效果最好——要像用户之间聊的话题，而不是像咨询公司的调研提纲：

| 合适（具体） | 不合适（太泛） |
|---|---|
| "用户怎么看 Notion 的定价？" | "生产力软件的未来是什么？" |
| "为什么有人从 Ender 换到 Bambu Lab？" | "3D 打印市场有多大？" |
| "用户愿意为 AI 编程助手付费吗？" | "2026 年 AI 发展到什么阶段了？" |

好问题里通常有具体的产品名、用户行为、或痛点方向。如果你的问题听起来像是问市场分析师而不是翻 Reddit，那更适合直接问 ChatGPT 或 Gemini——它们在整合宏观行业叙事方面更强。这个工具做的是：捕捉没人提问时用户自发在说什么。

### 工作原理

```
问题 → 语义主权初始化 → 大脑路由 → 侦察 → 双平台抓取 → 质量过滤 → 信号提取 → 统计 → 合成 → 报告
```

- **语义主权**在抓取前定义边界，防止无关噪音污染
- **平台不对称是信息增量**：YouTube 反映用户期望，Reddit 反映实际摩擦，两者间的差距就是产品机会
- **Python 锁定事实，LLM 生成叙事**：数字不会造假，Execution Manifest 保证可审计

### 报告结构

```
Executive Answer（执行摘要）   ← 60 秒了解核心结论
Detailed Analysis（详细分析）   ← 市场格局 · 数据脉搏 · 期望 vs 现实
Strategic Recommendations（建议） ← 优先级排序，含理由和风险
Evidence & Methodology（证据）  ← 逐条引用来源 · 执行清单
```

Executive Answer 一个段落一个核心发现。

### 与其他方案的区别

- **抗噪音**：广告、软文、相邻话题噪音在多层过滤中被拦截——语义边界、质量启发式、LLM 自检。你读的是信号，不是水。
- **不丢小信号**：音量型工具追着最大声的人群跑。这里保留那条"我为什么取消订阅"的 Reddit 评论——因为真正的洞察往往藏在一句话里。
- **可溯源**：每条结论指向真实的 Reddit 评论或 YouTube 时间戳。来自一线用户对痛点、功能缺失、付费意愿的真实反馈。
- **平台不对称是信息增量**：YouTube ≠ Reddit。YouTube 读期望，Reddit 读现实——两者之间的差距就是产品机会。
- **可审计**：Execution Manifest 由 Python 生成，LLM 不可能编造数据。
- **领域无关**：SaaS、硬件、消费 App、开发者工具都能跑，换个 anchor 和 subreddit 就行。
- **目前仅支持英文**：Pipeline 面向国际社媒平台（YouTube、Reddit），目前输入和输出均为英文。多语言支持在规划中，尚未开放。

### 使用前请了解

**本工具仅供研究和参考。** 生成的报告是对公开网络讨论的自动化摘要，不构成专业市场研究、法律意见或投资建议。分析结果可能不完整、受平台用户画像偏差影响、或被 LLM 的理解偏差所左右。在做任何产品或商业决策前，务必结合一手来源和自身判断进行验证。

使用者须尊重 YouTube、Reddit 及 LLM 供应商的服务条款和速率限制。作者对基于本工具输出所做的任何决策不承担责任。

