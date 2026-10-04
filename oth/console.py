import json
import os
import re
import sqlite3
import subprocess
import uuid
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core.console_store import ConsoleStore
from .core.pilot import PilotPlanner
from .core.kernel import OTHKernel

ROOT = Path(__file__).resolve().parents[1]
STORE = ConsoleStore(ROOT / "data" / "console.db")
WEB_ROOT = ROOT / "console"

def model_config():
    base = os.getenv("OTH_MODEL_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("OTH_MODEL_API_KEY", "")
    name = os.getenv("OTH_MODEL_NAME", "").strip()
    if not base:
        try:
            proc = subprocess.run(
                [
                    "wsl.exe", "-d", "Arch", "--", "bash", "-lc",
                    "ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            ip = next(
                (
                    line.strip()
                    for line in proc.stdout.splitlines()
                    if re.fullmatch(r"\d+(?:\.\d+){3}", line.strip())
                ),
                "",
            )
            if ip:
                base = f"http://{ip}:11434/v1"
        except Exception:
            pass
    if not base:
        base = "http://127.0.0.1:11434/v1"
    if not name:
        name = "auto"
    return base, key, name

def call_model(messages):
    base, key, name = model_config()
    if name == "auto":
        models_url = base + "/models"
        try:
            req = urllib.request.Request(models_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [item.get("id") for item in data.get("data", []) if item.get("id")]
            if not models:
                return None
            name = models[0]
        except Exception:
            return None
    payload = json.dumps({
        "model": name,
        "messages": messages,
        "temperature": 0.2,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        req = urllib.request.Request(base + "/chat/completions", data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None

MISSION_PREFIXES = (
    "build ", "create ", "implement ", "develop ", "fix ", "repair ",
    "set up ", "setup ", "configure ", "continue ", "run ", "deploy ",
    "automate ", "design ", "make ", "add ", "remove ", "refactor ",
    "execute ", "finish ", "work on ",
)

EXECUTE_EXISTING = (
    "execute the mission",
    "execute mission",
    "do the mission",
    "continue the mission",
    "continue with the mission",
    "finish the mission",
)

def is_mission(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(MISSION_PREFIXES) or lowered in EXECUTE_EXISTING

def resolve_mission(conversation_id: str, text: str) -> str:
    lowered = text.strip().lower()
    if lowered not in EXECUTE_EXISTING:
        return text.strip()
    history = STORE.messages(conversation_id, 80)
    for item in reversed(history):
        if item["role"] != "user":
            continue
        candidate = item["content"].strip()
        if candidate and candidate.lower() not in EXECUTE_EXISTING:
            return candidate
    return text.strip()

def queue_mission(text: str):
    kernel = OTHKernel(ROOT)
    try:
        planner = PilotPlanner()
        plan = planner.submit(kernel, text)
        return {
            "queued": True,
            "goal": plan["goal"],
            "strategy": plan["strategy"],
            "root_task_ids": plan["root_task_ids"],
            "task_count": plan["task_count"],
        }
    finally:
        kernel.close()

def pilot_fallback(text: str):
    planner = PilotPlanner()
    try:
        result = planner.plan(text)
        return (
            "OTH received the mission.\n\n"
            f"Goal: {result.goal}\n"
            f"Strategy: {result.strategy}\n"
            f"Tasks: {len(result.tasks)}"
        )
    except Exception:
        return (
            "OTH received and permanently stored this message. "
            "No model provider is configured yet; the local mission console is online."
        )

@contextmanager
def console_singleton():
    pid_path = ROOT / "data" / "oth-console.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    try:
        existing = int(pid_path.read_text(encoding="utf-8").strip())
        os.kill(existing, 0)
        yield False
        return
    except Exception:
        pass
    pid_path.write_text(str(pid), encoding="utf-8")
    try:
        yield True
    finally:
        try:
            if pid_path.read_text(encoding="utf-8").strip() == str(pid):
                pid_path.unlink()
        except OSError:
            pass

class Handler(BaseHTTPRequestHandler):
    server_version = "OTHConsole/0.1"

    def log_message(self, *_):
        return

    def json_response(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/status":
            base, _, name = model_config()
            self.json_response(200, {
                "ok": True,
                "console": "online",
                "storage": str(STORE.path),
                "model_base": base,
                "model": name,
                "stats": STORE.stats(),
            })
            return
        if self.path == "/api/conversations":
            self.json_response(200, {"items": STORE.list_conversations()})
            return
        if self.path.startswith("/api/conversations/") and self.path.endswith("/messages"):
            conversation_id = self.path.split("/")[3]
            self.json_response(200, {"items": STORE.messages(conversation_id)})
            return
        if self.path.startswith("/api/tasks/"):
            task_id = self.path.split("/")[3]
            db = sqlite3.connect(ROOT / "data" / "oth.db")
            db.row_factory = sqlite3.Row
            task = db.execute(
                "SELECT id, capability, action, status, priority, created_at, updated_at "
                "FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            event = db.execute(
                "SELECT kind, payload, created_at FROM events "
                "WHERE task_id=? ORDER BY rowid DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            db.close()
            if not task:
                self.json_response(404, {"error": "task not found"})
                return
            payload = {}
            if event:
                try:
                    payload = json.loads(event["payload"] or "{}")
                except Exception:
                    payload = {"raw": event["payload"]}
            self.json_response(200, {
                "task": dict(task),
                "latest_event": {
                    "kind": event["kind"],
                    "created_at": event["created_at"],
                    "payload": payload,
                } if event else None,
            })
            return
        if self.path == "/api/mission":
            mission_path = ROOT / "data" / "pilot_state.json"
            mission = json.loads(mission_path.read_text(encoding="utf-8")) if mission_path.exists() else {}
            self.json_response(200, mission)
            return
        if self.path in {"/", "/index.html"}:
            raw = (WEB_ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_error(404)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_POST(self):
        try:
            body = self.read_json()
        except Exception as exc:
            self.json_response(400, {"error": f"invalid json: {exc}"})
            return

        if self.path == "/api/conversations":
            conversation_id = str(uuid.uuid4())
            title = body.get("title") or "New Mission Chat"
            item = STORE.create_conversation(conversation_id, title)
            self.json_response(201, item)
            return

        if self.path.startswith("/api/conversations/") and self.path.endswith("/messages"):
            conversation_id = self.path.split("/")[3]
            text = str(body.get("content", "")).strip()
            if not text:
                self.json_response(400, {"error": "empty message"})
                return
            if not STORE.get_conversation(conversation_id):
                self.json_response(404, {"error": "conversation not found"})
                return

            STORE.add_message(conversation_id, "user", text)

            if is_mission(text):
                mission_text = resolve_mission(conversation_id, text)
                queued = queue_mission(mission_text)
                answer = (
                    "Mission queued into the OTH execution kernel.\n\n"
                    f"Goal: {queued['goal']}\n"
                    f"Strategy: {queued['strategy']}\n"
                    f"Root tasks: {', '.join(queued['root_task_ids'])}\n"
                    "The OTH daemon will execute the queued graph."
                )
                STORE.add_message(
                    conversation_id,
                    "assistant",
                    answer,
                    {"provider": "oth-kernel", "mission": queued},
                )
                self.json_response(200, {
                    "role": "assistant",
                    "content": answer,
                    "provider": "oth-kernel",
                    "mission": queued,
                })
                return

            context = STORE.context_for_model(conversation_id, text, recent=16, retrieved=8, memories=6)
            messages = [
                {"role": "system", "content":
                 "You are the OTH Pilot. The local OTH system is the durable source of truth. "
                 "Long conversation history is stored outside model context and selectively retrieved. "
                 "Use durable mission memory and relevant older conversation when supplied. "
                 "Be concise unless explicitly asked for detail. Never claim an action occurred unless it did."}
            ]
            messages.extend(context)
            answer = call_model(messages)
            provider = "model"
            if answer is None:
                answer = pilot_fallback(text)
                provider = "pilot-fallback"
            STORE.add_message(conversation_id, "assistant", answer, {"provider": provider})
            self.json_response(200, {"role": "assistant", "content": answer, "provider": provider})
            return

        self.json_response(404, {"error": "route not found"})

def main():
    host = os.getenv("OTH_CONSOLE_HOST", "127.0.0.1")
    port = int(os.getenv("OTH_CONSOLE_PORT", "18765"))
    with console_singleton() as acquired:
        if not acquired:
            print("OTH Console already running")
            return
        print(f"OTH Console online at http://{host}:{port}")
        ThreadingHTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__":
    main()
