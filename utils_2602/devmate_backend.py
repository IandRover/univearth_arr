"""
DevMate Backend - File-based exchange protocol for using DevMate as the LLM.

Instead of calling external APIs, the script writes prompts to files and waits
for DevMate (the VS Code AI assistant) to read them and write responses.

Exchange Protocol:
  1. Script writes  →  oscar_exchange/step_NNN_prompt.md
  2. Script prints  →  "[OSCAR] Waiting for DevMate response..."
  3. DevMate reads   →  oscar_exchange/step_NNN_prompt.md
  4. DevMate writes  →  oscar_exchange/step_NNN_response.md
  5. Script reads    →  oscar_exchange/step_NNN_response.md
  6. Script continues to next state

The exchange directory is auto-created per question:
  oscar_exchange/{unique_id}/step_001_prompt.md
  oscar_exchange/{unique_id}/step_001_response.md
  ...
"""

import os
import time
from typing import Optional


class DevMateBackend:
    """File-based LLM backend that uses DevMate as the AI provider."""

    def __init__(self, exchange_dir: str = "./oscar_exchange"):
        self.base_dir = exchange_dir
        self.session_dir = None
        self.step_counter = 0
        self.poll_interval = 2  # seconds between checks

    def start_session(self, unique_id: str):
        """Start a new exchange session for a question."""
        self.session_dir = os.path.join(self.base_dir, str(unique_id))
        os.makedirs(self.session_dir, exist_ok=True)
        self.step_counter = 0

    def call(self, system_prompt: str, user_prompt: str, state_name: str) -> str:
        """
        Write a prompt and wait for DevMate's response.

        Args:
            system_prompt: The system-level instruction.
            user_prompt: The user-level content.
            state_name: OSCAR state name (for display/logging).

        Returns:
            The response text written by DevMate.
        """
        self.step_counter += 1
        step_id = f"step_{self.step_counter:03d}_{state_name}"

        prompt_path = os.path.join(self.session_dir, f"{step_id}_prompt.md")
        response_path = os.path.join(self.session_dir, f"{step_id}_response.md")

        # Write the prompt file
        prompt_content = self._format_prompt(state_name, system_prompt, user_prompt)
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt_content)

        # Signal that we're waiting
        print(f"\n{'='*70}")
        print(f"[OSCAR] State: {state_name} (step {self.step_counter})")
        print(f"[OSCAR] Prompt written to: {prompt_path}")
        print(f"[OSCAR] Waiting for response at: {response_path}")
        print(f"{'='*70}\n")

        # Poll for response
        response = self._wait_for_response(response_path)
        print(f"[OSCAR] Response received for {state_name} ({len(response)} chars)")
        return response

    def _format_prompt(self, state_name: str, system_prompt: str, user_prompt: str) -> str:
        """Format the prompt as a readable Markdown file."""
        return (
            f"# OSCAR State: {state_name}\n\n"
            f"**Respond by creating the corresponding `_response.md` file "
            f"in the same directory.**\n\n"
            f"---\n\n"
            f"## System Prompt\n\n"
            f"{system_prompt}\n\n"
            f"---\n\n"
            f"## User Prompt\n\n"
            f"{user_prompt}\n"
        )

    def _wait_for_response(self, response_path: str) -> str:
        """Poll until the response file appears, then read it."""
        waited = 0
        while True:
            if os.path.exists(response_path):
                # Small delay to ensure file is fully written
                time.sleep(0.5)
                with open(response_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    return content

            time.sleep(self.poll_interval)
            waited += self.poll_interval
            if waited % 30 == 0:
                print(f"[OSCAR] Still waiting... ({waited}s elapsed). "
                      f"Write response to: {response_path}")
