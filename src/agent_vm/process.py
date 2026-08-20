from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .errors import AgentVMError


@dataclass
class Runner:
    dry_run: bool = False
    verbose: bool = False

    def run(
        self,
        args: Iterable[str],
        *,
        check: bool = True,
        capture: bool = False,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        sensitive: bool = False,
        stdin: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(value) for value in args]
        if self.verbose:
            rendered = "<redacted command>" if sensitive else shlex.join(command)
            print(f"+ {rendered}")
        if self.dry_run:
            return subprocess.CompletedProcess(command, 0, "", "")
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            return subprocess.run(
                command,
                check=check,
                text=True,
                capture_output=capture,
                cwd=cwd,
                env=merged_env,
                input=stdin,
            )
        except FileNotFoundError as exc:
            raise AgentVMError(f"Required command not found: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            suffix = f": {detail}" if detail and not sensitive else ""
            raise AgentVMError(f"Command failed ({exc.returncode}): {command[0]}{suffix}") from exc
