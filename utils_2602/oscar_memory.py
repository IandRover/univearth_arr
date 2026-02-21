"""
OSCAR Memory - Structured storage for OSCAR state machine execution history.

Logs every state transition so the full trajectory is preserved for analysis:
  Init → Observe → Plan → Execute → (Re-Plan loop) → Verify → Done
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class OscarMemory:
    """Memory structure for a single OSCAR execution trajectory."""

    def __init__(self, args, item: dict):
        self.save_dir = args.save_dir
        self.unique_id = item["UID"]
        self.file_path = os.path.join(self.save_dir, f"memory_{self.unique_id}.json")

        self.metadata = {
            "question": item["question"],
            "answer": item["answer"],
            "strategy": args.strategy,
            "code_llm": args.code_llm,
            "answer_llm": args.answer_llm,
            "language": args.language,
            "max_replan_attempts": args.max_replan_attempts,
            "suffix": args.suffix,
            "timestamp": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
            "url": item["URL"],
            "unique_id": item["UID"],
        }

        # State transition log — ordered list of state entries
        self.trajectory: List[Dict[str, Any]] = []
        # Summary data for quick access
        self.summary: Dict[str, Any] = {}

    def exists(self) -> bool:
        return os.path.exists(self.file_path)

    def log_state(self, state: str, data: Dict[str, Any]):
        """Log a state transition with its data.

        Args:
            state: One of 'init_observe', 'plan', 'execute', 'observe_post_exec',
                   'replan', 'answer', 'verify', 'done'
            data: State-specific data dict
        """
        entry = {
            "state": state,
            "timestamp": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
            "data": data,
        }
        self.trajectory.append(entry)

    def set_summary(self, summary: Dict[str, Any]):
        """Set the final summary for this execution."""
        self.summary = summary

    def save(self):
        """Persist to disk."""
        result = {
            "metadata": self.metadata,
            "trajectory": self.trajectory,
            "summary": self.summary,
        }
        with open(self.file_path, "w") as f:
            json.dump(result, f, indent=4)

    def load(self, file_path: Optional[str] = None):
        """Load from disk."""
        path = file_path or self.file_path
        with open(path, "r") as f:
            data = json.load(f)
        self.metadata = data["metadata"]
        self.trajectory = data.get("trajectory", [])
        self.summary = data.get("summary", {})

    @property
    def num_replan_attempts(self) -> int:
        """Count how many re-plan attempts have been made."""
        return sum(1 for t in self.trajectory if t["state"] == "replan")

    @property
    def final_answer(self) -> Optional[str]:
        """Get the final answer from summary."""
        return self.summary.get("final_answer")

    def get_states(self, state_name: str) -> List[Dict]:
        """Get all entries for a given state."""
        return [t for t in self.trajectory if t["state"] == state_name]
