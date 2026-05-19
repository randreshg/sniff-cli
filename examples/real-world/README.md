# Real-World `.dekk.toml` Snapshots

Complete, in-production configs from real compiler projects. Copy and adapt —
do not run as-is (the commands reference each project's own scripts).

| File | Project | Stack | Demonstrates |
|------|---------|-------|--------------|
| [`carts.dekk.toml`](carts.dekk.toml) | [randreshg/carts](https://github.com/randreshg/carts) | C/C++ + MLIR | conda from `environment.yml`, version-pinned tools, grouped commands + `skill = true`, install driver + wrapper, layered `.install/` paths |
| [`apxm.dekk.toml`](apxm.dekk.toml) | [randreshg/apxm](https://github.com/randreshg/apxm) | Rust + Python + MLIR | inline `[environment.packages]`, nested `[commands.<group>]` trees, `[[install.components]]` with `requires`, `bin` + `lib` paths |

These are **point-in-time snapshots**. The upstream repositories are the source
of truth; pull the latest `.dekk.toml` from there if they diverge.

For a section-by-section explanation of *why* each config is shaped this way,
see the annotated walkthrough: [`docs/real-world-examples.md`](../../docs/real-world-examples.md).

For minimal per-language starting points instead, see
[`docs/examples-by-language.md`](../../docs/examples-by-language.md).
