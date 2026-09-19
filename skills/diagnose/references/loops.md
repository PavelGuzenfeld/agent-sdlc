# Building a tight loop in this stack

Recipes for Phase 1, and the traps that make a loop lie. Only expensive lookups
live here; anything a `--help` away stays out.

Everything builds and runs in Docker. No toolchains on the host.

## Before you trust a red

- **Run the suite before the batch and after every test edit.** A red baseline makes
  every perturbation read as caught, which is worse than no loop at all.
- **Check that assertions still exist at runtime.** A wrapper setting
  `PYTHONOPTIMIZE=2` strips every Python `assert`, so an assert-based probe is a
  silent no-op.
- **Check which config actually loaded.** A run script that bind-mounts a host
  config over the image's copy makes the host copy win, and the image's version
  stamp invisible.

## Godot suites (live-action)

One suite runs in ~0.5 s, so mutation and bisection batches are cheap.

```bash
docker run --rm --user 1001:1002 -e HOME=/tmp/gdhome \
  --mount type=bind,src=$PWD,dst=/work -w /work \
  ghcr.io/<org>/<project>/godot-ci:<tag> \
  godot --headless --path godot/project --script res://tests/<suite>.gd
```

The Godot version drifts (4.7.1 and 4.7.2 have both been current). Read
`godot/docker/` or the CI workflow for the tag in use rather than pinning one here.

**Read the exit code, not the log.** A passing suite still prints leaked-ObjectDB
`WARNING:` and `ERROR:` lines at exit, plus an ALSA open failure in the container.
A loop that greps for `ERROR` reports every green run as red. Grep `[test] PASS`
or use `$?`. Verified 2026-09-04: `command_bus_test.gd` passes with four `ERROR:`
lines after it.

- `-e HOME` is required with `--user`, or Godot SIGSEGVs creating `/.local`.
- The GDExtension `.so` is prebuilt in `godot/project/bin/`. A fresh worktree has
  neither it nor `.godot`, so a loop there fails for the wrong reason.
- pytest needs numpy for the terrain-bake suites; without it they abort collection
  and take the whole run down. `--ignore` them when numpy is absent.
- Sim, for an end-to-end loop:
  `SCENARIO=<name> CONTENT_DIR=assets/content/google tools/run_e2e.sh up`. Allow
  ~55 s of tile loading before `[main] up`; REST answers on `127.0.0.1:4900`.
  `up` alone needs no SITL when a scripted entity drives the route.

## C++ / colcon / ctest

Prefer the single test target over building the tree — that is the difference
between a 20-second loop and a four-minute one nobody re-runs.

A project MCP server may expose these directly — `ctest_single`, `ctest_failed`,
`ctest_label`, `colcon_build_package`, `colcon_test_results`. Reach for those
before hand-rolling a docker invocation.

Where a container is built by hand: `g++` older than 13 cannot build C++23
(`<expected>`); use a `gcc:14` container rather than the system compiler.

## GStreamer pipelines

Make the pipeline itself the assertion:

- `fakesink` plus `num-buffers=N` gives a bounded run with an exit code.
- `identity silent=false` or a probe pad prints per-buffer timestamps, so a drop or
  a stall becomes a diff rather than a judgement call.
- Assert on the specific symptom: SSRC and sequence numbers for a wedge, PTS deltas
  for a stall, `GST_DEBUG` at a targeted category rather than a global level.
- A UDP sink pointed at an address the box cannot route produces silence that looks
  like a pipeline fault. Sink to loopback to verify encode, then add the network.

## PX4 SITL + pymavlink

- The gimbal link is stock in SITL: `mavlink start -x -u 13030 -f -m gimbal -o
  13280`, its own port and stream set, independent of the 14540 pose link.
- **One socket only.** PX4 retargets its stream to the source address of anything it
  hears on that link, so replying from a second socket moves the stream to an
  ephemeral port for the rest of PX4's life. This looks exactly like a dead link.
  Bind the port and transmit from the same socket.
- **pymavlink's default dialect is `ardupilotmega`**, which has no gimbal protocol
  v2 at all. Neither the `dialect=` kwarg nor `MAVLINK_DIALECT` took effect. What
  works: reassign `link.mav = common.MAVLink(link, srcSystem=..., srcComponent=...)`
  after opening the connection.
- Parameters marked `rebootRequired` ignore a `PARAM_SET` after boot. Gate-dependent
  modules need the autostart `.post` hook, which runs after the gate.
- PX4 image builds need a real clone at the release commit; a git **worktree** fails
  because the version CMake wants genuine `.git` metadata inside the `COPY`.

## Remote Jetson

- `ssh` as the box's own user; `sudo` needs a password on the benches, so a loop
  cannot read `dmesg` or a raw tty non-interactively. Route those through a
  container, or through a service that already runs as root.
- Reverse DNS on the lab subnet lies. Trust the hostname the box reports.
- A managed unit whose `ExecStartPre` does `docker rm -f <name>` will clobber a
  manual container of the same name. Mask the unit before a manual run.
- `journald` logging drivers mean `docker logs` is the wrong place to look if
  storage is disabled; read the journal.
- `docker build` on a kernel without the iptables `raw` table dies during endpoint
  setup. Use `docker build --network=host`.

## Docker traps that cost a loop

- `-v` silently creates a missing bind source, root-owned. Use
  `--mount type=bind,src=...,dst=...` so a wrong path fails loudly.
- A container running as root leaves outputs root-owned; chown back to `1001:1002`
  or the next host-side step fails on permissions.
- A stale image tag is the most common "the fix did nothing": confirm the tag you
  ran is the tag you built.

## Traps that make a passing test meaningless

- A two-layer validator that runs cross-checks **only on a schema-clean document**
  makes a cross-check duplicating a schema rule unreachable through the real entry
  point, while a test helper that runs both layers unconditionally reads green.
  Assert against the schema validator alone when the schema is what you mean to pin.
- A "declared key is consumed somewhere" test greps a fixed set of file types. A key
  read only by a language outside that set reports as dead, and a key only the
  browser reads cannot be guarded at all.
