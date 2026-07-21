# User Insights — Market Research Skill

Run dual-platform (YouTube + Reddit) market research from a single question. Scrapes real user conversations, extracts structured signals, and produces an executive report with verbatim proof and strategic recommendations.

## When to use

Activate when the user says any of:
- "run user-insights"
- "research <topic>"
- "what do users think about <topic>?"
- "user insights <question>"

## First-time setup

On first run, check if the CLI is installed and API keys are available:

```bash
which user-insights 2>/dev/null && echo "CLI: OK" || echo "CLI: MISSING"
cat ~/.user-insights.env 2>/dev/null || echo "KEYS: MISSING"
```

### If the CLI is not installed

Tell the user: "The user-insights CLI isn't installed yet. Run this and come back:"

```bash
pip install -e /path/to/user-insights
```

### If API keys are missing

Tell the user:

> Before running research, you'll need three API keys. You can paste them here in chat and I'll save them — one-time setup.
>
> 1. **LLM API key** — from [Anthropic Console](https://console.anthropic.com/) (or OpenAI-compatible provider)
> 2. **YouTube Data API key** — from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
> 3. **Reddit Client ID & Secret** — from [Reddit App Preferences](https://www.reddit.com/prefs/apps)
>
> Paste any of them and I'll save it.

When the user pastes a key, identify which one it is and write it to `~/.user-insights.env`:

```bash
# Example — replace with actual key values the user provides
echo 'export ANTHROPIC_API_KEY="sk-..."' >> ~/.user-insights.env
echo 'export YOUTUBE_API_KEY="AIza..."' >> ~/.user-insights.env
```

For Reddit credentials, write them to the project config or instruct the user to set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` as env vars.

Once all three are saved, tell the user setup is complete and ask: **"What would you like to research?"**

## How it works

1. Ask the user: **"What would you like to research?"**
2. Source the keys and run the pipeline:

```bash
source ~/.user-insights.env 2>/dev/null
user-insights run --question "<the user's research question>"
```

3. The pipeline scrapes YouTube and Reddit (10–25 min), then outputs a full report.
4. Summarize the Executive Answer section for the user. Mention the full report is available.

## Notes

- The pipeline takes 10–25 minutes. Tell the user it's running.
- Trust the Executive Answer for a quick read; Detailed Analysis and Evidence sections for depth.
- Every finding links to a verbatim quote and source URL — cite these when the user asks "where did this come from?"
