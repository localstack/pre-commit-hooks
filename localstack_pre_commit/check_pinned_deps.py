#!/usr/bin/env python

import argparse
import functools
from configparser import ConfigParser
from typing import Sequence

import toml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


class InvalidRequirement(Exception):
    pass


def print_error_msg(e: InvalidRequirement, extra: str = None):
    error_msg = "Due to changes in the {} you need to run `make upgrade-pinned-dependencies`"
    if extra is None:
        print(error_msg.format("base requirements"))
    else:
        print(error_msg.format(f"extra '{extra}'"))
    print(f"Violation: {e}")


def get_lock_file_from_extra(extra: str) -> str:
    return f"requirements-{extra}.txt"


@functools.cache
def get_unsafe_packages() -> list[str]:
    pyproject_toml = toml.load("pyproject.toml")
    pip_tools = pyproject_toml.get("tool", {}).get("pip-tools", {})
    if "unsafe-package" in pip_tools:
        return pip_tools["unsafe-package"]
    else:
        # if there is no unsafe-package key, return the default defined by pip-tools
        return ["pip", "setuptools", "distribute"]


def get_cfg_extras(cfg: ConfigParser) -> Sequence[str]:
    return list(cfg["options.extras_require"].keys())


def validate_requirements(lock_file_reqs: dict[str, Requirement],
                          cfg_reqs: dict[str, Requirement]):
    # the packages which should not be locked
    unsafe_packages = get_unsafe_packages()
    for req_name, req in cfg_reqs.items():
        if req_name in unsafe_packages:
            # ignore non-locked packages
            continue
        if req.marker is not None:
            # marking which environment the requirement is for
            if not req.marker.evaluate():
                # if it is not for the current environment, ignore it
                continue
        if req_name not in lock_file_reqs:
            raise InvalidRequirement(f"{req} is missing from lock file")
        # requirements can have multiple specifiers (e.g. >=1.0, <2.0) but lock files
        # only have one specifier (e.g. ==1.0). So we take the first (and only)
        # specifier from the lock file and extract the version defined in it.
        actual_version = next(iter(lock_file_reqs[req_name].specifier)).version
        valid_range = req.specifier
        # we can easily check if the version defined by the lock file is in the range
        # defined by the setup.cfg.
        # We need to allow pre-releases because of aws_cdk alpha dependencies.
        if not valid_range.contains(actual_version, prereleases=True):
            raise InvalidRequirement(
                f"{lock_file_reqs[req_name]} does not fulfil {req}")


def parse_requirements_from_cfg(cfg_deps: str) -> dict[str, Requirement]:
    requirements = {}
    for line in cfg_deps.splitlines():
        line = line.strip()
        if line.startswith("#") or line.startswith("%") or not line:
            # ignore comments and references to other extras
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
                # ignore comments and references to other extras
                continue
            req = Requirement(line)
            req.name = canonicalize_name(req.name)
            requirements[req.name] = req
    return requirements


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*", help="Filenames to check.")
    args = parser.parse_args(argv)

    if "setup.cfg" not in args.filenames:
        return 0

    setup_cfg = ConfigParser()
    setup_cfg.read("setup.cfg")

    # get the base requirements
    base_deps = parse_requirements_from_cfg(setup_cfg["options"]["install_requires"])
    # get the list of extras
    cfg_extras = get_cfg_extras(setup_cfg)
    for extra in cfg_extras:
        # get the requirements for each extra
        extra_deps = parse_requirements_from_cfg(
            setup_cfg["options.extras_require"][extra])
        lock_file = get_lock_file_from_extra(extra)
        parsed_lock_file = parse_requirements_from_lockfile(lock_file)
        try:
            validate_requirements(parsed_lock_file, base_deps)
        except InvalidRequirement as e:
            print_error_msg(e)
            return 1
        try:
            validate_requirements(parsed_lock_file, extra_deps)
        except InvalidRequirement as e:
            print_error_msg(e, extra)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
