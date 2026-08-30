import httpx

from graphiti_core.cross_encoder.client import CrossEncoderClient


class ApiRerankerClient(CrossEncoderClient):
    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.endpoint = f"{base_url.rstrip('/')}/rerank"
        self.model = model

    async def rank(
        self,
        query: str,
        passages: list[str],
    ) -> list[tuple[str, float]]:
        if not passages:
            return []
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "query": query,
                    "documents": passages,
                    "top_n": len(passages),
                },
            )
            response.raise_for_status()
        results = response.json().get("results", [])
        return [
            (passages[item["index"]], float(item["relevance_score"]))
            for item in results
            if 0 <= item.get("index", -1) < len(passages)
        ]
