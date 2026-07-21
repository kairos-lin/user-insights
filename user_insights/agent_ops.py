import json
import os
from datetime import datetime

from .models import Session, StepState


class AgentOps:
    def __init__(self, output_base: str):
        self.output_base = output_base
        self.session: Session | None = None

    def create_session(self, question: str, language: str) -> Session:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder = os.path.join(self.output_base, ts)
        os.makedirs(folder, exist_ok=True)
        self.session = Session(
            folder_path=folder,
            timestamp=ts,
            question=question,
            language=language,
        )
        self._init_steps()
        return self.session

    def _init_steps(self):
        for name in ["decompose", "scrape", "extract", "synthesize"]:
            self.session.steps[name] = StepState(name=name)

    def start_step(self, name: str, metadata: dict | None = None):
        step = self.session.steps.get(name)
        if not step:
            step = StepState(name=name)
            self.session.steps[name] = step
        step.status = "running"
        step.started_at = datetime.now().isoformat()
        if metadata:
            step.metadata.update(metadata)

    def finish_step(self, name: str, metadata: dict | None = None):
        step = self.session.steps[name]
        step.status = "done"
        step.finished_at = datetime.now().isoformat()
        if metadata:
            step.metadata.update(metadata)
        self.checkpoint()

    def fail_step(self, name: str, error: str):
        step = self.session.steps[name]
        step.status = "failed"
        step.error = error
        step.finished_at = datetime.now().isoformat()
        self.checkpoint()

    def checkpoint(self):
        if not self.session:
            return
        state = {
            "timestamp": self.session.timestamp,
            "question": self.session.question,
            "language": self.session.language,
            "folder_path": self.session.folder_path,
            "steps": {
                name: {
                    "name": s.name,
                    "status": s.status,
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                    "error": s.error,
                    "metadata": s.metadata,
                }
                for name, s in self.session.steps.items()
            },
            "resource_usage": self.session.resource_usage,
        }
        path = os.path.join(self.session.folder_path, "session_state.json")
        with open(path, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def resume_from(self, folder: str) -> int | None:
        state_path = os.path.join(folder, "session_state.json")
        if not os.path.exists(state_path):
            return None
        with open(state_path) as f:
            state = json.load(f)
        self.session = Session(
            folder_path=folder,
            timestamp=state["timestamp"],
            question=state["question"],
            language=state.get("language", "en"),
        )
        for name, s in state.get("steps", {}).items():
            self.session.steps[name] = StepState(**s)
        self.session.resource_usage = state.get("resource_usage", {})
        # Find first non-done step
        step_order = ["decompose", "scrape", "extract", "synthesize"]
        for i, name in enumerate(step_order):
            step = self.session.steps.get(name)
            if not step or step.status != "done":
                return i
        return len(step_order)  # all done

    def track_llm_call(self, tokens_used: int = 0):
        usage = self.session.resource_usage
        usage["llm_calls"] = usage.get("llm_calls", 0) + 1
        usage["tokens_estimated"] = usage.get("tokens_estimated", 0) + tokens_used

    def track_reddit_call(self):
        usage = self.session.resource_usage
        usage["reddit_calls"] = usage.get("reddit_calls", 0) + 1

    def summary(self) -> str:
        if not self.session:
            return "No session."
        u = self.session.resource_usage
        lines = [
            f"Session: {self.session.timestamp}",
            f"Question: {self.session.question[:80]}...",
            f"LLM calls: {u.get('llm_calls', 0)}",
            f"Tokens (est.): {u.get('tokens_estimated', 0)}",
            f"Reddit API calls: {u.get('reddit_calls', 0)}",
        ]
        return "\n".join(lines)

    def list_sessions(self) -> list[dict]:
        if not os.path.exists(self.output_base):
            return []
        results = []
        for name in sorted(os.listdir(self.output_base), reverse=True):
            folder = os.path.join(self.output_base, name)
            if not os.path.isdir(folder):
                continue
            state_path = os.path.join(folder, "session_state.json")
            if os.path.exists(state_path):
                with open(state_path) as f:
                    state = json.load(f)
                results.append({
                    "timestamp": state["timestamp"],
                    "question": state["question"][:100],
                    "folder": folder,
                    "steps_done": sum(
                        1 for s in state.get("steps", {}).values() if s["status"] == "done"
                    ),
                })
        return results
