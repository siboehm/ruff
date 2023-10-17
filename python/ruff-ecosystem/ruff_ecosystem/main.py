from ruff_ecosystem.models import RuffCommand, Target, Diff
from pathlib import Path
from ruff_ecosystem import logger
import asyncio
from ruff_ecosystem.git import clone
from ruff_ecosystem.ruff import ruff_check, ruff_format
import difflib
from typing import TypeVar
import re

T = TypeVar("T")


async def main(
    command: RuffCommand,
    ruff_base_executable: Path,
    ruff_compare_executable: Path,
    targets: list[Target],
    cache: Path | None,
    max_parallelism: int = 50,
) -> None:
    logger.debug("Using command %s", command)
    logger.debug("Using base Ruff executable at %s", ruff_base_executable)
    logger.debug("Using comparison Ruff executable at %s", ruff_compare_executable)
    logger.debug("Using cache directory %s", cache)
    logger.debug("Checking %s targets", len(targets))

    semaphore = asyncio.Semaphore(max_parallelism)

    async def limited_parallelism(coroutine: T) -> T:
        async with semaphore:
            return await coroutine

    diffs: list[Exception | Diff] = await asyncio.gather(
        *[
            limited_parallelism(
                compare(
                    command,
                    ruff_base_executable,
                    ruff_compare_executable,
                    target,
                    cache,
                )
            )
            for target in targets
        ],
        return_exceptions=True,
    )
    diffs_by_target = dict(zip(targets, diffs, strict=True))

    total_removed = total_added = errors = 0

    for diff in diffs_by_target.values():
        if isinstance(diff, Exception):
            errors += 1
        else:
            total_removed += len(diff.removed)
            total_added += len(diff.added)

    if total_removed == 0 and total_added == 0 and errors == 0:
        print("\u2705 ecosystem check detected no changes.")
    else:
        rule_changes: dict[str, tuple[int, int]] = {}
        s = "s" if errors != 1 else ""
        changes = f"(+{total_added}, -{total_removed}, {errors} error{s})"

        print(f"\u2139\ufe0f ecosystem check **detected changes**. {changes}")
        print()

        for target, diff in diffs_by_target.items():
            if isinstance(diff, Exception):
                changes = "error"
                print(f"<details><summary>{target.repo.fullname} ({changes})</summary>")
                print(target.repo.url, target.check_options.summary())
                print("<p>")
                print()

                print("```")
                print(str(diff))
                print("```")

                print()
                print("</p>")
                print("</details>")
            elif diff:
                changes = f"+{len(diff.added)}, -{len(diff.removed)}"
                print(f"<details><summary>{target.repo.fullname} ({changes})</summary>")
                print("<p>")
                print()
                diff_lines = list(diff)

                print("<pre>")
                for line in diff_lines:
                    match = DIFF_LINE_RE.match(line)
                    if match is None:
                        print(line)
                        continue

                    pre, inner, path, lnum, post = match.groups()
                    url = target.repo.url_for(diff.source_sha, path, int(lnum))
                    print(f"{pre} <a href='{url}'>{inner}</a> {post}")
                print("</pre>")

                print()
                print("</p>")
                print("</details>")

                # Count rule changes
                for line in diff_lines:
                    # Find rule change for current line or construction
                    # + <rule>/<path>:<line>:<column>: <rule_code> <message>
                    matches = re.search(r": ([A-Z]{1,4}[0-9]{3,4})", line)

                    if matches is None:
                        # Handle case where there are no regex matches e.g.
                        # +                 "?application=AIRFLOW&authenticator=TEST_AUTH&role=TEST_ROLE&warehouse=TEST_WAREHOUSE" # noqa: E501, ERA001
                        # Which was found in local testing
                        continue

                    rule_code = matches.group(1)

                    # Get current additions and removals for this rule
                    current_changes = rule_changes.get(rule_code, (0, 0))

                    # Check if addition or removal depending on the first character
                    if line[0] == "+":
                        current_changes = (current_changes[0] + 1, current_changes[1])
                    elif line[0] == "-":
                        current_changes = (current_changes[0], current_changes[1] + 1)

                    rule_changes[rule_code] = current_changes

            else:
                continue

        if len(rule_changes.keys()) > 0:
            print(f"Rules changed: {len(rule_changes.keys())}")
            print()
            print("| Rule | Changes | Additions | Removals |")
            print("| ---- | ------- | --------- | -------- |")
            for rule, (additions, removals) in sorted(
                rule_changes.items(),
                key=lambda x: (x[1][0] + x[1][1]),
                reverse=True,
            ):
                print(f"| {rule} | {additions + removals} | {additions} | {removals} |")


async def compare(
    command: RuffCommand,
    ruff_base: Path,
    ruff_compare: Path,
    target: Target,
    cache: Path,
) -> Diff:
    """Check a specific repository against two versions of ruff."""
    removed, added = set(), set()

    assert ":" not in target.repo.owner
    assert ":" not in target.repo.name

    match command:
        case RuffCommand.Check:
            ruff_task, options = (ruff_check, target.check_options)
        case RuffCommand.Format:
            ruff_task, options = (ruff_format, target.format_options)
        case _:
            raise ValueError(f"Unknowm target Ruff command {command}")

    checkout_dir = cache.joinpath(f"{target.repo.owner}:{target.repo.name}")
    async with clone(target.repo, checkout_dir) as cloned_repo:
        try:
            async with asyncio.TaskGroup() as tg:
                base_task = tg.create_task(
                    ruff_task(
                        executable=ruff_base,
                        path=cloned_repo.path,
                        name=cloned_repo.fullname(),
                        options=options,
                    ),
                )
                compare_task = tg.create_task(
                    ruff_task(
                        executable=ruff_compare,
                        path=cloned_repo.path,
                        name=cloned_repo.fullname(),
                        options=options,
                    ),
                )
        except ExceptionGroup as e:
            raise e.exceptions[0] from e

        for line in difflib.ndiff(base_task.result(), compare_task.result()):
            if line.startswith("- "):
                removed.add(line[2:])
            elif line.startswith("+ "):
                added.add(line[2:])

    return Diff(removed, added)
