"""Copies the tarballs and digests that the arguments name into ./dist."""

import os
import shutil
import sys


def main():
    dist = os.path.join(os.environ["BUILD_WORKSPACE_DIRECTORY"], "dist")
    os.makedirs(dist, exist_ok=True)
    for path in sys.argv[1:]:
        target = os.path.join(dist, os.path.basename(path))
        shutil.copyfile(path, target)
        os.chmod(target, 0o644)
        print(target)


if __name__ == "__main__":
    main()
