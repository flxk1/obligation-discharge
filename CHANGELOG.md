# Changelog

## 0.1.0

First release.

- `admit` — XACML 3.0's rule kept intact: a permit carrying a mandatory
  obligation the enforcement point cannot discharge must be denied. Silence
  counts as inability.
- `settle` — whether accepted duties were performed, and on time.
- `fitness` — which duties in a policy an enforcement point cannot carry,
  answerable before any request exists.
- `obligations=None` is `UNDETERMINED`, never permissive.
