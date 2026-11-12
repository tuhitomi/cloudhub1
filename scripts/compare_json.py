"""Exit 1 when two JSON files differ semantically (ignores formatting and line endings)."""
import json
import sys


def main(left, right):
    with open(left, encoding='utf-8') as a, open(right, encoding='utf-8') as b:
        if json.load(a) == json.load(b):
            return 0
    print(f'{left} is out of date; regenerate it and commit the result.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:3]))
