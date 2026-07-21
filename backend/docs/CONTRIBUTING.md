# Contributing Guide

## Code Standards

This project follows **Clean Architecture** with strict SOLID principles.

### Rules
- **Never** write business logic in routers or controllers
- **Always** define an interface (`I*`) before an implementation
- Business logic lives in `services/`, data access in `repositories/`
- API contracts are defined in `schemas/`

### Adding a New Domain Feature

1. Define Pydantic schemas in `app/schemas/{domain}.py`
2. Add SQLAlchemy model in `app/models/{domain}.py` and register in `app/models/__init__.py`
3. Define repository interface in `app/repositories/interfaces/{domain}_repo.py`
4. Implement repository in `app/repositories/{domain}_repo_impl.py`
5. Define service interface in `app/services/interfaces/{domain}_service.py`
6. Implement service in `app/services/{domain}_service_impl.py`
7. Add dependency factories in `app/dependencies/services.py` and `app/dependencies/repositories.py`
8. Write controller in `app/api/v1/controllers/{domain}_controller.py`
9. Write router in `app/api/v1/routers/{domain}_router.py`
10. Register router in `app/api/v1/router.py`
11. Generate Alembic migration: `alembic revision --autogenerate -m "add_{domain}"`

### Code Style
```bash
ruff check app/    # Lint
ruff format app/   # Format
mypy app/          # Type checking
pytest tests/ -v   # Tests
```
