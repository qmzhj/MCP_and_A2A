import os
import tempfile

os.environ["DEMO_DELAY_MS"] = "0"
os.environ["TRACE_REMOTE"] = "0"
os.environ["TRACE_LOG"] = os.path.join(tempfile.gettempdir(), "agent-protocol-lab-trace.jsonl")
