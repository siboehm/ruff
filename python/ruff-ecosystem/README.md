# ruff-ecosystem

Ruff ecosystem checks.

## Installation

From the Ruff project root, install with `pip`:

```shell
pip install -e ./python/ruff-ecosystem
```

## Usage

Run `ruff check` ecosystem checks comparing your debug build to your system Ruff:

```shell
ruff-ecosystem check  "$(which ruff)" "./target/debug/ruff"
```

Run `ruff format` ecosystem checks comparing your debug build to your system Ruff:

```shell
ruff-ecosystem format  "$(which ruff)" "./target/debug/ruff"
```
