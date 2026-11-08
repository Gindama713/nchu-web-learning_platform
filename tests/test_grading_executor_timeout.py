"""real_executor 的超时与进程组回归（#58 审查意见第 3 条）。

原实现先 readline() 读到 EOF 再 wait(timeout)：引擎挂起且不肯关 stdout 时
主线程永久阻塞，永远走不到超时分支。这里用一个 print 后 sleep 的子进程复现。
"""

import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.engines import grading as engine


class RealExecutorTimeoutTest(TestCase):
    def test_hung_process_with_open_stdout_is_killed(self):
        argv = [sys.executable, "-c",
                "import time; print('alive', flush=True); time.sleep(60)"]
        with TemporaryDirectory() as directory:
            started = time.monotonic()
            with self.assertRaises(engine.SandboxTimeout):
                engine.real_executor(argv, Path(directory), timeout=1, max_output=1_000_000)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 10, f"挂起进程未在合理时间内终止，耗时 {elapsed:.1f}s")

    def test_output_limit_still_raises(self):
        argv = [sys.executable, "-c",
                "for _ in range(100): print('x' * 200)"]
        with TemporaryDirectory() as directory, self.assertRaises(engine.SandboxOutputLimit):
            engine.real_executor(argv, Path(directory), timeout=20, max_output=100)

    def test_normal_output_is_returned(self):
        argv = [sys.executable, "-c", "print('hello')"]
        with TemporaryDirectory() as directory:
            output, code = engine.real_executor(argv, Path(directory), timeout=20, max_output=10_000)
        self.assertIn("hello", output)
        self.assertEqual(code, 0)
