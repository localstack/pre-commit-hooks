#!/usr/bin/env python

#
# This script validates the LocalStack OpenAPI specification.
#

import argparse
import importlib.machinery
import importlib.util
import sys
from typing import Sequence

import openapi_spec_validator


# Files that define the OpenAPI spec in a variable named `OPENAPI`
SCHEMA_FILES = ("localstack/spec.py", "localstack_ext/spec.py")


def load_spec_dict(file: str) -> dict:
    # Attempt to load given file as a Python module
    loader = importlib.machinery.SourceFileLoader('module', file)
    loader_spec = importlib.util.spec_from_loader('module', loader)
    module = importlib.util.module_from_spec(loader_spec)
    loader.exec_module(module)

    # Return the OAS dict
    return module.OPENAPI


def validate(spec: dict) -> int:
    # Validate spec dict against OAS 3.1
    result = openapi_spec_validator.OpenAPIV31SpecValidator(spec).iter_errors()

    err_count = 0
    for err_count, err in enumerate(result, start=1):
        msg = f"{list(err.path)}: {err.message}"
        print(msg, file=sys.stderr)

    return err_count


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*", help="Filenames to check.")
    args = parser.parse_args(argv)

    for file in args.filenames:
        for schema_file in SCHEMA_FILES:
            if file.endswith(schema_file):
                spec = load_spec_dict(file)
                if validate(spec) != 0:
                    return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
