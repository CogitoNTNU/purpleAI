import os

# The authorized target. Overridable via the TARGET_URL env var so several
# isolated instances can each point at their own vulnerable-app port
# (8080, 8081, …) without editing code. Defaults to the lab's first app.
Target_url = os.environ.get("TARGET_URL", "http://192.168.0.120:8080/")
