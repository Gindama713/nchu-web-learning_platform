"""Linux process isolation: only trusted runtime, current task and pinned JAR are mounted."""

import math
import os
import shutil
from pathlib import Path

from backend.engines.grading import real_executor


def bubblewrap_executor(argv, cwd, timeout, max_output, cancel_event=None):
    if os.name != "posix" or not shutil.which("bwrap"):
        raise RuntimeError("Linux bubblewrap is required for isolated grading")
    cwd = Path(cwd).resolve()
    cwd.chmod(0o755)
    java = shutil.which(argv[0])
    if not java:
        raise RuntimeError("Java is not available in PATH")
    java_home = Path(java).resolve().parent.parent
    command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
               "--uid", "65534", "--gid", "65534", "--clearenv", "--setenv", "PATH", "/usr/bin:/bin",
               "--setenv", "LANG", "C.UTF-8", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for path in ("/usr", "/bin", "/lib", "/lib64", "/etc/alternatives", "/etc/java-21-openjdk", "/etc/fonts"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    command += ["--ro-bind", str(cwd), "/work", "--dir", "/engine", "--ro-bind", str(java_home), "/engine/jre", "--ro-bind", str(Path(argv[3]).resolve()),
                "/engine/logisim.jar", "--chdir", "/work"]
    rewritten = ["/engine/jre/bin/java", argv[1], "-XX:ActiveProcessorCount=1", "-Duser.home=/tmp"]
    for argument in argv[2:]:
        if argument == argv[3]:
            rewritten.append("/engine/logisim.jar")
        elif str(argument).startswith(str(cwd) + "/"):
            rewritten.append("/work/" + Path(argument).name)
        else:
            rewritten.append(str(argument))
    # CPU time is enforced by the OS; heap cap remains -Xmx, not a claim of whole-process RSS.
    if shutil.which("prlimit"):
        command = ["prlimit", f"--cpu={math.ceil(timeout) + 1}", "--nofile=128", "--", *command]
    if hasattr(os, "sched_getaffinity") and shutil.which("taskset"):
        command = ["taskset", "-c", str(min(os.sched_getaffinity(0))), *command]
    # Private display INSIDE the namespace: no host X socket/authority is exposed.
    return real_executor([*command, "/usr/bin/xvfb-run", "-a", "-s", "-screen 0 1024x768x24 -nolisten tcp", *rewritten],
                         cwd, timeout, max_output, cancel_event=cancel_event)
