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


def parse_requirement(line: str, ignore_list: list[str] = None) -> Requirement | None:
    if ignore_list is None:
        # ignore comments
        ignore_list = ["#"]

    # remove trailing comments
    line = line.split("#")[0]
    line = line.strip()
    if not line or any(line.startswith(ignore) for ignore in ignore_list):
        # ignore empty lines and elements in the ignore list
        return None
    req = Requirement(line)
    req.name = canonicalize_name(req.name)
    return req


def parse_requirements(lines: Sequence, ignore_list: list[str] = None) -> dict[
    str, Requirement]:
    requirements = {}
    for line in lines:
        req = parse_requirement(line, ignore_list)
        if req is None:
            continue
        requirements[req.name] = req
    return requirements


class ProjectDefinition:
    def get_defined_extras(self) -> Sequence[str]:
        raise NotImplementedError()

    def get_base_requirements(self) -> dict[str, Requirement]:
        raise NotImplementedError()

    def get_extra_requirements(self, extra: str) -> dict[str, Requirement]:
        raise NotImplementedError()


class PyProjectDefinition:
    pyproject: dict

    def __init__(self, pyproject_path: str = "pyproject.toml"):
        self.pyproject = toml.load(pyproject_path)

    def get_defined_extras(self) -> Sequence[str]:
        return list(self.pyproject["project"]["optional-dependencies"].keys())

    def get_base_requirements(self) -> dict[str, Requirement]:
        return parse_requirements(self.pyproject["project"]["dependencies"])

    def get_extra_requirements(self, extra: str) -> dict[str, Requirement]:
        return parse_requirements(
            self.pyproject["project"]["optional-dependencies"][extra],
            ignore_list=["#", self.pyproject["project"]["name"]])


class SetupCfgDefinition(ProjectDefinition):
    def __init__(self, setup_cfg_path: str = "setup.cfg"):
        self.setup_cfg = ConfigParser()
        self.setup_cfg.read(setup_cfg_path)

    def get_defined_extras(self) -> Sequence[str]:
        return list(self.setup_cfg["options.extras_require"].keys())

    def get_base_requirements(self) -> dict[str, Requirement]:
        return parse_requirements(
            self.setup_cfg["options"]["install_requires"].splitlines())

    def get_extra_requirements(self, extra: str) -> dict[str, Requirement]:
        return parse_requirements(
            self.setup_cfg["options.extras_require"][extra].splitlines(),
            ignore_list=["#", "%"])


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


def parse_requirements_from_project_def(cfg_deps: str) -> dict[str, Requirement]:
    requirements = {}
    for line in cfg_deps.splitlines():
        req = parse_requirement(line)
        if req is None:
            continue
        requirements[req.name] = req
    return requirements


def parse_requirements_from_lockfile(lockfile: str) -> dict[str, Requirement]:
    requirements = {}
    with open(lockfile, "r") as f:
        for line in f:
            req = parse_requirement(line)
            if req is None:
                continue
            requirements[req.name] = req
    return requirements


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*", help="Filenames to check.")
    args = parser.parse_args(argv)

    if "setup.cfg" not in args.filenames and "pyproject.toml" not in args.filenames:
        return 0

    pyproject = toml.load("pyproject.toml")

    if "project" in pyproject:
        project_def = PyProjectDefinition()
    elif "setup.cfg" not in args.filenames:
        return 0
    else:
        project_def = SetupCfgDefinition()

    setup_cfg = ConfigParser()
    setup_cfg.read("setup.cfg")

    # get the base requirements
    base_deps = project_def.get_base_requirements()
    # get the list of extras
    extras = project_def.get_defined_extras()
    for extra in extras:
        # get the requirements for each extra
        extra_deps = project_def.get_extra_requirements(extra)
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
