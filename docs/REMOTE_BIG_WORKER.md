# Proposal: a big remote worker on SER9

Status: not deployed. Nothing on SER9 has these settings.
`--config=remote-exec-big` fails after 300 s until the worker exists.

## Required change in any case

A Node 26 action needs more than 1800 s. More CPUs may not fix that, so raise the limit first.
A rule cannot set the action timeout. Bazel 9.1.1 removes the key.

In devlayer, `workloads/bazel/config/scheduler.jsonnet`:

```
defaultExecutionTimeout: '7200s',
```

This also applies to every other action on the scheduler. A stuck action can hold a slot for 2 hours, not 30 minutes.

## Optional: the big pool

- Add a second runner and worker in `workloads/bazel`, with the property `pool=big`.
- Set `concurrency: 1`, and caps of 10 CPUs and 12 GiB.
- Set `jobs` to 10 for this platform in `node/defs.bzl`. The action key changes.
- Do not cap at 16 GiB. The host has 31 GiB and no swap, and it uses 14 to 21 GiB.
- Stop the GHA runners during a big build, or accept the risk of memory pressure.

Expected gain, not measured: Node 16 from 12.6 min to 6 or 7 min.

## Deploy plan

1. Hold `RELEASE.LOCK`.
2. Make a rollback snapshot.
3. Check that no Bazel build is running. A scheduler restart stops builds in flight.
4. Deploy the configuration.
5. Run `bazel build --config=remote-exec //node:rootbeer_26`.
6. Log the result in PROGRESS.md.

Rollback: restore the snapshot, and restart the scheduler.
