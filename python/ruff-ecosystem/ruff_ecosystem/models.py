from enum import Enum
from dataclasses import dataclass, field
from typing import Self, NamedTuple, Iterator
import heapq


class RuffCommand(Enum):
    Check = "check"
    Format = "format"


@dataclass(frozen=True)
class Repository:
    """
    A remote GitHub repository
    """

    owner: str
    name: str
    branch: str | None


@dataclass(frozen=True)
class ClonedRepository(Repository):
    """
    A cloned GitHub repository
    """

    path: str
    commit_hash: str

    def url_for(self: Self, path: str, line_number: int | None = None) -> str:
        """
        Return the remote GitHub URL for the given path in this repository.
        """
        # Default to main branch
        url = f"https://github.com/{self.owner}/{self.name}/blob/{self.commit_hash}/{path}"
        if line_number:
            url += f"#L{line_number}"
        return url

    def url(self: Self) -> str:
        return f"https://github.com/{self.owner}/{self.name}@{self.commit_hash}"

    def fullname(self) -> str:
        return f"{self.owner}/{self.name}"


class Diff(NamedTuple):
    """A diff between two runs of ruff."""

    removed: set[str]
    added: set[str]

    def __bool__(self: Self) -> bool:
        """Return true if this diff is non-empty."""
        return bool(self.removed or self.added)

    def __iter__(self: Self) -> Iterator[str]:
        """Iterate through the changed lines in diff format."""
        for line in heapq.merge(sorted(self.removed), sorted(self.added)):
            if line in self.removed:
                yield f"- {line}"
            else:
                yield f"+ {line}"


@dataclass(frozen=True)
class CheckOptions:
    """
    Ruff check options
    """

    select: str = ""
    ignore: str = ""
    exclude: str = ""

    # Generating fixes is slow and verbose
    show_fixes: bool = False

    def summary(self) -> str:
        return f"select {self.select} ignore {self.ignore} exclude {self.exclude}"


@dataclass(frozen=True)
class FormatOptions:
    """
    Ruff format options
    """

    pass


@dataclass(frozen=True)
class Target:
    """
    An ecosystem target
    """

    repo: Repository
    check_options: CheckOptions = field(default_factory=CheckOptions)
    format_options: FormatOptions = field(default_factory=FormatOptions)
