# .sniff-cli.toml Examples by Language

Ready-to-use `.sniff-cli.toml` configurations for common project types, each
with a wrapper generation example. Use `sniff` as the canonical command in the
examples below. `sniff-cli` remains available as a compatibility alias.

---

## Python (pip / conda)

```toml
[project]
name = "ml-pipeline"

[conda]
name = "ml-pipeline"
file = "environment.yaml"

[tools]
python  = { command = "python", version = ">=3.10" }
jupyter = { command = "jupyter", optional = true }

[env]
PYTHONPATH = "{project}/src"

[paths]
bin = ["{conda}/bin"]
```

**Wrapper:**

```bash
sniff wrap ml-pipeline ./tools/cli.py \
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
sniff wrap my-rust-app ./target/release/my-rust-app
```

---

## C / C++ (cmake)

```toml
[project]
name = "physics-sim"

[conda]
name = "physics-sim"
file = "environment.yaml"

[tools]
cmake = { command = "cmake", version = ">=3.20" }
ninja = { command = "ninja" }
clang = { command = "clang", version = ">=17", optional = true }
gcc   = { command = "gcc", optional = true }

[env]
CMAKE_PREFIX_PATH = "{conda}"
CMAKE_BUILD_TYPE  = "Release"
CMAKE_GENERATOR   = "Ninja"

[paths]
bin = ["{project}/build/bin"]
```

**Wrapper:**

```bash
# After: cmake --build build
sniff wrap physics-sim ./build/bin/physics-sim
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
sniff wrap web-app ./node_modules/.bin/next
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
sniff wrap api-server ./bin/api-server
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
JAVA_HOME  = "{conda}/lib/jvm"
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
JAVA_HOME   = "{conda}/lib/jvm"
GRADLE_OPTS = "-Xmx2g"
```

**Wrapper (for a Java fat JAR):**

```bash
# Create a launcher script first: ./bin/backend-service
# #!/bin/sh
# exec java -jar /path/to/backend-service.jar "$@"

sniff wrap backend-service ./bin/backend-service
```

---

## Multi-Language Project

A project combining Python, Rust, and LLVM/MLIR (e.g., a compiler toolkit):

```toml
[project]
name = "compiler-toolkit"

[conda]
name = "compiler-toolkit"
file = "environment.yaml"

[tools]
python = { command = "python", version = ">=3.10" }
cargo  = { command = "cargo", version = ">=1.80" }
cmake  = { command = "cmake", version = ">=3.20" }
ninja  = { command = "ninja" }

[env]
MLIR_DIR = "{conda}/lib/cmake/mlir"
LLVM_DIR = "{conda}/lib/cmake/llvm"

[paths]
bin = [
    "{conda}/bin",
    "{project}/bin",
    "{project}/target/release",
]
```

**Wrapper:**

```bash
# Wrap the Python CLI that drives the Rust-built compiler
sniff wrap compiler-toolkit ./tools/cli.py \
  --python /path/to/conda/envs/compiler-toolkit/bin/python3
```

---

## Patterns

### Minimal (any language)

The smallest valid `.sniff-cli.toml`:

```toml
[project]
name = "hello"
```

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

[conda]
name = "data-science"
file = "environment.yaml"

[env]
PYTHONPATH = "{project}/src"
```

### Multiple binaries

Generate separate wrappers for each entry point:

```bash
sniff wrap myapp-server ./target/release/server
sniff wrap myapp-cli    ./target/release/cli
sniff wrap myapp-worker ./target/release/worker
```

All three wrappers share the same environment from `.sniff-cli.toml`.

---

## See Also

- [.sniff-cli.toml Specification](spec.md) -- full field reference
- [Wrapper Generation](wrapper.md) -- how wrappers work
- [Quick Reference](cheatsheet.md) -- one-page cheat sheet
