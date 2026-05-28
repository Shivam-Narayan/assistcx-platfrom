import re
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "__init__.py"


def get_version():
    with open(VERSION_FILE, "r") as f:
        content = f.read()
    match = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', content, re.MULTILINE)
    if match:
        return match.group(1)
    raise RuntimeError("Unable to find version string.")


def bump_version(bump_type):
    version = get_version().split(".")
    if bump_type == "major":
        version[0] = str(int(version[0]) + 1)
        version[1] = "0"
        version[2] = "0"
    elif bump_type == "minor":
        version[1] = str(int(version[1]) + 1)
        version[2] = "0"
    elif bump_type == "patch":
        version[2] = str(int(version[2]) + 1)
    else:
        raise ValueError("Invalid bump type. Use 'major', 'minor', or 'patch'.")

    new_version = ".".join(version)
    with open(VERSION_FILE, "r") as f:
        content = f.read()

    new_content = re.sub(
        r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
        f'__version__ = "{new_version}"',
        content,
        flags=re.MULTILINE,
    )

    with open(VERSION_FILE, "w") as f:
        f.write(new_content)

    return new_version


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print(bump_version(sys.argv[1]))
    else:
        print(get_version())
