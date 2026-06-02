import json
import os

log_path = "/Users/Siddharth/.gemini/antigravity/brain/e291c032-60a9-4feb-81f9-b8ce562d37cd/.system_generated/logs/transcript.jsonl"
static_dir = "/Users/Siddharth/Documents/AiDincharya/src/static"

with open(log_path, "r") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "USER_INPUT":
                content = data.get("content", "")
                if "kirrthanaa is building the mobile app" in content:
                    # Extract HTML
                    idx = content.find("<!-- Design System -->")
                    if idx != -1:
                        html = content[idx:]
                        with open(os.path.join(static_dir, "index.html"), "w") as out:
                            out.write(html)
                if "most of it is missing" in content and "AI Architecture" in content:
                    idx = content.find("<!DOCTYPE html>")
                    if idx != -1:
                        html = content[idx:]
                        with open(os.path.join(static_dir, "architecture.html"), "w") as out:
                            out.write(html)
        except Exception as e:
            pass
