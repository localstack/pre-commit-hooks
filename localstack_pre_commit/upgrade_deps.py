#!/usr/bin/env python

import argparse
import functools
import subprocess
from configparser import ConfigParser
from typing import Sequence

import toml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


class InvalidRequirement(Exception):
    pass


def get_lock_file_from_extra(extra: str) -> str:
    return f"requirements-{extra}.txt"


@functools.cache
def get_unsafe_packages() -> list[str]:
    pyproject_toml = toml.load("pyproject.toml")
    unsafe = pyproject_toml["tool"]["pip-tools"]["unsafe-package"]
    return unsafe


def get_old_and_new_setup_cfg(
    setup_cfg_path: str = "setup.cfg",
) -> tuple[ConfigParser, ConfigParser]:
    old_file_contents = get_file_contents_before_change(setup_cfg_path)
    if old_file_contents is None:
        raise SystemExit(1)
    old_cfg = ConfigParser()
    old_cfg.read_string(old_file_contents)

    new_cfg = ConfigParser()
    new_cfg.read(setup_cfg_path)

    return old_cfg, new_cfg


def get_file_contents_before_change(file_path: str) -> str | None:
    git_show_cmd = f"git show HEAD:{file_path}"
    try:
        result = subprocess.run(
            git_show_cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise SystemExit(1) from e


def get_changed_extras(old_cfg: ConfigParser, new_cfg: ConfigParser) -> Sequence[str]:
    changed_extras = []
    for extra_group, extra_items in old_cfg["options.extras_require"].items():
        now_extra = new_cfg["options.extras_require"][extra_group]
        if extra_items != now_extra:
            changed_extras.append(extra_group)
    return changed_extras


def base_requirements_changed(old_cfg: ConfigParser, new_cfg: ConfigParser) -> bool:
    old_base_reqs = old_cfg["options"]["install_requires"]
    new_base_reqs = new_cfg["options"]["install_requires"]
    return old_base_reqs != new_base_reqs


def validate_requirements(lock_file_reqs: dict[str, Requirement], cfg_reqs: dict[str, Requirement]):
    unsafe_packages = get_unsafe_packages()
    for req_name, req in cfg_reqs.items():
        if req_name in unsafe_packages:
            continue
        if req_name not in lock_file_reqs:
            raise InvalidRequirement(f"{req} is missing from lock file")
        # todo comment
        actual_version = next(iter(lock_file_reqs[req_name].specifier)).version
        valid_range = req.specifier
        # need to allow pre-releases because of aws_cdk alpha dependencies
        if not valid_range.contains(actual_version, prereleases=True):
            raise InvalidRequirement(f"{lock_file_reqs[req_name]} does not fulfil {req}")


def parse_requirements_from_cfg(cfg_deps: str) -> dict[str, Requirement]:
    requirements = {}
    for line in cfg_deps.splitlines():
        line = line.strip()
        if line.startswith("#") or line.startswith("%") or not line:
            continue
        req = Requirement(line)
        req.name = canonicalize_name(req.name)
        requirements[req.name] = req
    return requirements


def parse_requirements_from_lockfile(lockfile: str) -> dict[str, Requirement]:
    requirements = {}
    with open(lockfile, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or line.startswith("%") or not line:
                continue
            req = Requirement(line)
            req.name = canonicalize_name(req.name)
            requirements[req.name] = req
    return requirements


def run_make(targets: Sequence[str]):
    make_cmd = ["make", *targets]
    try:
        subprocess.run(make_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(1) from e


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*", help="Filenames to check.")
    args = parser.parse_args(argv)

    if "setup.cfg" not in args.filenames:
        return 0

    old_cfg, new_cfg = get_old_and_new_setup_cfg()

    if base_requirements_changed(old_cfg, new_cfg):
        base_deps = parse_requirements_from_cfg(new_cfg["options"]["install_requires"])
        parsed_lock_file = parse_requirements_from_lockfile("requirements.txt")
        try:
            validate_requirements(parsed_lock_file, base_deps)
        except InvalidRequirement:
            print(
                "Due to changes in the base requirements" "you need to run `make upgrade-all-reqs`"
            )
            return 1

    changed_extras = get_changed_extras(old_cfg, new_cfg)
    for extra in changed_extras:
        extra_deps = parse_requirements_from_cfg(new_cfg["options.extras_require"][extra])
        lock_file = get_lock_file_from_extra(extra)
        parsed_lock_file = parse_requirements_from_lockfile(lock_file)
        try:
            validate_requirements(parsed_lock_file, extra_deps)
        except InvalidRequirement as e:
            print(
                f"Due to changes in the extra '{extra}' " f"you need to run `make upgrade-all-reqs`"
            )
            print(f"Error: {e}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
