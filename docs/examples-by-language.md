# .dekk.toml Examples by Language

Ready-to-use `.dekk.toml` configurations for common project types, each
with a wrapper generation example. Use `dekk` in the examples below.

---

## Python (pip / conda)

```toml
[project]
name = "ml-pipeline"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
python  = { command = "python", version = ">=3.10" }
jupyter = { command = "jupyter", optional = true }

[env]
PYTHONPATH = "{project}/src"

[paths]
bin = ["{environment}/bin"]
```

**Wrapper:**

```bash
dekk wrap ml-pipeline ./tools/cli.py \
  --python /path/to/conda/envs/ml-pipeline/bin/python3
```

---

## Rust (cargo)

```toml
[project]
name = "my-rust-app"

[tools]
cargo = { command = "cargo", version = ">=1.70" }
rustc = { command = "rustc", version = ">=1.70" }

[paths]
bin = ["{project}/target/release"]
```

**Wrapper:**

```bash
# After: cargo build --release
dekk wrap my-rust-app ./target/release/my-rust-app
```

---

## C / C++ (cmake)

```toml
[project]
name = "physics-sim"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
cmake = { command = "cmake", version = ">=3.20" }
ninja = { command = "ninja" }
clang = { command = "clang", version = ">=17", optional = true }
gcc   = { command = "gcc", optional = true }

[env]
CMAKE_PREFIX_PATH = "{environment}"
CMAKE_BUILD_TYPE  = "Release"
CMAKE_GENERATOR   = "Ninja"

[paths]
bin = ["{project}/build/bin"]
```

**Wrapper:**

```bash
# After: cmake --build build
dekk wrap physics-sim ./build/bin/physics-sim
```

---

## Node.js (npm / pnpm)

### npm

```toml
[project]
name = "web-app"

[tools]
node = { command = "node", version = ">=18" }
npm  = { command = "npm", version = ">=9" }

[env]
NODE_ENV = "development"
```

### pnpm

```toml
[project]
name = "monorepo-app"

[tools]
node = { command = "node", version = ">=18" }
pnpm = { command = "pnpm", version = ">=8" }

[env]
NODE_ENV = "development"
```

**Wrapper (for a Node.js CLI tool):**

```bash
dekk wrap web-app ./node_modules/.bin/next
```

---

## Go

```toml
[project]
name = "api-server"

[tools]
go = { command = "go", version = ">=1.21" }

[env]
GOPATH      = "{home}/go"
GO111MODULE = "on"
CGO_ENABLED = "0"

[paths]
bin = ["{home}/go/bin", "{project}/bin"]
```

**Wrapper:**

```bash
# After: go build -o ./bin/api-server ./cmd/server
dekk wrap api-server ./bin/api-server
```

---

## Java (maven / gradle)

### Maven

```toml
[project]
name = "backend-service"

[tools]
java  = { command = "java", version = ">=17" }
mvn   = { command = "mvn", version = ">=3.9" }

[env]
JAVA_HOME  = "{environment}/lib/jvm"
MAVEN_OPTS = "-Xmx2g"
```

### Gradle

```toml
[project]
name = "android-lib"

[tools]
java   = { command = "java", version = ">=17" }
gradle = { command = "gradle", version = ">=8.0" }

[env]
JAVA_HOME   = "{environment}/lib/jvm"
GRADLE_OPTS = "-Xmx2g"
```

**Wrapper (for a Java fat JAR):**

```bash
# Create a launcher script first: ./bin/backend-service
# #!/bin/sh
# exec java -jar /path/to/backend-service.jar "$@"

dekk wrap backend-service ./bin/backend-service
```

---

## Multi-Language Project

A project combining Python, Rust, and LLVM/MLIR (e.g., a compiler toolkit):

```toml
[project]
name = "compiler-toolkit"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }
cargo  = { command = "cargo", version = ">=1.80" }
cmake  = { command = "cmake", version = ">=3.20" }
ninja  = { command = "ninja" }

[env]
CMAKE_PREFIX_PATH = "{environment}"

[paths]
bin = [
    "{environment}/bin",
    "{project}/bin",
    "{project}/target/release",
]
```

**Wrapper:**

```bash
# Wrap the Python CLI that drives the Rust-built compiler
dekk wrap compiler-toolkit ./tools/cli.py \
  --python /path/to/conda/envs/compiler-toolkit/bin/python3
```

---

## Patterns

### Minimal (any language)

The smallest valid `.dekk.toml`:

```toml
[project]
name = "hello"
```

### Agent-enabled project

Use the built-in template when the repo should generate checked-in agent files:

```bash
dekk init --example agents
dekk agents init
dekk agents generate --target all
```

The template adds `[commands]` and `[agents]` so `.agents/` can be scaffolded
from project commands.

### Tools only (no conda)

When you rely on system-installed tools:

```toml
[project]
name = "system-project"

[tools]
gcc  = { command = "gcc", version = ">=11" }
make = "make"
git  = "git"
```

### Conda only (no version-checked tools)

When conda provides everything:

```toml
[project]
name = "data-science"

[environment]
type = "conda"
path = "{project}/.dekk/env"
file = "environment.yaml"

[env]
PYTHONPATH = "{project}/src"
```

### Multiple binaries

Generate separate wrappers for each entry point:

```bash
dekk wrap myapp-server ./target/release/server
dekk wrap myapp-cli    ./target/release/cli
dekk wrap myapp-worker ./target/release/worker
```

All three wrappers share the same environment from `.dekk.toml`.

---

## See Also

- [.dekk.toml Specification](spec.md) -- full field reference
- [Wrapper Generation](wrapper.md) -- how wrappers work
- [Quick Reference](cheatsheet.md) -- one-page cheat sheet
