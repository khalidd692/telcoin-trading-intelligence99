import sys
import json
import uuid
import os

def load_db(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                return []
    return []

def save_db(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def main():
    args = sys.argv[1:]
    if '--db' not in args:
        print('Usage: tasks.py --db PATH COMMAND ...', file=sys.stderr)
        sys.exit(1)
    db_index = args.index('--db')
    if db_index + 1 >= len(args):
        print('Missing db path', file=sys.stderr)
        sys.exit(1)
    db_path = args[db_index + 1]
    cmd_args = args[db_index + 2:]
    if not cmd_args:
        print('Missing command', file=sys.stderr)
        sys.exit(1)
    command = cmd_args[0]
    tasks = load_db(db_path)

    if command == 'add':
        if len(cmd_args) < 2:
            print('Usage: add TITLE', file=sys.stderr)
            sys.exit(1)
        title = ' '.join(cmd_args[1:])
        task = {'id': uuid.uuid4().hex, 'title': title, 'done': False}
        tasks.append(task)
        save_db(db_path, tasks)
        print(json.dumps(task, ensure_ascii=False))

    elif command == 'edit':
        if len(cmd_args) < 3:
            print('Usage: edit ID TITLE', file=sys.stderr)
            sys.exit(1)
        task_id = cmd_args[1]
        title = ' '.join(cmd_args[2:])
        for task in tasks:
            if task['id'] == task_id:
                task['title'] = title
                save_db(db_path, tasks)
                print(json.dumps(task, ensure_ascii=False))
                return
        print('Task not found', file=sys.stderr)
        sys.exit(1)

    elif command == 'complete':
        if len(cmd_args) < 2:
            print('Usage: complete ID', file=sys.stderr)
            sys.exit(1)
        task_id = cmd_args[1]
        for task in tasks:
            if task['id'] == task_id:
                task['done'] = True
                save_db(db_path, tasks)
                print(json.dumps(task, ensure_ascii=False))
                return
        print('Task not found', file=sys.stderr)
        sys.exit(1)

    elif command == 'delete':
        if len(cmd_args) < 2:
            print('Usage: delete ID', file=sys.stderr)
            sys.exit(1)
        task_id = cmd_args[1]
        for i, task in enumerate(tasks):
            if task['id'] == task_id:
                deleted = tasks.pop(i)
                save_db(db_path, tasks)
                print(json.dumps(deleted, ensure_ascii=False))
                return
        print('Task not found', file=sys.stderr)
        sys.exit(1)

    elif command == 'list':
        print(json.dumps(tasks, ensure_ascii=False))

    else:
        print(f'Unknown command: {command}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
