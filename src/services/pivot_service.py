from src.schemas.domain import PivotSuggestion
from src.services.query_builder import build_query


def suggest_pivot(field_type: str, value: str) -> PivotSuggestion:
    """Turn a result field into a ready-to-run seeded search.

    build_query raises ValueError for non-whitelisted (non-pivotable) fields.
    That error is intentionally left to propagate — it IS the non-pivotable signal.
    """
    query = build_query(field_type, value)
    return PivotSuggestion(field_type=field_type, value=value, query=query)
