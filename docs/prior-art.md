# Prior art

## Prior art

XACML 3.0 §7.18 defines obligations and the discharge rule this package keeps.
Its implementations bind that rule to XACML's XML policy language and PDP.
What is unpackaged is the decision itself, usable with the engines that
dropped it — hence a standalone function over plain data.

[AuthZEN Authorization API 1.0](https://openid.net/specs/authorization-api-1_0-01.html)
defines `reason_admin`/`reason_user` and no obligations.
[Deontic Policies for Runtime Governance of Agentic AI Systems](https://arxiv.org/pdf/2606.19464)
(2026) argues these duties are "structurally inexpressible in allow/deny or
ABAC rule engines". Deontic vocabularies such as DPV and ODRL name what a duty
*is*; this package decides whether one can be carried.
