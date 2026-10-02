import argparse
from pathlib import Path
from .core.kernel import OTHKernel

ROOT = Path(__file__).resolve().parents[1]

def main(argv=None):
    parser = argparse.ArgumentParser(prog="oth")
    sub = parser.add_subparsers(dest="cmd", required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("--capability", required=True)
    submit.add_argument("--action", required=True)
    submit.add_argument("--message", default="")

    run = sub.add_parser("run")
    run.add_argument("task_id")

    sub.add_parser("tasks")
    args = parser.parse_args(argv)
    kernel = OTHKernel(ROOT)

    if args.cmd == "submit":
        task = kernel.submit(args.capability, args.action, {"message": args.message})
        print(task.id)
    elif args.cmd == "run":
        print(kernel.dispatch(args.task_id))
    else:
        for task in kernel.tasks():
            print(task)

if __name__ == "__main__":
    main()
