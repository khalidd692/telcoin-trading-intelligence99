"""Scripted test fixture for the native task-management contract."""

import argparse
import json
import pathlib
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=pathlib.Path, required=True)
    parser.add_argument("operation", choices=["add", "edit", "complete", "delete", "list"])
    parser.add_argument("values", nargs="*")
    args = parser.parse_args()
    tasks = json.loads(args.db.read_text()) if args.db.exists() else []
    if args.operation == "list":
        print(json.dumps(tasks))
        return
    if args.operation == "add":
        task = {"id": uuid.uuid4().hex, "title": args.values[0], "done": False}
        tasks.append(task)
    else:
        task = next(t for t in tasks if t["id"] == args.values[0])
        if args.operation == "edit":
            task["title"] = args.values[1]
        elif args.operation == "complete":
            task["done"] = True
        else:
            tasks.remove(task)
    args.db.write_text(json.dumps(tasks))
    print(json.dumps(task))


if __name__ == "__main__":
    main()
