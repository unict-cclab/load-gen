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
load-gen compare --experiment baseline=path/to/experiment --experiment candidate=path/to/experiment --output-dir comparison
```

`run` also accepts `--dry-run`. Plot commands accept `--slo-ms`; `plot-csv`
also accepts `--output-dir`.

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
