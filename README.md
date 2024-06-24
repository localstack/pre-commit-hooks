# LocalStack [pre-commit](https://pre-commit.com/) hooks

## Usage in Repositories

### Prerequisites 
You need to add [pre-commit](https://pre-commit.com/) to your python environment and install the hooks:

```bash
pip install pre-commit
pre-commit install
```

### Install

Then, to use hooks from this repo add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/localstack/pre-commit-hooks
    rev: v1.0.0
    hooks:
      - id: check-pinned-deps-for-needed-upgrade
```

### Testing
To run a hook manually on the staged changes use the following command:

```bash
pre-commit run <hook-id> --files $(git diff --name-only --cached)
```

## Available Hooks

- `check-pinned-deps-for-needed-upgrade`: This hook will notify contributors if the project file has changed and the pinned dependencies do not satisfy the project file. 
The project file can either be `pyproject.toml` or `setup.cfg`.
If the `pyproject.toml` file contains a `project` section, the hook will check the `pyproject.toml` file, otherwise it will check the `setup.cfg` file.
- `validate-localstack-openapi-spec`: This hook validates the LocalStack OpenAPI specification against OAS 3.1, which it looks for in `localstack.spec` and `localstack_ext.spec` modules.

## Adding new Hooks

To add a new hook, create a new python file in the `localstack_pre_commit` directory.
It should have a function called `main` that takes a list of files as an argument.
The function should return a `0` if the hook passes and a `1` if it fails.
After creating the hook, add the main function to the `project.scripts` section of the `pyproject.toml` file using a concise script name.

Then create a new entry in the `.pre-commit-hooks.yaml` file giving the hook a unique id and referencing the script name from the `pyproject.toml` file.
Also give a brief description of what the hook does.

Finally, add the hook to the `README.md` file in the `## Available Hooks` section.
