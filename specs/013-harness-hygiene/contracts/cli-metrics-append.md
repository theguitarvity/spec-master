# Contract: `metrics record-round --append`

```
python3 spec-master/lib/cli.py metrics record-round --round-id ID --phase P \
  --started-at ISO --ended-at ISO [--input-tokens N] [--output-tokens N] \
  [--work-packages-completed N] [--features-completed N] [--notes TEXT] \
  [--feature-id ID] [--tier XS|S|M|L|XL] [--append FILE]
```

| Case | stdout | FILE after | exit |
|---|---|---|---|
| no `--append` | row JSON (unchanged) | untouched | 0 |
| `--append`, FILE missing | row JSON | `[row]` (parent dir created) | 0 |
| `--append`, FILE is a JSON array | row JSON | previous rows + row (last) | 0 |
| `--append`, FILE invalid JSON or root not an array | nothing | untouched | 1, error on stderr |

Write is temp-file in the same directory + `os.replace`; concurrent appenders are serialised by an advisory `fcntl.flock` on the parent directory when the platform supports `fcntl`.

Library: `metrics.append_round(path: str, row: dict) -> list[dict]` returns the new array; raises `ValueError` on invalid content.
