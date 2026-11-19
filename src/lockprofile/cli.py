import argparse
import hashlib
import json
import os
import stat
import sys
import tomllib

from .core import compare


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("input must be a regular file")
        data = stream.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("input exceeds 4 MiB")
    return data


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare pylock selection across all public feature subsets"
    )
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument(
        "--environment", required=True, help="JSON of all 11 marker environment fields"
    )
    parser.add_argument("--max-nodes", type=int, default=100_000)
    args = parser.parse_args(argv)
    try:
        old, new, env = (
            read_regular(path) for path in (args.before, args.after, args.environment)
        )
        report = compare(
            tomllib.loads(old.decode("utf-8")),
            tomllib.loads(new.decode("utf-8")),
            json.loads(env, object_pairs_hook=unique),
            max_nodes=args.max_nodes,
        )
        report["receipts"] = {
            label: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for label, raw in (("before", old), ("after", new), ("environment", env))
        }
        output = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        sys.stdout.write(output)
        sys.stdout.flush()
    except (ValueError, OSError, RecursionError, TypeError) as error:
        try:
            print("lockprofile: " + str(error), file=sys.stderr, flush=True)
        except OSError:
            pass
        return 2
    return 0 if report["status"] == "EQUIVALENT_IN_PROFILE" else 1


def entrypoint():
    code = main()
    if code == 2:
        # main() never closes caller streams; an executable owns final shutdown.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.close()
            except OSError:
                pass
    return code
