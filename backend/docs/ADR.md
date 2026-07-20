# Architecture Decision Records (ADR)

This document records the key architectural decisions made during backend development.

---

## ADR-001 — Clean Architecture with Dependency Inversion

**Date:** 2025-01-01  
**Status:** Accepted

### Context
The platform needs to support multiple ML models, 12 AI agents, several weather data sources, and 5+ hazard types. Without a clear separation of concerns, the codebase would become impossible to test or extend.

### Decision
Adopt **Clean Architecture**:
- `routers/` — HTTP concerns only (no business logic)
- `controllers/` — Bridge between HTTP and services
- `services/` — All business logic, defined by interfaces (`IAuthService`, etc.)
- `repositories/` — Data access only, defined by interfaces (`IUserRepository`, etc.)
- `models/` — Database schema only

Every layer depends on abstractions, not concretions (Dependency Inversion Principle).

### Consequences
- Every component is independently unit-testable with mocked dependencies
- Adding a new ML model, weather source, or database backend requires no changes to service code
- Slightly more boilerplate for simple CRUD, but worth it at this scale

---

## ADR-002 — Pydantic v2 Settings with `lru_cache`

**Date:** 2025-01-01  
**Status:** Accepted

### Context
Environment configuration must be immutable, type-safe, and not cause module-level side effects.

### Decision
Use `pydantic-settings` with nested model groups (`Settings.database`, `Settings.security`, etc.) and `@lru_cache(maxsize=1)` on `get_settings()` to create a true singleton.

### Consequences
- `get_settings()` can be imported anywhere without re-reading `.env`
- In tests, override by patching `get_settings` return value

---

## ADR-003 — JWT Stateless Auth with Redis Blacklist

**Date:** 2025-01-01  
**Status:** Accepted

### Context
JWT tokens cannot be invalidated server-side without either keeping state or accepting a logout-does-nothing model.

### Decision
- Include a `jti` (JWT ID) claim in every access token
- On logout, write the `jti` to Redis with a TTL equal to the token's remaining lifetime
- On every authenticated request, check `EXISTS blacklist:{jti}` in Redis (single O(1) command)

### Consequences
- Near-zero overhead per request (Redis lookup < 1ms)
- Instant token revocation (e.g., on logout, password change, account compromise)
- Redis is a non-critical dependency for auth — if Redis fails open, auth degrades gracefully to non-revocable tokens

---

## ADR-004 — Prometheus Bounded Cardinality Labels

**Date:** 2025-01-01  
**Status:** Accepted

### Context
Prometheus OOM is caused by unbounded label cardinality. If path labels include UUIDs, every unique user ID creates a new time series.

### Decision
- Normalize all path labels by replacing UUID/numeric segments with `{id}` (done in `TimingMiddleware._normalize_path`)
- Constrain model/agent labels to bounded enums (max ~15 values each)
- Never label on user IDs, IPs, or request payloads

### Consequences
- Prometheus memory stays predictable regardless of traffic volume
- p99 latency percentiles are accurate per-endpoint rather than per-user

---

## ADR-005 — Fail-Open Rate Limiter

**Date:** 2025-01-01  
**Status:** Accepted

### Context
The platform is used by disaster management agencies during active emergencies. Blocking all API traffic because Redis is down would be a life-safety issue.

### Decision
The `RateLimiterMiddleware` **fails open** — if the Redis call raises any exception, the request is allowed through and the error is logged at WARNING level.

### Consequences
- During Redis outages, rate limiting is temporarily disabled
- Malicious actors could exploit a sustained Redis outage window
- This is explicitly acceptable given the disaster management use case

---

## ADR-006 — Celery with asyncio Bridge for Background Workers

**Date:** 2025-01-01  
**Status:** Accepted

### Context
Celery workers run in synchronous Python processes. Our service and repository layers are all `async`. Running sync Celery and needing to call async services creates a conflict.

### Decision
Each Celery task uses a `_run_async(coro)` helper that:
1. Gets or creates an asyncio event loop
2. Runs the coroutine to completion
3. Returns the result synchronously

### Consequences
- Celery tasks can call all async services/repositories cleanly
- One event loop per Celery task (not shared) avoids cross-task contamination
- Slightly more boilerplate in task files but clean separation maintained
