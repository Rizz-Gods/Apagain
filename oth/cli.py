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

    daemon = sub.add_parser("daemon")
    daemon.add_argument("--interval", type=float, default=2.0)
    daemon.add_argument("--once", action="store_true")

    sub.add_parser("tools")

    args = parser.parse_args(argv)
    if args.cmd == "skill":
        manager = SkillAcquirer(ROOT)
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
        if args.cmd == "approve":
            print(kernel.approve(args.task_id))
            return
        if args.cmd == "submit":
            payload = {"prompt": args.prompt} if args.prompt else {"message": args.message}
            payload["risk"] = args.risk
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
