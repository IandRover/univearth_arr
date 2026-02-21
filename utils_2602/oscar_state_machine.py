"""
OSCAR State Machine Controller for Earth Observation.

Implements the five-state OSCAR (Operating System Control via State-Aware
Reasoning and Re-Planning) architecture:

    [Init → Observe] → [Observe → Plan] → [Plan → Execute]
        → [Execute → Observe] (loop with re-planning up to N times)
        → [Verify → Done]

Key OSCAR mechanisms:
1. Task-Driven Re-Planning: On execution failure, only the failing step
   is modified while successful parts are preserved.
2. Code-Centric Control: The agent's ONLY output to the GEE environment
   is executable Python code — no natural language actions.
"""

import re
from enum import Enum
from typing import Dict, Optional, Tuple

from utils_2511.execution import execute_code
from utils_2602.oscar_llm import OscarLLM
from utils_2602.oscar_memory import OscarMemory
from utils_2602.verify import (
    check_execution_success,
    format_physical_validation,
    should_replan,
)


class OscarState(Enum):
    INIT = "init"
    OBSERVE = "observe"
    PLAN = "plan"
    EXECUTE = "execute"
    OBSERVE_POST_EXEC = "observe_post_exec"
    REPLAN = "replan"
    ANSWER = "answer"
    VERIFY = "verify"
    DONE = "done"
    FAILED = "failed"


class OscarStateMachine:
    """
    OSCAR State Machine for Earth Observation tasks.

    Orchestrates the full trajectory:
      Init → Observe → Plan → Execute → Observe → (Re-Plan loop) → Verify → Done

    Args:
        code_llm: OscarLLM instance for code generation (Observe/Plan/Execute/Re-Plan)
        answer_llm: OscarLLM instance for answer classification and verification
        memory: OscarMemory instance for logging
        max_replan_attempts: Maximum re-planning attempts (default: 3)
        execution_timeout: Code execution timeout in seconds (default: 120)
        language: Programming language for code execution (default: "python")
    """

    def __init__(
        self,
        code_llm: OscarLLM,
        answer_llm: OscarLLM,
        memory: OscarMemory,
        max_replan_attempts: int = 3,
        execution_timeout: int = 120,
        language: str = "python",
    ):
        self.code_llm = code_llm
        self.answer_llm = answer_llm
        self.memory = memory
        self.max_replan = max_replan_attempts
        self.timeout = execution_timeout
        self.language = language

        self.state = OscarState.INIT
        self.replan_count = 0

        # Running context passed between states
        self.ctx: Dict = {}

    def run(self, info: dict) -> dict:
        """
        Execute the full OSCAR state machine for one question.

        Args:
            info: Dict with at least 'question' key.

        Returns:
            Dict with final results including 'answer', 'code', 'exec_msg', etc.
        """
        self.ctx = dict(info)
        self.state = OscarState.INIT
        self.replan_count = 0

        while self.state not in (OscarState.DONE, OscarState.FAILED):
            self._transition()

        return self.ctx

    def _transition(self):
        """Execute the current state and transition to the next."""

        if self.state == OscarState.INIT:
            self._do_init_observe()

        elif self.state == OscarState.PLAN:
            self._do_plan()

        elif self.state == OscarState.EXECUTE:
            self._do_execute()

        elif self.state == OscarState.OBSERVE_POST_EXEC:
            self._do_observe_post_exec()

        elif self.state == OscarState.REPLAN:
            self._do_replan()

        elif self.state == OscarState.ANSWER:
            self._do_answer()

        elif self.state == OscarState.VERIFY:
            self._do_verify()

        else:
            self.state = OscarState.FAILED

    # ------------------------------------------------------------------ #
    #  State Implementations                                               #
    # ------------------------------------------------------------------ #

    def _do_init_observe(self):
        """[Init → Observe]: Capture environment state."""
        result = self.code_llm.init_observe(self.ctx)
        self.ctx.update(result)
        self.memory.log_state("init_observe", result)
        self.state = OscarState.PLAN

    def _do_plan(self):
        """[Observe → Plan]: Generate structured action plan."""
        result = self.code_llm.plan(self.ctx)
        self.ctx.update(result)
        self.memory.log_state("plan", result)
        self.state = OscarState.EXECUTE

    def _do_execute(self):
        """[Plan → Execute]: Generate and run code."""
        code_result = self.code_llm.execute(self.ctx)

        if not code_result or not code_result.get("code"):
            # LLM failed to produce code
            self.ctx["code"] = None
            self.ctx["raw_code"] = code_result.get("raw_code", "")
            self.ctx["exec_msg"] = ""
            self.ctx["exec_stderr"] = "LLM failed to generate valid code."
            self.ctx["exec_returncode"] = 1
            self.memory.log_state(
                "execute",
                {
                    "raw_code": self.ctx.get("raw_code"),
                    "code": None,
                    "error": "No code generated",
                },
            )
            self.state = OscarState.OBSERVE_POST_EXEC
            return

        self.ctx.update(code_result)
        self.memory.log_state(
            "execute_codegen",
            {
                "raw_code": code_result.get("raw_code"),
                "code": code_result.get("code"),
            },
        )

        # Run the code
        exec_result = execute_code(
            code_result["code"],
            timeout=self.timeout,
            language=self.language,
        )
        self.ctx.update(exec_result)
        self.memory.log_state("execute_run", exec_result)
        self.state = OscarState.OBSERVE_POST_EXEC

    def _do_observe_post_exec(self):
        """[Execute → Observe]: Evaluate execution result and decide next state."""
        exec_returncode = self.ctx.get("exec_returncode", 1)
        exec_stderr = self.ctx.get("exec_stderr", "")
        exec_msg = self.ctx.get("exec_msg", "")

        need_replan, reason = should_replan(exec_returncode, exec_stderr, exec_msg)

        # Extract the self-reported answer from stdout for logging clarity
        detected_answer = None
        if exec_msg and exec_msg.strip():
            for line in reversed(exec_msg.strip().split("\n")[-5:]):
                line = line.strip()
                if line in ("A", "B", "C1", "C2", "C3", "D"):
                    detected_answer = line
                    break
                m = re.match(r"^(A|B|C1|C2|C3|D)\b", line)
                if m:
                    detected_answer = m.group(1)
                    break

        self.memory.log_state(
            "observe_post_exec",
            {
                "exec_returncode": exec_returncode,
                "detected_answer": detected_answer,
                "need_replan": need_replan,
                "replan_reason": reason,
                "replan_count": self.replan_count,
            },
        )

        if need_replan and self.replan_count < self.max_replan:
            self.ctx["replan_reason"] = reason
            self.state = OscarState.REPLAN
        else:
            self.state = OscarState.ANSWER

    def _do_replan(self):
        """[Observe → Re-Plan → Execute]: Targeted fix and re-execute."""
        self.replan_count += 1
        self.ctx["attempt_number"] = str(self.replan_count)
        self.ctx["max_attempts"] = str(self.max_replan)

        replan_result = self.code_llm.replan(self.ctx)

        if not replan_result or not replan_result.get("code"):
            # Re-plan failed to produce code — go straight to answer
            self.memory.log_state(
                "replan",
                {
                    "attempt": self.replan_count,
                    "error": "Re-plan failed to generate code",
                    "raw_code": replan_result.get("raw_code", ""),
                },
            )
            self.state = OscarState.ANSWER
            return

        self.ctx["code"] = replan_result["code"]
        self.ctx["raw_code"] = replan_result.get("raw_code", "")
        self.ctx["diagnosis"] = replan_result.get("diagnosis", "")
        self.memory.log_state(
            "replan",
            {
                "attempt": self.replan_count,
                "diagnosis": replan_result.get("diagnosis"),
                "code": replan_result["code"],
            },
        )

        # Re-execute the corrected code
        exec_result = execute_code(
            replan_result["code"],
            timeout=self.timeout,
            language=self.language,
        )
        self.ctx.update(exec_result)
        self.memory.log_state(
            "replan_execute",
            {
                "attempt": self.replan_count,
                **exec_result,
            },
        )

        # Back to observation
        self.state = OscarState.OBSERVE_POST_EXEC

    def _do_answer(self):
        """[Observe → Answer]: Classify execution output."""
        answer_result = self.answer_llm.generate_answer(self.ctx)
        self.ctx.update(answer_result)
        self.ctx["preliminary_answer"] = answer_result.get("answer", "D")
        self.memory.log_state("answer", answer_result)
        self.state = OscarState.VERIFY

    def _do_verify(self):
        """[Verify → Done]: Physical checks + LLM self-consistency verification."""
        # Step 1: Physical range validation
        physical_validation = format_physical_validation(
            self.ctx.get("exec_msg", ""),
            self.ctx.get("exec_stderr", ""),
            self.ctx.get("exec_returncode", 1),
            self.ctx.get("code", ""),
        )
        self.ctx["physical_validation"] = physical_validation

        # Step 2: LLM-based verification
        verify_result = self.answer_llm.verify(self.ctx)
        self.ctx.update(verify_result)

        # Determine final answer
        # If the verifier agrees with the preliminary answer, use it.
        # If the verifier disagrees, trust the verifier (it has more context).
        preliminary = self.ctx.get("preliminary_answer", "D")
        verified = verify_result.get("verified_answer")
        confidence = verify_result.get("confidence", "low")

        if verified and verified != preliminary:
            final_answer = verified
            answer_source = "verify_override"
        else:
            final_answer = preliminary
            answer_source = "preliminary"

        self.ctx["answer"] = final_answer
        self.ctx["answer_source"] = answer_source

        self.memory.log_state(
            "verify",
            {
                "physical_validation": physical_validation,
                "preliminary_answer": preliminary,
                "verified_answer": verified,
                "confidence": confidence,
                "final_answer": final_answer,
                "answer_source": answer_source,
            },
        )

        # Set summary
        self.memory.set_summary(
            {
                "final_answer": final_answer,
                "answer_source": answer_source,
                "confidence": confidence,
                "replan_attempts": self.replan_count,
                "total_states": len(self.memory.trajectory),
            }
        )

        self.state = OscarState.DONE
