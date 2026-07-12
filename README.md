# Load Gen

Runs Locust workloads from YAML or JSON configuration and generates normalized
CSV files, plots, and a summary.

## Install and commands

```bash
pip install -e .
load-gen preview -c config.yaml
load-gen run -c config.yaml
load-gen plot -c config.yaml
load-gen plot-csv -c config.yaml
load-gen aggregate --experiment-dir path/to/experiment
load-gen compare --experiment baseline=path/to/experiment --experiment candidate=path/to/experiment --output-dir comparison
```

`run` also accepts `--dry-run`. Plot commands accept `--slo-ms`; `plot-csv`
also accepts `--output-dir`.

`aggregate` averages matching time-series samples across the completed runs of
one Experiment Executor experiment and writes canonical CSV files and plots to
its top-level `csv/` and `plots/` directories.

## Configuration

| Key | Default | Description |
| --- | --- | --- |
| `locustfile` | required | Application Locust file |
| `host` | conditional | Base URL; required unless `endpoints` is set |
| `endpoints` | conditional | URL strings or objects with `url`, optional `weight` and `zone` |
| `pattern` | required | Workload pattern |
| `name` | `experiment` | Run directory name |
| `output_dir` | `outputs` | Output root |
| `sample_interval_s` | `1` | Ideal-curve sampling interval |
| `warmup_s` | `0` | Warm-up excluded from normalized metrics |
| `slo_ms` | unset | Response-time SLO |
| `p95_window_s` | `30` | P95 aggregation window |
| `max_users` | peak RPS | Maximum Locust users |
| `spawn_rate` | derived | Locust user spawn rate |
| `stream_locust_output` | `false` | Stream Locust output |
| `exit_code_on_error` | `0` | Locust request-failure exit code |
| `locust_args` | empty | Additional Locust arguments |
| `zone_distribution` | unset | Optional traffic distribution across endpoint zones |
| `kubernetes` | disabled | Optional replica and scheduling sampler |

Paths are resolved relative to the config file. See
[`examples/onlineboutique-mixed/config.yaml`](examples/onlineboutique-mixed/config.yaml).

## Patterns

Supported workload pattern types:

- `constant`: `rps`, `duration`
- `sinusoidal`: `baseline_rps`, `amplitude_rps`, `period`, `duration`
- `exponential`: `start_rps`, `end_rps`, `curve`, `duration`
- `mixed`: ordered `parts`

Durations accept `h`, `m`, and `s`. Mixed parts may override `endpoints`.

Zone distributions use explicit zone weights:

- `constant_weights`: fixed `weights` mapping;
- `linear_weights`: linearly interpolated `start_weights` and `end_weights`.

Weights must be non-negative and have a positive total. Omitted endpoint zones
receive zero traffic. Weighted transitions can therefore move traffic directly
between two zones without sending requests through other zones.

## Kubernetes sampling

| Key | Default | Description |
| --- | --- | --- |
| `kubernetes.enabled` | `false` | Enables sampling |
| `kubernetes.namespace` | required when enabled | Namespace to inspect |
| `kubernetes.sample_interval_s` | `5` | Polling interval |
| `kubernetes.selector` | empty | Deployment and Pod label selector |
| `kubernetes.kubeconfig` | default config | Optional kubeconfig path |

## Outputs

Results are written below `output_dir/name`:

- `generated/` — generated Locust files
- `locust/` — raw Locust output
- `csv/` — normalized workload, response-time, failure, replica, and scheduling data
- `plots/` — PDF and PNG plots
- `summary.json` — run summary

Comparisons include a windowed P95 time-series overlay and an `overall_p95`
bar chart based on Locust's cumulative whole-run P95.

Suite comparisons generate time-series overlays for input rate, successful
throughput, failed request rate, windowed P95 response time, and total replica
count. Summary bars compare failure percentage, whole-experiment P95, mean
throughput, mean pod creation-to-scheduled time, and mean replica count. The
scheduling value uses Kubernetes Pod timestamps and is therefore a coarse
end-to-end measurement rather than scheduler execution latency. Failure percentage is
computed as `failed / (successful + failed) * 100` from the normalized rates.
Individual runs and single-experiment aggregates additionally include
`replicas_by_service` CSV and plot artifacts; these are intentionally omitted
from suite overlays to keep cross-experiment comparisons readable.
