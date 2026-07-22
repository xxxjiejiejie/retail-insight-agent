from pydantic import BaseModel, Field


class RunMetrics(BaseModel):
    route: str
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0)
    cache_hit: bool = False
    error_code: str | None = None
