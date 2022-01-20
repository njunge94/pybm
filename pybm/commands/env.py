import argparse
from typing import List, Callable, Mapping, Optional

from pybm.builders import BaseBuilder
from pybm.command import CLICommand
from pybm.config import PybmConfig, get_builder_class
from pybm.env_store import EnvironmentStore
from pybm.exceptions import PybmError
from pybm.logging import get_logger
from pybm.status_codes import ERROR, SUCCESS

logger = get_logger(__name__)

EnvSubcommand = Callable[[argparse.Namespace], int]


class EnvCommand(CLICommand):
    """
    Create and manage pybm benchmark environments.
    """

    # TODO: Better formatting through argparse formatter subclass
    usage = (
        "pybm env create <commit-ish> <name> <dest> [<options>]\n"
        "   or: pybm env delete <identifier> [<options>]\n"
        "   or: pybm env install <identifier> <packages> [<options>]\n"
        "   or: pybm env uninstall <identifier> <packages> [<options>]\n"
        "   or: pybm env list\n"
        "   or: pybm env update <env> <attr> <value>\n"
    )

    def __init__(self):
        super(EnvCommand, self).__init__(name="env")
        config = PybmConfig.load(".pybm/config.yaml")
        self.config = config

    def add_arguments(self, subcommand: str = None):
        if subcommand == "create":
            self.parser.add_argument(
                "commit_ish",
                metavar="<commit-ish>",
                help="Commit, branch or tag to create a git worktree for.",
            )
            self.parser.add_argument(
                "name",
                metavar="<name>",
                nargs="?",
                default=None,
                help="Unique name for the created "
                "environment. Can be used to "
                "reference environments from "
                "the command line.",
            )
            self.parser.add_argument(
                "destination",
                metavar="<dest>",
                nargs="?",
                default=None,
                help="Destination directory of "
                "the new worktree. Defaults to "
                "repository-name@{commit|branch|tag}.",
            )
            self.parser.add_argument(
                "-f",
                "--force",
                action="store_true",
                default=False,
                help="Force worktree creation. Useful "
                "for checking out a branch "
                "multiple times with different "
                "custom requirements.",
            )
            self.parser.add_argument(
                "-R",
                "--resolve-commits",
                action="store_true",
                default=False,
                help="Always resolve the given git "
                "ref to its associated commit. "
                "If the given ref is a branch "
                "name, this detaches the HEAD "
                "(see https://git-scm.com/docs/"
                "git-checkout#_detached_head).",
            )
            self.parser.add_argument(
                "--no-checkout",
                action="store_true",
                default=False,
                help="Skip worktree checkout after "
                "creation. Useful for sparsely "
                "checking out branches.",
            )
            self.parser.add_argument(
                "-L",
                "--link-existing",
                type=str,
                default=None,
                dest="link_dir",
                metavar="<path-to-venv>",
                help="Link an existing Python virtual "
                "environment to the created pybm "
                "environment. Raises an error if "
                "the path does not exist or is not "
                "recognized as a valid Python "
                "virtual environment.",
            )
        elif subcommand in ["delete", "install", "uninstall"]:
            self.parser.add_argument(
                "identifier",
                metavar="<id>",
                help="Information that uniquely "
                "identifies the environment. "
                "Can be name, checked out "
                "commit/branch/tag name, "
                "or worktree root directory.",
            )
            if subcommand == "delete":
                self.parser.add_argument(
                    "-f",
                    "--force",
                    action="store_true",
                    help="Force worktree removal, "
                    "including untracked files and changes.",
                )
            else:
                self.parser.add_argument(
                    "packages",
                    nargs="*",
                    default=None,
                    metavar="<packages>",
                    help="Package dependencies to install "
                    "into the new virtual environment.",
                )
        elif subcommand == "list":
            pass
        elif subcommand == "update":
            pass

        assert subcommand is not None, "no valid subcommand specified"

        builder: BaseBuilder = get_builder_class(config=self.config)

        builder_args = builder.additional_arguments(command=subcommand)

        if builder_args:
            builder_name = self.config.get_value("builder.name")
            builder_group_desc = (
                f"Additional options from configured builder class {builder_name!r}"
            )
            builder_group = self.parser.add_argument_group(builder_group_desc)

            # add builder-specific options into the group
            for arg in builder_args:
                builder_group.add_argument(arg.pop("flags"), **arg)

    def create(self, options: argparse.Namespace):
        option_dict = vars(options)

        # verbosity
        verbose: bool = option_dict.pop("verbose")

        # git worktree info
        commit_ish: str = option_dict.pop("commit_ish")
        name: str = option_dict.pop("name")
        destination: str = option_dict.pop("destination")
        force: bool = option_dict.pop("force")
        checkout: bool = not option_dict.pop("no_checkout")
        resolve_commits: bool = option_dict.pop("resolve_commits")

        # Python env info
        link_dir: str = option_dict.pop("link_dir")

        env_store = EnvironmentStore(config=self.config, verbose=verbose)
        env_store.create(
            commit_ish=commit_ish,
            name=name,
            destination=destination,
            force=force,
            checkout=checkout,
            resolve_commits=resolve_commits,
            link_dir=link_dir,
            **option_dict,
        )

        return SUCCESS

    def delete(self, options: argparse.Namespace):
        option_dict = vars(options)

        # verbosity
        verbose: bool = option_dict.pop("verbose")

        # env name / git worktree info
        identifier: str = option_dict.pop("identifier")
        force: bool = option_dict.pop("force")

        env_store = EnvironmentStore(config=self.config, verbose=verbose)
        env_store.delete(identifier=identifier, force=force)

        return SUCCESS

    def install(self, options: argparse.Namespace):
        option_dict = vars(options)

        # verbosity
        verbose: bool = option_dict.pop("verbose")

        # env name / git worktree info
        identifier: str = option_dict.pop("identifier")

        # builder arguments
        packages: Optional[List[str]] = option_dict.pop("packages")

        builder: BaseBuilder = get_builder_class(config=self.config)

        env_store = EnvironmentStore(config=self.config, verbose=verbose)

        target_env = env_store.get(identifier)

        builder.install(
            spec=target_env.python, packages=packages, verbose=verbose, **option_dict
        )

        return SUCCESS

    def uninstall(self, options: argparse.Namespace):
        option_dict = vars(options)

        # verbosity
        verbose: bool = option_dict.pop("verbose")

        identifier: str = option_dict.pop("identifier")

        # builder arguments
        packages: List[str] = option_dict.pop("packages")

        builder: BaseBuilder = get_builder_class(config=self.config)

        env_store = EnvironmentStore(config=self.config, verbose=verbose)

        target_env = env_store.get(identifier)

        builder.uninstall(
            spec=target_env.python, packages=packages, verbose=verbose, **option_dict
        )

        return SUCCESS

    def list(self, options: argparse.Namespace):
        verbose: bool = options.verbose

        env_store = EnvironmentStore(config=self.config, verbose=verbose)
        env_store.list()

        return SUCCESS

    def update(self, options: argparse.Namespace):
        raise PybmError("env updating is not implemented yet.")

    def run(self, args: List[str]):
        logger.debug(f"Running command: `{self.format_call(args)}`")

        subcommand_handlers: Mapping[str, EnvSubcommand] = {
            "create": self.create,
            "delete": self.delete,
            "install": self.install,
            "uninstall": self.uninstall,
            "list": self.list,
            "update": self.update,
        }

        if not args or args[0] not in subcommand_handlers:
            self.parser.print_help()
            return ERROR

        subcommand, *args = args

        self.add_arguments(subcommand=subcommand)

        options = self.parser.parse_args(args)

        return subcommand_handlers[subcommand](options)
