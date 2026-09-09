# Tests and conformance

## Tests

```
pytest -q
python conformance/run_conformance.py
```

The conformance vectors in `conformance/vectors.json` are the specification:
any implementation reproducing those verdicts is conformant. They construct
positionally, which is deliberate — a field inserted into the middle of a
dataclass rebinds every positional caller, and keyword-using tests cannot see
it.
