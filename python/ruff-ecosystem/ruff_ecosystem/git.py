from ruff_ecosystem.models import Repository, ClonedRepository
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from asyncio import create_subprocess_exec
from subprocess import PIPE
from ruff_ecosystem import logger


@asynccontextmanager
async def clone(
    repo: Repository, checkout_dir: Path
) -> AsyncGenerator[ClonedRepository, None]:
    """Shallow clone this repository to a temporary directory."""
    if checkout_dir.exists():
        logger.debug(f"Reusing {repo.org}:{repo.repo}")
        yield await _cloned_repository(repo, checkout_dir)
        return

    logger.debug(f"Cloning {repo.org}:{repo.repo}")
    git_clone_command = [
        "git",
        "clone",
        "--config",
        "advice.detachedHead=false",
        "--quiet",
        "--depth",
        "1",
        "--no-tags",
    ]
    if repo.branch:
        git_clone_command.extend(["--branch", repo.branch])

    git_clone_command.extend(
        [
            f"https://github.com/{repo.org}/{repo.repo}",
            checkout_dir,
        ],
    )

    git_clone_process = await create_subprocess_exec(
        *git_clone_command,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )

    status_code = await git_clone_process.wait()

    logger.debug(
        f"Finished cloning {repo.org}/{repo.repo} with status {status_code}",
    )
    yield await _cloned_repository(repo, checkout_dir)


async def _cloned_repository(repo: Repository, checkout_dir: Path) -> ClonedRepository:
    return ClonedRepository(
        name=repo.name,
        owner=repo.owner,
        path=checkout_dir,
        commit_hash=await _get_commit_hash(checkout_dir),
    )


async def _get_commit_hash(checkout_dir: Path) -> str:
    """
    Return the commit sha for the repository in the checkout directory.
    """
    git_sha_process = await create_subprocess_exec(
        *["git", "rev-parse", "HEAD"],
        cwd=checkout_dir,
        stdout=PIPE,
    )
    git_sha_stdout, _ = await git_sha_process.communicate()
    assert (
        await git_sha_process.wait() == 0
    ), f"Failed to retrieve commit sha at {checkout_dir}"
    return git_sha_stdout.decode().strip()
