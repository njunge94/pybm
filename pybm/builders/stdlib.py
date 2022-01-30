"""
Virtual environment creation class for benchmarking
with custom requirements in Python.
"""
import contextlib
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Union

import pybm.builders.util as builder_util
from pybm.builders.base import BaseBuilder
from pybm.config import PybmConfig
from pybm.exceptions import BuilderError
from pybm.specs import PythonSpec
from pybm.util.common import version_string
from pybm.util.print import abbrev_home
from pybm.util.subprocess import run_subprocess


@contextlib.contextmanager
def action_context(action: str, directory: Union[str, Path]):
    try:
        new_or_existing = "new" if action == "create" else "existing"
        if action.endswith("e"):
            action = action[:-1]
        print(
            f"{action.capitalize()}ing {new_or_existing} virtual environment in "
            f"location {abbrev_home(directory)}.....",
            end="",
        )
        yield
        print("done.")
        print(
            f"Successfully {action}ed {new_or_existing} virtual environment in "
            f"location {abbrev_home(directory)}."
        )
    except BuilderError as e:
        print("failed.")
        raise e


@contextlib.contextmanager
def pip_context(
    action: str,
    directory: Union[str, Path],
    packages: Optional[List[str]] = None,
    requirements_file: Optional[str] = None,
):
    try:
        if packages is None:
            resource = f"from requirements file {requirements_file!r}"
        else:
            resource = ", ".join(packages)
        into_or_from = "into" if action == "install" else "from"
        print(
            f"{action.capitalize()}ing packages {resource} {into_or_from} virtual "
            f"environment in location {str(directory)}.....",
            end="",
        )
        yield
        print("done.")
        print(
            f"Successfully {action}ed packages {resource} {into_or_from} virtual "
            f"environment in location {str(directory)}."
        )
    except BuilderError as e:
        print("failed.")
        raise e


class VenvBuilder(BaseBuilder):
    """Python standard library virtual environment builder class."""

    def __init__(self, config: PybmConfig):
        super().__init__(config=config)
        self.venv_home: str = config.get_value("builder.homedir")

        # persistent venv options
        self.venv_options: List[str] = []
        venv_option_string: str = config.get_value("builder.venvoptions")

        if venv_option_string != "":
            self.venv_options = venv_option_string.split(",")

        # persistent pip install options
        self.pip_install_options: List[str] = []

        pip_install_option_string: str = config.get_value("builder.pipinstalloptions")
        if pip_install_option_string != "":
            self.pip_install_options = pip_install_option_string.split(",")

        # persistent pip uninstall options
        self.pip_uninstall_options: List[str] = []

        pip_uninstall_option_string: str = config.get_value(
            "builder.pipuninstalloptions"
        )
        if pip_uninstall_option_string != "":
            self.pip_uninstall_options = pip_uninstall_option_string.split(",")

    def additional_arguments(self, command: str):
        if command == "create":
            args = [
                {
                    "flags": "--python",
                    "type": str,
                    "default": sys.executable,
                    "dest": "executable",
                    "help": "Python interpreter to use in virtual environment "
                    "construction.",
                    "metavar": "<python>",
                },
                {
                    "flags": "--venv-options",
                    "nargs": "*",
                    "default": None,
                    "dest": "options",
                    "help": "Space-separated list of command line options for virtual "
                    "environment creation using venv. To get a comprehensive list of "
                    "options, run `python -m venv -h`.",
                    "metavar": "<options>",
                },
            ]

        elif command == "install":
            args = [
                {
                    "flags": "-r",
                    "type": str,
                    "default": None,
                    "metavar": "<requirements>",
                    "dest": "requirements_file",
                    "help": "Requirements file for dependency installation in the "
                    "newly created virtual environment.",
                },
                {
                    "flags": "--pip-options",
                    "nargs": "*",
                    "default": None,
                    "help": "Space-separated list of command line options for "
                    "dependency installation in the created virtual environment using "
                    "`pip install`. To get a comprehensive list of options, run "
                    "`python -m pip install -h`.",
                    "metavar": "<options>",
                },
            ]
        elif command == "uninstall":
            args = [
                {
                    "flags": "-r",
                    "type": str,
                    "default": None,
                    "metavar": "<requirements>",
                    "dest": "requirements_file",
                    "help": "Requirements file containing dependencies to uninstall "
                    "from the chosen virtual environment.",
                },
                {
                    "flags": "--pip-options",
                    "nargs": "*",
                    "default": None,
                    "help": "Space-separated list of command line options for "
                    "dependency removal in the benchmark environment using "
                    "`pip uninstall`. To get a comprehensive list of options, run "
                    "`python -m pip uninstall -h`.",
                    "metavar": "<options>",
                },
            ]
        else:
            args = []
        return args

    def create(
        self,
        executable: Union[str, Path],
        destination: Union[str, Path],
        options: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> PythonSpec:

        options = options or []
        options += self.venv_options

        # create the venv in the worktree or in a special home directory
        dest = Path(destination)

        if self.venv_home == "":
            env_dir = dest
        else:
            env_dir = (Path(self.venv_home) / dest.name).resolve()

        # THIS LINE IS EXTREMELY IMPORTANT. Resolve symlinks if the
        # given Python interpreter was a symlink to begin with.
        resolved_executable = Path(executable).resolve()

        command = [str(resolved_executable), "-m", "venv", str(env_dir)]
        # Prevent duplicate options
        command += list(set(options))

        with action_context("create", directory=env_dir):
            run_subprocess(command)

        executable = builder_util.get_executable(env_dir)
        python_version = version_string(builder_util.get_python_version(executable))

        return PythonSpec(
            root=str(env_dir),
            executable=executable,
            version=python_version,
            packages=self.list(executable),
        )

    def delete(self, env_dir: Union[str, Path], verbose: bool = False) -> None:
        path = Path(env_dir)
        if not path.exists() or not path.is_dir():
            raise BuilderError(
                f"No virtual environment found at location {env_dir}: Location does "
                f"not exist or is not a directory."
            )
        elif not builder_util.is_valid_venv(path):
            raise BuilderError(
                f"Given directory {env_dir} is not a valid virtual environment."
            )

        with action_context("remove", directory=env_dir):
            shutil.rmtree(env_dir)

    def install(
        self,
        spec: PythonSpec,
        packages: Optional[List[str]] = None,
        requirements_file: Optional[str] = None,
        pip_options: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> None:
        options = pip_options or []
        executable = spec.executable

        command = [executable, "-m", "pip", "install"]
        if packages is not None:
            command += packages
        elif requirements_file is not None:
            command += ["-r", requirements_file]

        options += self.pip_install_options
        options += [f"--find-links={loc}" for loc in self.wheel_caches]
        command += list(set(options))

        with pip_context("install", spec.root, packages, requirements_file):
            run_subprocess(command, ex_type=BuilderError)

        new_packages = self.list(executable=executable)
        spec.update_packages(packages=new_packages)

    def link(self, env_dir: Union[str, Path], verbose: bool = False):
        # TODO: This discovery stuff should go into caller routine
        if (Path(self.venv_home) / env_dir).exists():
            path = Path(self.venv_home) / env_dir
        else:
            path = Path(env_dir)
        if not builder_util.is_valid_venv(path, verbose=verbose):
            msg = (
                f"The specified path {str(env_dir)} was not recognized as a valid "
                f"virtual environment, since no `python`/`pip` executables or symlinks "
                f"were discovered."
            )
            raise BuilderError(msg)

        with action_context("link", directory=env_dir):
            executable = builder_util.get_executable(env_dir)
            python_version = version_string(builder_util.get_python_version(executable))
            packages = self.list(executable, verbose=verbose)

            spec = PythonSpec(
                root=str(env_dir),
                executable=executable,
                version=python_version,
                packages=packages,
            )
            return spec

    def list(self, executable: Union[str, Path], verbose: bool = False) -> List[str]:
        command = [str(executable), "-m", "pip", "list", "--format=freeze"]
        # `pip list` output: table header, separator, package list
        # _, packages = flat_pkg_table[0], flat_pkg_table[2:]
        # return lmap(lambda x: "==".join(x.split()[:2]), packages)

        rc, pip_output = run_subprocess(command)

        return pip_output.splitlines()

    def uninstall(
        self,
        spec: PythonSpec,
        packages: List[str],
        requirements_file: Optional[str] = None,
        pip_options: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> None:

        options = pip_options or []
        options += self.pip_uninstall_options
        executable = spec.executable

        # do not ask for confirmation
        command = [executable, "-m", "pip", "uninstall", "-y", *packages]
        command += list(set(options))

        with pip_context("uninstall", spec.root, packages, None):
            run_subprocess(command)

        new_packages = self.list(executable=executable)
        spec.update_packages(packages=new_packages)
