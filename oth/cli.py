import argparse
import json
from pathlib import Path

from .core.kernel import OTHKernel
from .core.runner import OTHRunner
from .core.skills import SkillAcquirer

ROOT = Path(__file__).resolve().parents[1]

def main(argv=None):
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
    social_connect = social_sub.add_parser("connect")
    social_connect.add_argument("provider")
    social_connect.add_argument("--account", default="")
    social_sub.add_parser("status")
    social_sub.add_parser("doctor")
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

    memory = sub.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_cmd", required=True)
    memory_list = memory_sub.add_parser("list")
    memory_list.add_argument("--capability")

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
            runner = OTHRunner(kernel, args.interval)
            if args.once:
                print(runner.run_once())
            else:
                print("OTH daemon online")
                runner.run_forever()
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
            if args.social_cmd == "setup":
                payload = {"input": {}}
                if args.provider:
                    payload["input"]["provider"] = args.provider
                task = kernel.submit("social-accounts", "setup", payload, 70)
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
