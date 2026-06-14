# Load Gen

Load Gen is a small Locust-based experiment helper for paper-oriented autoscaling experiments.

The intended workflow is:

1. Each application keeps its own normal `locustfile.py`.
2. Each experiment has one YAML config describing the target host, workload pattern, output directory, and optional Kubernetes replica sampling.
3. Load Gen generates a temporary Locust wrapper with a `LoadTestShape`, runs Locust headless, normalizes CSVs, and emits paper-ready plots.

Load Gen treats workload `rps` values as target HTTP request starts per second. It generates a Locust `LoadTestShape`, keeps enough active users available, and globally paces outgoing HTTP requests to the configured curve. The **actual RPS** plot comes from Locust's measured CSV history.

## Install

From this directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

This installs the `load-gen` command.

## Commands

Preview the configured workload:

```bash
load-gen preview -c examples/onlineboutique-mixed/config.yaml
```

The same example is also available as JSON at `examples/onlineboutique-mixed/config.json`.

Run an experiment:

```bash
load-gen run -c examples/onlineboutique-mixed/config.yaml
```

Regenerate plots for an existing run:

```bash
load-gen plot -c examples/onlineboutique-mixed/config.yaml
```

Regenerate plots from normalized experiment CSVs:

```bash
load-gen plot-csv -c examples/onlineboutique-mixed/config.yaml
```

Recompute windowed p95 from Locust history before plotting. The window is read from `p95_window_s` in the config:

```bash
load-gen plot-csv -c examples/onlineboutique-mixed/config.yaml
```

The config is always the reference. Load Gen resolves it to `output_dir/name`, and uses config values such as `slo_ms` and `p95_window_s` when regenerating plots.

## Pattern Types

Constant:

```yaml
pattern:
  type: constant
  rps: 100
  duration: 10m
```

Sinusoidal:

```yaml
pattern:
  type: sinusoidal
  baseline_rps: 180
  amplitude_rps: 120
  period: 10m
  duration: 30m
```

Exponential:

```yaml
pattern:
  type: exponential
  start_rps: 50
  end_rps: 450
  curve: 3.0
  duration: 10m
```

Mixed:

```yaml
pattern:
  type: mixed
  parts:
    - type: constant
      rps: 70
      duration: 5m
    - type: sinusoidal
      baseline_rps: 185
      amplitude_rps: 115
      period: 10m
      duration: 20m
```

Durations support `h`, `m`, and `s`, including combinations such as `1h30m`.

## Outputs

Each experiment directory contains:

| Path | Meaning |
|------|---------|
| `config.yaml` / `config.json` | Experiment configuration |
| `output/generated/locustfile.py` | Temporary Locust wrapper with the generated load shape |
| `output/generated/app_locustfile.py` | Copy of the application Locust file used for the run |
| `output/locust/locust_stats_history.csv` | Raw Locust history CSV |
| `output/locust/locust_stats.csv` | Raw Locust aggregate stats CSV |
| `output/csv/ideal_rps.csv` | Configured target RPS over experiment minutes |
| `output/csv/actual_rps.csv` | Delivered RPS from Locust history |
| `output/csv/failure_rate.csv` | Failures per second from Locust history |
| `output/csv/p95_response_time.csv` | Windowed P95 response time from Locust history |
| `output/csv/replicas.csv` | Optional deployment replicas sampled with `kubectl` |
| `output/plots/*.png` | Paper-friendly plots |
| `output/preview/csv/ideal_rps.csv` | Preview-only ideal workload CSV |
| `output/preview/plots/ideal_rps.png` | Preview-only ideal workload plot |
| `output/summary.json` | Mean, max, and last values for the collected metrics |

Plots use minutes on the x axis and a compact academic style suitable for papers. Figures use the same squarer scale as the project reference P95 plot, with lines kept slightly heavier than axes and gridlines so trends remain visible after scaling into a paper column.

## Kubernetes Replica Sampling

Replica sampling is optional. Enable it when you want per-service and total replica plots:

```yaml
kubernetes:
  enabled: true
  namespace: default
  sample_interval_s: 5
  selector: app.kubernetes.io/part-of=onlineboutique
  kubeconfig: ../../kubeconfig-am-cluster-01
```

The sampler uses:

```bash
kubectl get deployments -n <namespace> -o json
```

It writes one row per deployment plus a `__total__` row at each sample.

## Configuration Reference

Required keys:

| Key | Description |
|-----|-------------|
| `locustfile` | Path to the application Locust file, relative to the config file |
| `host` | Application base URL passed to Locust |
| `pattern` | Workload pattern |

Useful optional keys:

| Key | Default | Description |
|-----|---------|-------------|
| `name` | `experiment` | Experiment directory name |
| `output_dir` | `outputs` | Output root, relative to the config file. Use `output` when the config lives in the experiment directory |
| `sample_interval_s` | `1` | Ideal workload CSV sample interval |
| `slo_ms` | unset | Draws an SLO line on the P95 plot |
| `p95_window_s` | `30` | Window duration for `p95_response_time.csv` and summary windowed p95 |
| `max_users` | peak RPS | Maximum Locust users available to drive the request-rate throttle |
| `spawn_rate` | `min(max_users, 100)` | Locust user ramp-up rate |
| `stream_locust_output` | `false` | Stream Locust stdout/stderr instead of writing `output/locust/locust.log` |
| `exit_code_on_error` | `0` | Locust process exit code when requests fail |
| `locust_args` | `[]` | Extra arguments appended to the Locust command |
