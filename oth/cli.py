import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from .core.kernel import OTHKernel
from .core.runner import OTHRunner
from .core.skills import SkillAcquirer
from .core.secure_tokens import SecureTokenStore
from .core.pilot import PilotPlanner

@contextlib.contextmanager
def daemon_singleton(root: Path):
    pid_path = root / "data" / "oth-daemon.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    acquired = False
    while not acquired:
        try:
            with pid_path.open("x", encoding="utf-8") as handle:
                handle.write(str(pid))
            acquired = True
        except FileExistsError:
            try:
                existing_pid = int(pid_path.read_text(encoding="utf-8").strip())
                os.kill(existing_pid, 0)
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                try:
                    pid_path.unlink()
                except FileNotFoundError:
                    pass
            else:
                yield False
                return
    try:
        yield True
    finally:
        try:
            if pid_path.read_text(encoding="utf-8").strip() == str(pid):
                pid_path.unlink()
        except (FileNotFoundError, OSError):
            pass

ROOT = Path(__file__).resolve().parents[1]

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="oth")
    sub = parser.add_subparsers(dest="cmd", required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("--capability", required=True)
    submit.add_argument("--action", required=True)
    submit.add_argument("--message", default="")
    submit.add_argument("--prompt", default="")
    submit.add_argument("--risk", default="safe")
    submit.add_argument("--max-retries", type=int, default=0)

    run = sub.add_parser("run")
    run.add_argument("task_id")

    approve = sub.add_parser("approve")
    approve.add_argument("task_id")

    sub.add_parser("tasks")

    graph = sub.add_parser("graph")
    graph.add_argument("task_id")
    graph.add_argument("--depth", type=int, default=8)

    skill = sub.add_parser("skill")
    skill_sub = skill.add_subparsers(dest="skill_cmd", required=True)
    acquire = skill_sub.add_parser("acquire")
    acquire.add_argument("repo")
    acquire.add_argument("--ref")
    acquire.add_argument("--install", action="store_true")
    skill_sub.add_parser("list")
    sync = skill_sub.add_parser("sync")
    sync.add_argument("repo")

    daemon = sub.add_parser("daemon")
    daemon.add_argument("--interval", type=float, default=2.0)
    daemon.add_argument("--once", action="store_true")

    sub.add_parser("tools")
    sub.add_parser("agents")
    sub.add_parser("workforce")
    sub.add_parser("coverage")
    engineering = sub.add_parser("engineering")
    engineering_sub = engineering.add_subparsers(dest="engineering_cmd", required=True)
    engineering_scorecard = engineering_sub.add_parser("scorecard")
    engineering_scorecard.add_argument("--limit", type=int, default=20)

    mission = sub.add_parser("mission")
    mission_sub = mission.add_subparsers(dest="mission_cmd", required=True)
    mission_status = mission_sub.add_parser("status")
    mission_status.add_argument("mission_id")
    mission_resume = mission_sub.add_parser("resume")
    mission_resume.add_argument("mission_id")
    mission_resume.add_argument("--task-id", action="append")
    mission_resume.add_argument("--approve-external", action="store_true")
    opp = sub.add_parser("opportunities")
    opp_sub = opp.add_subparsers(dest="opp_cmd", required=True)
    opp_list = opp_sub.add_parser("list")
    opp_list.add_argument("--limit", type=int, default=20)
    opp_top = opp_sub.add_parser("top")
    opp_top.add_argument("--limit", type=int, default=20)
    blue = sub.add_parser("blueprints")
    blue.add_argument("--limit", type=int, default=20)
    builds = sub.add_parser("builds")
    builds.add_argument("--limit", type=int, default=20)
    qa = sub.add_parser("qa")
    qa.add_argument("--limit", type=int, default=20)
    promotions = sub.add_parser("promotions")
    promotions.add_argument("--limit", type=int, default=20)
    provisions = sub.add_parser("provisioning")
    provisions.add_argument("--limit", type=int, default=20)

    social = sub.add_parser("social")
    social_sub = social.add_subparsers(dest="social_cmd", required=True)
    social_setup = social_sub.add_parser("setup")
    social_setup.add_argument("--provider")
    social_onboard = social_sub.add_parser("onboard")
    social_onboard.add_argument("--provider")
    social_oauth_start = social_sub.add_parser("oauth-start")
    social_oauth_start.add_argument("provider")
    social_oauth_browser = social_sub.add_parser("oauth-browser")
    social_oauth_browser.add_argument("provider")
    social_oauth_status = social_sub.add_parser("oauth-status")
    social_oauth_listen = social_sub.add_parser("oauth-listen")
    social_oauth_listen.add_argument("provider")
    social_oauth_listen.add_argument("--state", required=True)
    social_oauth_listen.add_argument("--host", default="127.0.0.1")
    social_oauth_listen.add_argument("--port", type=int, required=True)
    social_oauth_listen.add_argument("--timeout", type=int, default=300)
    social_oauth_callback = social_sub.add_parser("oauth-callback")
    social_oauth_callback.add_argument("provider")
    social_oauth_callback.add_argument("--state", required=True)
    social_oauth_callback.add_argument("--code", required=True)
    social_probe = social_sub.add_parser("probe")
    social_probe.add_argument("provider")
    social_connect = social_sub.add_parser("connect")
    social_connect.add_argument("provider")
    social_connect.add_argument("--account", default="")
    social_sub.add_parser("status")
    social_sub.add_parser("doctor")
    social_prepare = social_sub.add_parser("prepare")
    social_prepare.add_argument("provider")
    social_prepare.add_argument("text")
    social_prepare.add_argument("--media-ref")
    social_prepare.add_argument("--media-required", action="store_true")
    social_prepare.add_argument("--title")
    social_prepare.add_argument("--description")
    social_autopilot = social_sub.add_parser("autopilot")
    social_autopilot.add_argument("--min-score", type=float, default=65)
    social_autopilot.add_argument("--max-new", type=int, default=1)
    social_autopilot.add_argument("--platforms", nargs="+")
    social_content = social_sub.add_parser("content")
    social_content_sub = social_content.add_subparsers(dest="content_cmd", required=True)
    content_draft = social_content_sub.add_parser("draft")
    content_draft.add_argument("market")
    content_draft.add_argument("offer")
    content_draft.add_argument("--pain", default="")
    content_draft.add_argument("--proof", default="")
    content_draft.add_argument("--cta", default="")
    content_draft.add_argument("--hook", default="")
    content_draft.add_argument("--pillar", default="acquisition")
    content_draft.add_argument("--platforms", nargs="+")
    content_draft.add_argument("--media-ref")
    content_draft.add_argument("--privacy-status", choices=["private", "unlisted", "public"], default="private")
    content_queue = social_content_sub.add_parser("queue")
    content_queue.add_argument("market")
    content_queue.add_argument("offer")
    content_queue.add_argument("--pain", default="")
    content_queue.add_argument("--proof", default="")
    content_queue.add_argument("--cta", default="")
    content_queue.add_argument("--hook", default="")
    content_queue.add_argument("--pillar", default="acquisition")
    content_queue.add_argument("--platforms", nargs="+")
    content_queue.add_argument("--media-ref")
    content_queue.add_argument("--privacy-status", choices=["private", "unlisted", "public"], default="private")
    social_content_sub.add_parser("list")
    social_analytics = social_sub.add_parser("analytics")
    social_analytics_sub = social_analytics.add_subparsers(dest="analytics_cmd", required=True)
    social_analytics_sub.add_parser("list")
    social_analytics_sub.add_parser("sync")
    analytics_fetch = social_analytics_sub.add_parser("fetch")
    analytics_fetch.add_argument("provider")
    analytics_fetch.add_argument("external_id")
    analytics_fetch.add_argument("--content-id", default="")
    analytics_fetch.add_argument("--campaign-id", default="")
    social_control = social_sub.add_parser("control")
    social_control_sub = social_control.add_subparsers(dest="control_cmd", required=True)
    social_control_sub.add_parser("status")
    social_control_sub.add_parser("attention")
    social_queue = social_sub.add_parser("queue")
    social_queue_sub = social_queue.add_subparsers(dest="queue_cmd", required=True)
    queue_list = social_queue_sub.add_parser("list")
    queue_list.add_argument("--status")
    queue_list.add_argument("--platform")
    queue_approve = social_queue_sub.add_parser("approve")
    queue_approve.add_argument("content_id")
    queue_schedule = social_queue_sub.add_parser("schedule")
    queue_schedule.add_argument("content_id")
    queue_schedule.add_argument("due_at")
    queue_media = social_queue_sub.add_parser("attach-media")
    queue_media.add_argument("content_id")
    queue_media.add_argument("media_ref")
    queue_reject = social_queue_sub.add_parser("reject")
    queue_reject.add_argument("content_id")
    queue_reject.add_argument("--reason", default="operator_rejected")
    queue_reconcile = social_queue_sub.add_parser("reconcile")
    social_lead = social_sub.add_parser("lead")
    social_lead_sub = social_lead.add_subparsers(dest="lead_cmd", required=True)
    lead_ingest = social_lead_sub.add_parser("ingest")
    lead_ingest.add_argument("platform")
    lead_ingest.add_argument("message")
    lead_ingest.add_argument("--external-id", default="")
    lead_ingest.add_argument("--name", default="")
    lead_ingest.add_argument("--handle", default="")
    lead_ingest.add_argument("--contact", default="")
    lead_ingest.add_argument("--consent", action="store_true")
    lead_ingest.add_argument("--content-id", default="")
    lead_ingest.add_argument("--campaign-id", default="")
    lead_list = social_lead_sub.add_parser("list")
    lead_list.add_argument("--status")
    lead_qualify = social_lead_sub.add_parser("qualify")
    lead_qualify.add_argument("lead_id")
    lead_convert = social_lead_sub.add_parser("convert")
    lead_convert.add_argument("lead_id")
    social_lead_sub.add_parser("summary")
    lead_followup = social_lead_sub.add_parser("followup")
    lead_followup.add_argument("lead_id")
    social_publish = social_sub.add_parser("publish")
    social_publish.add_argument("provider")
    social_publish.add_argument("text")
    social_publish.add_argument("--actor")
    social_opt = social_sub.add_parser("optimize")
    social_opt.add_argument("--platform")
    social_record = social_sub.add_parser("record")
    social_record.add_argument("platform")
    social_record.add_argument("content_id")
    social_record.add_argument("--hook", default="")
    social_record.add_argument("--format", default="")
    social_record.add_argument("--pillar", default="")
    social_record.add_argument("--impressions", type=float, default=0)
    social_record.add_argument("--engagements", type=float, default=0)
    social_record.add_argument("--qualified-leads", type=float, default=0)
    social_record.add_argument("--conversions", type=float, default=0)

    pilot = sub.add_parser("pilot")
    pilot.add_argument("instruction", nargs="+")

    memory = sub.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_cmd", required=True)
    memory_list = memory_sub.add_parser("list")
    memory_list.add_argument("--capability")

    production = sub.add_parser("production")
    production_sub = production.add_subparsers(dest="production_cmd", required=True)
    production_sub.add_parser("list")
    production_sub.add_parser("review")
    production_plan = production_sub.add_parser("plan")
    production_plan.add_argument("--brief-id")
    resolve = sub.add_parser("resolve")
    resolve_sub = resolve.add_subparsers(dest="resolve_cmd", required=True)
    resolve_sub.add_parser("status")
    resolve_sub.add_parser("launch")
    resolve_sub.add_parser("connect")
    resolve_sub.add_parser("render-status")
    resolve_project = resolve_sub.add_parser("prepare")
    resolve_project.add_argument("--campaign-id")
    resolve_render = resolve_sub.add_parser("render")
    resolve_render.add_argument("--campaign-id")
    media = sub.add_parser("media")
    media_sub = media.add_subparsers(dest="media_cmd", required=True)
    media_sub.add_parser("list")
    media_inspect = media_sub.add_parser("inspect")
    media_inspect.add_argument("media_ref")
    media_register = media_sub.add_parser("register")
    media_register.add_argument("media_ref")
    media_normalize = media_sub.add_parser("normalize")
    media_normalize.add_argument("media_ref")
    media_source = media_sub.add_parser("source-download")
    media_source.add_argument("url")
    media_transcribe = media_sub.add_parser("transcribe")
    media_transcribe.add_argument("media_ref")
    media_transcribe.add_argument("--model", default="large-v3-turbo")
    media_qa = media_sub.add_parser("qa")
    media_qa.add_argument("media_ref")
    media_qa.add_argument("--resolution", default="1080x1920")
    media_qa.add_argument("--max-duration", type=float)
    media_qa.add_argument("--min-duration", type=float)
    social_plan = social_sub.add_parser("plan")
    social_plan_sub = social_plan.add_subparsers(dest="plan_cmd", required=True)
    social_plan_sub.add_parser("preview")
    social_plan_sub.add_parser("run")
    social_autonomy = social_sub.add_parser("autonomy")
    social_autonomy_sub = social_autonomy.add_subparsers(dest="autonomy_cmd", required=True)
    social_autonomy_sub.add_parser("status")
    social_autonomy_sub.add_parser("tick")
    autonomy_command = social_autonomy_sub.add_parser("command")
    autonomy_command.add_argument("instruction", nargs="+")

    schedule = sub.add_parser("schedule")
    schedule_sub = schedule.add_subparsers(dest="schedule_cmd", required=True)
    schedule_sub.add_parser("list")
    sadd = schedule_sub.add_parser("add")
    sadd.add_argument("id")
    sadd.add_argument("--interval", type=float, required=True)
    sadd.add_argument("--capability", required=True)
    sadd.add_argument("--action", required=True)
    sadd.add_argument("--message", default="")
    sadd.add_argument("--prompt", default="")
    sadd.add_argument("--risk", default="safe")
    sadd.add_argument("--priority", type=int, default=50)

    args = parser.parse_args(argv)
    if args.cmd == "schedule":
        schedule_path = ROOT / "config" / "schedules.json"
        config = json.loads(schedule_path.read_text(encoding="utf-8"))
        if args.schedule_cmd == "list":
            print(json.dumps(config, indent=2))
        else:
            payload = {"prompt": args.prompt} if args.prompt else {"message": args.message}
            payload["risk"] = args.risk
            config.setdefault("schedules", []).append({
                "id": args.id,
                "enabled": True,
                "interval_seconds": args.interval,
                "capability": args.capability,
                "action": args.action,
                "payload": payload,
                "priority": args.priority
            })
            schedule_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            print(json.dumps(config["schedules"][-1], indent=2))
        return

    if args.cmd == "skill":
        manager = SkillAcquirer(ROOT)
        if args.skill_cmd == "sync":
            print(json.dumps(manager.sync(args.repo), indent=2))
            return
        if args.skill_cmd == "acquire":
            repo = manager.clone(args.repo, args.ref)
            entries = manager.scan(repo)
            for entry in entries:
                entry["source_url"] = args.repo
            manager.index(entries, ROOT / "data" / "skills-index.json")
            if args.install:
                for entry in entries:
                    manager.install(entry)
            print(json.dumps({"repo": str(repo), "skills": entries,
                               "installed": bool(args.install)}, indent=2))
        else:
            index = ROOT / "data" / "skills-index.json"
            print(index.read_text(encoding="utf-8") if index.exists()
                  else '{"skills": []}')
        return

    kernel = OTHKernel(ROOT)
    try:
        if args.cmd == "daemon":
            with daemon_singleton(ROOT) as acquired:
                if not acquired:
                    print("OTH daemon already running")
                    return
                runner = OTHRunner(kernel, args.interval)
                if args.once:
                    print(runner.run_once())
                else:
                    print("OTH daemon online")
                    runner.run_forever()
            return
        if args.cmd == "graph":
            print(json.dumps(
                kernel.db.task_graph(args.task_id, max(1, min(args.depth, 32))),
                indent=2,
            ))
            return
        if args.cmd == "tools":
            for tool in kernel.tools.discover():
                print(tool)
            return
        if args.cmd == "agents":
            for agent in kernel.registry.load_agents():
                print({
                    "id": agent.id,
                    "name": agent.name,
                    "capabilities": agent.capabilities,
                    "status": agent.status,
                    "health": kernel.db.agent_health(agent.id),
                })
            return
        if args.cmd == "workforce":
            print(json.dumps(kernel.workforce.status(kernel.db), indent=2))
            return
        if args.cmd == "coverage":
            print(json.dumps(kernel.workforce.coverage(kernel.db), indent=2))
            return
        if args.cmd == "engineering":
            if args.engineering_cmd == "scorecard":
                coverage = kernel.workforce.coverage(kernel.db)
                engineering = next(
                    item for item in coverage["capabilities"]
                    if item["capability"] == "engineering"
                )
                print(json.dumps(
                    [
                        dict(row)
                        for row in kernel.db.engineering_scorecard(
                            engineering["active_workers"],
                            args.limit,
                        )
                    ],
                    indent=2,
                ))
            return
        if args.cmd == "mission":
            if args.mission_cmd == "status":
                mission = kernel.missions.get(args.mission_id)
                if mission is None:
                    print(json.dumps({"status": "missing", "mission_id": args.mission_id}))
                else:
                    payload = dict(mission)
                    payload["graph"] = kernel.missions.graph_for_mission(args.mission_id, kernel.db.path)
                    print(json.dumps(payload, indent=2))
            else:
                print(json.dumps(
                    kernel.resume_mission(
                        args.mission_id,
                        task_ids=args.task_id,
                        approve_external=args.approve_external,
                    ),
                    indent=2,
                ))
            return
        if args.cmd == "opportunities":
            rows = (kernel.db.top_opportunities(args.limit)
                    if args.opp_cmd == "top"
                    else kernel.db.list_opportunities(args.limit))
            for row in rows:
                print(dict(row))
            return
        if args.cmd == "builds":
            for row in kernel.db.list_build_artifacts(args.limit):
                print(dict(row))
            return
        if args.cmd == "qa":
            for row in kernel.db.list_qa_results(args.limit):
                print(dict(row))
            return
        if args.cmd == "promotions":
            for row in kernel.db.list_promotion_results(args.limit):
                print(dict(row))
            return
        if args.cmd == "provisioning":
            print("Dependency provisioning is currently plan-only.")
            return
        if args.cmd == "social":
            if args.social_cmd == "oauth-start":
                task = kernel.submit("social-accounts", "oauth_start", {
                    "input": {"provider": args.provider}
                }, 72)
            elif args.social_cmd == "oauth-browser":
                task = kernel.submit("social-accounts", "oauth_browser", {
                    "input": {"provider": args.provider}
                }, 72)
            elif args.social_cmd == "oauth-status":
                task = kernel.submit("social-accounts", "oauth_status", {"input": {}}, 64)
            elif args.social_cmd == "oauth-listen":
                task = kernel.submit("social-accounts", "oauth_listen", {
                    "input": {
                        "provider": args.provider,
                        "state": args.state,
                        "host": args.host,
                        "port": args.port,
                        "timeout_seconds": args.timeout,
                    }
                }, 72)
            elif args.social_cmd == "oauth-callback":
                SecureTokenStore(ROOT).set(
                    f"oauth-code:{args.state}", {"code": args.code}
                )
                task = kernel.submit("social-accounts", "oauth_callback", {
                    "input": {"provider": args.provider, "state": args.state}
                }, 72)
            elif args.social_cmd in {"setup", "onboard"}:
                payload = {"input": {}}
                if args.provider:
                    payload["input"]["provider"] = args.provider
                action = "onboard" if args.social_cmd == "onboard" else "setup"
                task = kernel.submit("social-accounts", action, payload, 70)
            elif args.social_cmd == "probe":
                task = kernel.submit("social-accounts", "probe", {
                    "input": {"provider": args.provider}
                }, 72)
            elif args.social_cmd == "connect":
                task = kernel.submit("social-accounts", "connect", {
                    "input": {
                        "provider": args.provider,
                        "account_label": args.account,
                    }
                }, 70)
            elif args.social_cmd == "status":
                task = kernel.submit("social-accounts", "status", {"input": {}}, 70)
            elif args.social_cmd == "doctor":
                task = kernel.submit("social-actions", "doctor", {"input": {}}, 75)
            elif args.social_cmd == "autopilot":
                task = kernel.submit("social-autopilot", "run", {
                    "input": {
                        "min_score": args.min_score,
                        "max_new_campaigns": args.max_new,
                        "platforms": args.platforms,
                    }
                }, 74)
            elif args.social_cmd == "prepare":
                task = kernel.submit("social-actions", "prepare_publish", {
                    "input": {
                        "provider": args.provider,
                        "text": args.text,
                        "media_ref": args.media_ref,
                        "media_required": args.media_required,
                        "title": args.title,
                        "description": args.description,
                    }
                }, 72)
            elif args.social_cmd == "plan":
                action = "preview" if args.plan_cmd == "preview" else "plan"
                task = kernel.submit("social-planner", action, {"input": {}}, 63)
            elif args.social_cmd == "autonomy":
                if args.autonomy_cmd == "status":
                    action = "status"
                    payload = {"input": {}}
                elif args.autonomy_cmd == "command":
                    action = "command"
                    payload = {"input": {"instruction": " ".join(args.instruction)}}
                else:
                    action = "tick"
                    payload = {"input": {}}
                task = kernel.submit("social-autonomy", action, payload, 88)
            elif args.social_cmd == "analytics":
                if args.analytics_cmd == "list":
                    task = kernel.submit("social-analytics", "list", {"input": {}}, 63)
                elif args.analytics_cmd == "sync":
                    task = kernel.submit("social-analytics", "sync", {"input": {}}, 64)
                else:
                    task = kernel.submit("social-analytics", "fetch", {
                        "input": {
                            "platform": args.provider,
                            "external_id": args.external_id,
                            "content_id": args.content_id,
                            "campaign_id": args.campaign_id,
                        }
                    }, 64)
            elif args.social_cmd == "control":
                task = kernel.submit("social-control", args.control_cmd, {"input": {}}, 60)
            elif args.social_cmd == "queue":
                if args.queue_cmd == "list":
                    task = kernel.submit("social-queue", "list", {
                        "input": {"status": args.status, "platform": args.platform}
                    }, 70)
                elif args.queue_cmd == "approve":
                    task = kernel.submit("social-queue", "approve", {
                        "input": {"content_id": args.content_id, "approved_by": "operator"}
                    }, 75)
                elif args.queue_cmd == "schedule":
                    task = kernel.submit("social-queue", "schedule", {
                        "input": {"content_id": args.content_id, "due_at": args.due_at}
                    }, 72)
                elif args.queue_cmd == "attach-media":
                    task = kernel.submit("social-queue", "attach_media", {
                        "input": {"content_id": args.content_id, "media_ref": args.media_ref}
                    }, 72)
                elif args.queue_cmd == "reject":
                    task = kernel.submit("social-queue", "reject", {
                        "input": {"content_id": args.content_id, "reason": args.reason}
                    }, 75)
                else:
                    task = kernel.submit("social-queue", "reconcile", {"input": {}}, 76)
            elif args.social_cmd == "content":
                if args.content_cmd == "list":
                    task = kernel.submit("social-content", "list", {"input": {}}, 65)
                else:
                    task = kernel.submit("social-content", args.content_cmd, {
                        "input": {
                            "market": args.market,
                            "offer": args.offer,
                            "pain": args.pain,
                            "proof": args.proof,
                            "cta": args.cta,
                            "hook": args.hook,
                            "pillar": args.pillar,
                            "platforms": args.platforms,
                            "media_ref": args.media_ref,
                            "privacy_status": args.privacy_status,
                        }
                    }, 70)
            elif args.social_cmd == "lead":
                if args.lead_cmd == "ingest":
                    task = kernel.submit("social-leads", "ingest", {
                        "input": {
                            "platform": args.platform,
                            "message": args.message,
                            "external_id": args.external_id,
                            "name": args.name,
                            "handle": args.handle,
                            "contact": args.contact,
                            "consent": args.consent,
                            "content_id": args.content_id,
                            "campaign_id": args.campaign_id,
                        }
                    }, 68)
                elif args.lead_cmd == "list":
                    task = kernel.submit("social-leads", "list", {
                        "input": {"status": args.status}
                    }, 65)
                elif args.lead_cmd in {"qualify", "convert"}:
                    task = kernel.submit("social-leads", args.lead_cmd, {
                        "input": {"lead_id": args.lead_id}
                    }, 67)
                elif args.lead_cmd == "summary":
                    task = kernel.submit("social-leads", "summary", {"input": {}}, 65)
                else:
                    task = kernel.submit("social-leads", "followup_draft", {
                        "input": {"lead_id": args.lead_id}
                    }, 67)
            elif args.social_cmd == "publish":
                task = kernel.submit("social-actions", "publish_text", {
                    "input": {
                        "provider": args.provider,
                        "text": args.text,
                        "actor": args.actor,
                    }
                }, 75)
            elif args.social_cmd == "optimize":
                task = kernel.submit("social-optimization", "optimize", {
                    "input": {"platform": args.platform}
                }, 65)
            else:
                task = kernel.submit("social-optimization", "record", {
                    "input": {
                        "platform": args.platform,
                        "content_id": args.content_id,
                        "hook": args.hook,
                        "format": args.format,
                        "pillar": args.pillar,
                        "metrics": {
                            "impressions": args.impressions,
                            "engagements": args.engagements,
                            "qualified_leads": args.qualified_leads,
                            "conversions": args.conversions,
                        },
                    }
                }, 65)
            print(json.dumps(kernel.dispatch(task.id), indent=2))
            return
        if args.cmd == "media":
            if args.media_cmd == "list":
                task = kernel.submit("media-assets", "list", {"input": {}}, 65)
            elif args.media_cmd == "source-download":
                task = kernel.submit("media-ingest", "download", {
                    "input": {"url": args.url}
                }, 66)
            elif args.media_cmd == "transcribe":
                task = kernel.submit("media-transcription", "transcribe", {
                    "input": {"media_ref": args.media_ref, "model": args.model}
                }, 72)
            elif args.media_cmd == "qa":
                task = kernel.submit("media-qa", "check", {
                    "input": {
                        "media_ref": args.media_ref,
                        "resolution": args.resolution,
                        "max_duration_seconds": args.max_duration,
                        "min_duration_seconds": args.min_duration,
                    }
                }, 75)
            else:
                task = kernel.submit("media-assets", args.media_cmd, {
                    "input": {"media_ref": args.media_ref}
                }, 68)
            print(json.dumps(kernel.dispatch(task.id), indent=2))
            return
        if args.cmd == "pilot":
            planner = PilotPlanner()
            result = planner.submit(kernel, " ".join(args.instruction))
            runner = OTHRunner(kernel, interval=0.05)
            executions = []
            for _ in range(min(4, max(1, result["task_count"]))):
                step = runner.run_once()
                if step is None:
                    break
                executions.append(step)
            print(json.dumps({**result, "executions": executions}, indent=2))
            return
        if args.cmd == "production":
            if args.production_cmd == "list":
                task = kernel.submit("media-production", "list", {"input": {}}, 65)
            elif args.production_cmd == "review":
                task = kernel.submit("media-production", "review", {"input": {}}, 65)
            else:
                task = kernel.submit("media-production", "plan", {
                    "input": {"briefs": [] if not args.brief_id else [{"brief_id": args.brief_id}]}
                }, 68)
            print(json.dumps(kernel.dispatch(task.id), indent=2))
            return
        if args.cmd == "resolve":
            if args.resolve_cmd == "status":
                action = "status"
            elif args.resolve_cmd == "launch":
                action = "launch"
            elif args.resolve_cmd == "connect":
                action = "connect"
            elif args.resolve_cmd == "render-status":
                action = "render_status"
            elif args.resolve_cmd == "render":
                action = "render"
            else:
                action = "prepare_project"
            task = kernel.submit("resolve-bridge", action, {"input": {"campaign_id": getattr(args, "campaign_id", None)}}, 68)
            print(json.dumps(kernel.dispatch(task.id), indent=2))
            return
        if args.cmd == "blueprints":
            for row in kernel.db.list_blueprints(args.limit):
                print(dict(row))
            return
        if args.cmd == "memory":
            rows = kernel.db.recent_memories(args.capability, 20)
            for row in rows:
                print(dict(row))
            return
        if args.cmd == "approve":
            print(kernel.approve(args.task_id))
            return
        if args.cmd == "submit":
            payload = {"prompt": args.prompt} if args.prompt else {"message": args.message}
            payload["risk"] = args.risk
            payload["max_retries"] = args.max_retries
            task = kernel.submit(args.capability, args.action, payload)
            print(task.id)
        elif args.cmd == "run":
            print(kernel.dispatch(args.task_id))
        else:
            for task in kernel.tasks():
                print(task)
    finally:
        kernel.close()

if __name__ == "__main__":
    main()
