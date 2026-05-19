# Real-World `.dekk.toml` Examples

The configs in [`docs/examples-by-language.md`](examples-by-language.md) are
deliberately minimal. This page is the opposite: two **complete, in-production**
`.dekk.toml` files from real compiler projects, annotated section by section, so
a new project can copy a proven structure instead of assembling one from
fragments.

| Project | Stack | What it demonstrates | Upstream |
|---------|-------|----------------------|----------|
| **CARTS** | C/C++ + MLIR | conda from `environment.yml`, version-pinned toolchain, grouped `[commands]` with `skill = true`, install driver + optional wrapper, layered `.install/` bin paths | [randreshg/carts](https://github.com/randreshg/carts/blob/main/.dekk.toml) |
| **APXM** | Rust + Python + MLIR | inline `[environment.packages]` (no `environment.yml`), deeply nested `[commands.<group>]` sub-command trees, multi-step `[[install.components]]` with `requires` | [randreshg/apxm](https://github.com/randreshg/apxm/blob/main/.dekk.toml) |

Copy-ready snapshots live in
[`examples/real-world/`](../examples/real-world/). They are point-in-time
copies — the upstream repos are the source of truth.

---

## CARTS — a CMake/MLIR compiler driven by a Python CLI

CARTS transforms OpenMP-annotated C/C++ into task-parallel executables on the
ARTS runtime. Every contributor command goes through `dekk carts <command>`.

### Environment from a checked-in `environment.yml`

```toml
[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yml"
name = "carts"
```

The env is **project-local** (`{project}/.dekk/env`), so worktrees and clones
never collide and nothing leaks into the user's global conda. `file` points at
a tracked `environment.yml` — the right choice when the dependency set is large,
already maintained for other tooling, or shared with non-dekk workflows.

> Use this when you already have an `environment.yml`. Use APXM's inline
> `[environment.packages]` (below) when you want the pins to live in
> `.dekk.toml` itself.

### Version-pinned toolchain, with optionals

```toml
[tools]
cmake     = { command = "cmake",   version = ">=3.20" }
clang     = { command = "clang",   version = ">=18" }
"clang++" = { command = "clang++", version = ">=18" }
python    = { command = "python",  version = ">=3.11" }
gcc          = { command = "gcc",          optional = true }
clang-format = { command = "clang-format", optional = true }
lit          = { command = "lit",          optional = true }
```

Two things worth copying:

- A tool key containing `+` (`"clang++"`) **must be quoted** — it is a TOML key,
  not the command. `command = "clang++"` is what actually gets resolved.
- `optional = true` turns "missing" into a warning, not a hard activation
  failure. `gcc`, `clang-format`, and `lit` are nice-to-have, so a fresh clone
  still activates without them.

### Grouped commands, with `skill = true` on the important ones

```toml
[commands]
doctor   = { run = "python tools/carts_cli.py doctor",  description = "...", group = "Environment" }
build    = { run = "python tools/carts_cli.py build",   description = "...", skill = true, group = "Build & Test" }
compile  = { run = "python tools/carts_cli.py compile", description = "...", skill = true, group = "Compilation" }
```

Every command is a thin shim to one Python CLI. The payoff:

- `group` buckets commands in `dekk carts --help` ("Environment", "Build &
  Test", "Compilation", "Benchmarking", "Development", "Docker") instead of one
  flat wall of names.
- `skill = true` marks the commands that become agent skills when you run
  `dekk carts skills init` / `skills generate` — here the genuine workflow verbs
  (`build`, `compile`, `pipeline`, `test`, `benchmarks`, `triage-benchmark`),
  not inspection helpers like `env` or `version`.

> Pattern: keep the real logic in your own CLI; let `.dekk.toml` be the stable,
> declarative, agent-readable surface over it.

### Install driver + opt-in wrapper

```toml
[install]
build = "python tools/install_driver.py"
wrap  = { name = "carts", target = "tools/carts_cli.py" }

[env]
CARTS_DIR            = "{project}"
LLVM_SYMBOLIZER_PATH = "{project}/.install/llvm/bin/llvm-symbolizer"

[paths]
bin = [
    "{project}/.install",
    "{project}/.install/bin",
    "{project}/.install/carts/bin",
    "{project}/.install/llvm/bin",
    "{project}/.install/arts/bin",
    "{project}/.install/polygeist/bin",
]
```

`dekk carts install` sets up the env then runs `install_driver.py`. `wrap` is
defined but only materializes with `dekk carts install --wrap`, producing
`./.install/carts` for activation-free daily use. The `[paths].bin` list layers
every sub-toolchain's `bin/` (LLVM, ARTS, Polygeist) onto `PATH` in one place,
and `{project}`-relative entries keep that correct in any worktree.

---

## APXM — a Rust+Python workspace with a deep command tree

APXM compiles agent graphs through an MLIR dialect. It pushes three features
CARTS doesn't use.

### Inline conda packages — no `environment.yml`

```toml
[environment]
type = "conda"
path = "{project}/.dekk/env"
name = "apxm"
channels = ["conda-forge"]

[environment.packages]
mlir = "22"
clang = "22"
python = "3.11"
cmake = ""
ninja = ""
nodejs = "22"
```

The pins live **in `.dekk.toml`**. `[environment.packages]` is a map of
`package = "version"`; an empty string means "latest / unpinned". `channels`
overrides the default `["conda-forge"]`.

> `environment.file` and `[environment.packages]` are **mutually exclusive** —
> dekk raises a config error if both are set. Inline packages keep the whole
> environment in one reviewable file; pick it when the dependency set is small
> and dekk-owned.

### Nested command groups

CARTS commands are flat. APXM nests them — `[commands.<group>]` tables whose
non-metadata keys are themselves commands:

```toml
[commands.backend]
description = "Manage inference backends (cloud/onprem/local)"
group = "Configuration"
add  = { run = "apxm backend add",  description = "Add backend", skill = true }
list = { run = "apxm backend list", description = "List backends" }
```

This is invoked as `dekk apxm backend add`. `description`, `group`, `run`, and
`skill` are reserved metadata keys; every *other* key in the table is parsed as
a sub-command (recursively). `dekk apxm backend` with no sub-command prints
group help. APXM uses this for `backend`, `vllm`, `mcp`, `ops`, `template`,
`tool`, `agent`, `cache`, and `process` — a CLI-sized surface kept entirely
declarative.

### Multi-component install with `requires`

```toml
[install]
wrap = { name = "apxm", target = "target/release/apxm" }

[[install.components]]
name = "compiler-runtime"
label = "Compiler + Runtime"
run = "python tools/scripts/cargo.py build -p apxm-cli --features driver,metrics --release"
default = true

[[install.components]]
name = "dspy"
label = "DSPy Prompt Optimizer"
run = "pip install dspy-ai>=2.6.0"
default = false
requires = ["pip"]
```

`[[install.components]]` (an array of tables) gives `dekk apxm install` an
interactive checklist. `default = true` pre-selects core pieces
(`compiler-runtime`, `mcp-server`); `default = false` leaves heavy extras
(`gui`, `vllm`, `dspy`) opt-in. `requires = ["pip"]` gates a component on a
command being present — dekk skips/flags it up front instead of failing
mid-build. Non-interactive callers use
`--all` / `--components a,b` / `--no-interactive`.

### `bin` *and* `lib` paths

```toml
[paths]
bin = ["{project}/bin", "{project}/target/release", "{home}/.cargo/bin"]
lib = ["{project}/target/release/lib", "{environment}/lib"]
```

`bin` is prepended to `PATH`. Other keys like `lib` are exposed for consumers
(here paired with an explicit `LD_LIBRARY_PATH` in `[env]` so the
MLIR-linked Rust binary finds its shared libs at runtime).

### One caveat — not every value is a dekk feature

```toml
[env]
LLM_GATEWAY_KEY = "env:LLM_GATEWAY_KEY"
```

dekk stores this as the **literal string** `"env:LLM_GATEWAY_KEY"`. The `env:`
prefix is an APXM-internal indirection convention that APXM resolves itself —
it is *not* dekk variable expansion. Only `{project}`, `{environment}`, and
`{home}` are expanded by dekk (see [spec.md](spec.md#variable-expansion)).
Called out so the pattern isn't copied expecting dekk to dereference it.

---

## Choosing between these as a starting point

- **CMake / C / C++, large or shared dependency set** → start from
  [`carts.dekk.toml`](../examples/real-world/carts.dekk.toml): `environment.file`,
  flat grouped commands, install driver.
- **Rust / Python / mixed, dekk-owned deps, big sub-command surface** → start
  from [`apxm.dekk.toml`](../examples/real-world/apxm.dekk.toml): inline
  `[environment.packages]`, nested command groups, install components.

Both share the load-bearing conventions: project-local conda env under
`{project}/.dekk/env`, every workflow exposed as a `dekk <app> <command>`, and
`{project}`-relative paths so it all works from any worktree.

## See Also

- [.dekk.toml Specification](spec.md) — full field reference
- [Examples by Language](examples-by-language.md) — minimal per-language configs
- [Agent Workflows](agents.md) — what `skill = true` feeds into
