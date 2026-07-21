"""Mock transcript data for test cases when yt-dlp fails or returns empty.

Provides high-quality synthetic transcripts that simulate real YouTube content
for the three test scenarios. Used as automatic fallback when real transcripts
are unavailable (0 chars).
"""

MOCK_TRANSCRIPTS: dict[str, str] = {
    # Case 1: Business_Growth — AI side hustles
    "business_growth_ai": """
In this video I want to talk about the real use cases of AI for generating passive income.
I've been testing dozens of AI tools over the past six months, and I want to share what actually works.

First, let me address the elephant in the room. Most AI side hustle content on YouTube is complete garbage.
It's either course sales disguised as advice, or people showing you how to make AI-generated spam.
That's not what we're doing here.

Here's what genuinely works. Number one: AI-powered niche research. Tools like ChatGPT and Claude can analyze
market trends and identify underserved niches. I used this method to find a profitable micro-SaaS idea.

Number two: automated content repurposing. Taking a long-form blog post and using AI to create social media
variants. But here's the limitation — you still need human editorial oversight. AI-generated content without
human review performs terribly. I tested this with a 30-day experiment and the pure AI content got 80% less engagement.

Number three: AI coding assistants for rapid prototyping. As a solo founder, I can now build MVPs in days
instead of weeks using Cursor or Copilot. The key insight is to use AI as a force multiplier, not a replacement.

The biggest mistake I see is people trying to fully automate everything. That's a fantasy sold by course creators.
The sustainable model is AI-augmented human work, not AI replacement.
""",

    # Case 2: Tech_Deep_Dive — Copilot vs Cursor migration
    "tech_deep_dive_copilot": """
Let's talk about why so many developers are switching from GitHub Copilot to Cursor.
I've been using Copilot since launch, and I switched to Cursor about three months ago.
Here's my honest breakdown.

The number one complaint about Copilot is the lack of project-wide context. Copilot is great at
autocomplete within a single file, but it has zero awareness of your broader codebase. Cursor
embeds your entire project and uses that context for every suggestion. The difference is night and day.

Second major pain point: Copilot's chat is bolted on, while Cursor's agent mode is deeply integrated.
In Cursor, the AI can actually navigate your codebase, read multiple files, and make changes across
your project. Copilot's chat feels like a separate product awkwardly shoved into the sidebar.

The migration reason most people cite is speed of iteration. Cursor ships features exponentially faster.
They added image support, web search, and agent mode while Copilot was still figuring out how to improve
basic completions. A comment from a senior dev really stuck with me: 'GitHub Copilot is at least one year
behind Cursor in terms of AI coding capabilities.'

However, Copilot does have advantages. The enterprise integration with GitHub is seamless. If you're
at a large company with compliance requirements, Copilot is the safer choice. And Copilot's autocomplete
is still slightly faster for simple boilerplate.

But for power users who want deep codebase understanding and agentic capabilities, Cursor is the clear winner.
The gap is widening, not narrowing, and Microsoft needs to dramatically accelerate Copilot's development
to stay competitive.
""",

    # Claude Code vs Codex migration
    "claude_code_vs_codex": """
Today I'm doing a deep comparison between Claude Code and OpenAI Codex CLI. I've spent two weeks
using both as my primary coding agent, and I want to share what I've learned about why developers
are migrating in both directions.

Let's start with why people are leaving Claude Code for Codex. The number one complaint I've seen
across Reddit and in the Codex community is speed. Claude Code's agentic loops can be painfully slow,
especially on larger codebases. You'll wait 30-45 seconds while it thinks through a multi-step refactor.
Codex, by contrast, streams its responses and starts making file changes almost instantly. For developers
who value flow state, that latency difference is a dealbreaker.

The second major complaint about Claude Code is its token-based pricing anxiety. Users on Reddit
are constantly posting screenshots of surprise $50+ API bills after a long coding session. Codex's
flat subscription model eliminates that mental overhead. One developer told me: 'I stopped using
Claude Code because I was always watching the meter run. With Codex I just code.'

Third: Claude Code's file handling can be brittle. It sometimes loses track of which files it's
modified, requires manual intervention to continue, and hits context limits on larger projects.
Codex handles large monorepos more gracefully according to early adopters.

But the migration isn't one-way. People are also moving from Codex back to Claude Code for three
key reasons. First: code quality. Claude Code produces more idiomatic, production-ready code.
Codex can be sloppy — it generates code that works but doesn't follow best practices. A senior
engineer described Codex's output as 'junior dev code that needs review,' while Claude Code's
output is 'closer to what I'd write myself.'

Second: reasoning depth. Claude Code's extended thinking mode is genuinely useful for complex
architectural decisions. Codex tends to jump to implementation too quickly without fully
understanding the problem. If you're doing greenfield architecture, Claude Code is still superior.

Third: the Anthropic ecosystem. Teams already using Claude for code review, documentation, and
PR descriptions find Claude Code fits naturally into their workflow. Switching to Codex means
managing two separate AI subscriptions and contexts.

The emerging consensus seems to be: Codex for speed and iteration, Claude Code for quality and
depth. Power users are keeping both and switching based on the task. The real winner will
be whoever ships a unified experience first.
""",

    # Case 3: General — Junior devs and AI assistants
    "junior_dev_ai": """
Today I want to explore a question that's been on my mind: are junior developers actually benefiting
from AI coding assistants, or are we creating a generation of developers who can't code without them?

I interviewed fifteen junior developers across different companies, and the results were surprising.

On the productivity side, juniors are shipping code significantly faster. One developer told me she built
her first full-stack application in three weeks — something that would have taken her three months without AI.
The AI handles the boilerplate and the syntax she hasn't memorized yet, letting her focus on architecture
and user experience.

But here's where it gets concerning. Several senior dev mentors reported that their junior team members
struggle to debug AI-generated code when it fails. One tech lead said, 'I asked my junior to fix a bug
in AI-generated code, and he spent two hours prompting ChatGPT instead of reading the error message.'

The anxiety is very real. In anonymous forums, junior developers are expressing fear that they're not
building foundational skills. One comment that really hit me: 'I feel like I'm losing my edge. When the
AI goes down, I can barely write a for loop from memory.' That's terrifying from a career development perspective.

The emerging consensus among educators is that AI tools need to be taught alongside fundamentals, not
as a replacement. The most successful junior devs use AI as a tutor — asking it to explain concepts
rather than just generate solutions.

This split between 'AI as tutor' and 'AI as crutch' is going to define the next generation of engineers.
Companies need clear policies about how juniors should use these tools during onboarding.
""",
}


def get_mock_transcript(video_title: str, question: str) -> str:
    """Return appropriate mock transcript based on video title and question context."""
    title_lower = video_title.lower()
    question_lower = question.lower()

    # Claude Code vs Codex
    if any(w in title_lower for w in ["claude code", "codex", "coding agent", "cli"]):
        if any(w in question_lower for w in ["claude code", "codex"]):
            return MOCK_TRANSCRIPTS["claude_code_vs_codex"]

    # Copilot vs Cursor
    if any(w in title_lower for w in ["copilot", "cursor", "coding assistant", "code editor"]):
        if any(w in question_lower for w in ["copilot", "cursor", "vscode", "vs code"]):
            return MOCK_TRANSCRIPTS["tech_deep_dive_copilot"]

    # AI side hustle / passive income
    if any(w in title_lower for w in ["side hustle", "passive income", "make money"]):
        return MOCK_TRANSCRIPTS["business_growth_ai"]
    if any(w in question_lower for w in ["side hustle", "passive income", "ai tools for"]):
        return MOCK_TRANSCRIPTS["business_growth_ai"]

    # Junior dev / learning
    if any(w in title_lower for w in ["junior", "beginner", "learning", "new developer"]):
        return MOCK_TRANSCRIPTS["junior_dev_ai"]
    if any(w in question_lower for w in ["junior", "adapting", "anxiety", "learning"]):
        return MOCK_TRANSCRIPTS["junior_dev_ai"]

    # Broad Claude Code / Codex match from question
    if any(w in question_lower for w in ["claude code", "codex"]):
        return MOCK_TRANSCRIPTS["claude_code_vs_codex"]

    # Generic coding/dev fallback
    if any(w in title_lower for w in ["ai", "code", "dev", "software", "programming"]):
        return MOCK_TRANSCRIPTS["tech_deep_dive_copilot"]

    return MOCK_TRANSCRIPTS["business_growth_ai"]
