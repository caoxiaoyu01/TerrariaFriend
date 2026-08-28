import json
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.errors import EdgeNotFoundError
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode

from agent.memory.graphiti.client import create_graphiti
from agent.memory.ports import MemoryEpisode, MemoryEvidenceEpisode, MemoryTriplet


class GraphitiMemoryBackend:
    """负责读写图结构的长期记忆"""

    def __init__(
        self,
        client: Graphiti | None = None,
        *,
        client_factory: Callable[[], Graphiti] = create_graphiti,
    ) -> None:
        self._client = client
        self._client_factory = client_factory

    @property
    def client(self) -> Graphiti:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    async def initialize(self) -> None:
        await self.client.build_indices_and_constraints()

    async def add_episode(self, episode: MemoryEpisode) -> Any:
        source = EpisodeType.json if episode.source == "json" else EpisodeType.text
        return await self.client.add_episode(
            name=episode.name,
            episode_body=episode.body,
            source=source,
            source_description=episode.source_description,
            reference_time=episode.reference_time,
            group_id=episode.group_id,
        )

    async def search(
        self,
        query: str,
        *,
        group_ids: list[str],
        num_results: int = 10,
    ) -> list[Any]:
        return await self.client.search(
            query,
            group_ids=group_ids,
            num_results=num_results,
        )

    async def upsert_evidence_episode(
        self,
        episode: MemoryEvidenceEpisode,
    ) -> None:
        """直接保存明确的证据来源 不让模型再次提取"""

        node = EpisodicNode(
            uuid=episode.episode_id,
            name=f"l1-evidence-{episode.episode_id}",
            group_id=episode.group_id,
            source=EpisodeType.json,
            source_description="TerrariaFriend L2 relation evidence",
            content=json.dumps(
                {
                    "kind": "terrariafriend_l1_evidence",
                    "episode_id": episode.episode_id,
                    "occurred_at": episode.occurred_at.isoformat(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            valid_at=episode.occurred_at,
        )
        await node.save(self.client.driver)

    async def upsert_memory_triplet(self, triplet: MemoryTriplet) -> Any:
        source = EntityNode(
            uuid=triplet.source_uuid,
            name=triplet.source_name,
            group_id=triplet.group_id,
            labels=["Player"],
        )
        target = EntityNode(
            uuid=triplet.target_uuid,
            name=triplet.target_name,
            group_id=triplet.group_id,
            labels=["MemoryObject"],
        )
        evidence_ids = list(dict.fromkeys(triplet.evidence_episode_ids))
        attributes = dict(triplet.attributes)
        valid_at = triplet.valid_at
        reference_time = triplet.reference_time
        created_at = datetime.now(timezone.utc)
        expired_at = None
        invalid_at = None
        try:
            existing = await EntityEdge.get_by_uuid(
                self.client.driver,
                triplet.edge_uuid,
            )
            evidence_ids = list(dict.fromkeys([*existing.episodes, *evidence_ids]))
            attributes = {**existing.attributes, **attributes}
            attributes["evidenceEpisodeIds"] = evidence_ids
            valid_at = min(existing.valid_at or valid_at, valid_at)
            reference_time = max(
                existing.reference_time or reference_time,
                reference_time,
            )
            created_at = existing.created_at
            expired_at = existing.expired_at
            invalid_at = existing.invalid_at
        except EdgeNotFoundError:
            pass

        # 旧数据可能只有关系而没有对应的证据节点
        # 保存关系前补齐它引用的全部证据节点
        await self._ensure_evidence_nodes(
            evidence_ids,
            group_id=triplet.group_id,
            fallback_occurred_at=valid_at,
        )

        edge = EntityEdge(
            uuid=triplet.edge_uuid,
            group_id=triplet.group_id,
            source_node_uuid=source.uuid,
            target_node_uuid=target.uuid,
            created_at=created_at,
            name=triplet.relation_type,
            fact=triplet.fact,
            episodes=evidence_ids,
            expired_at=expired_at,
            valid_at=valid_at,
            invalid_at=invalid_at,
            reference_time=reference_time,
            attributes=attributes,
        )
        result = await self.client.add_triplet(source, edge, target)
        resolved_edge_uuid = result.edges[0].uuid if result.edges else edge.uuid
        for episode_id in evidence_ids:
            episode = await EpisodicNode.get_by_uuid(
                self.client.driver,
                episode_id,
            )
            if resolved_edge_uuid not in episode.entity_edges:
                episode.entity_edges.append(resolved_edge_uuid)
                await episode.save(self.client.driver)
        return result

    async def _ensure_evidence_nodes(
        self,
        episode_ids: list[str],
        *,
        group_id: str,
        fallback_occurred_at: datetime,
    ) -> None:
        existing_nodes = await EpisodicNode.get_by_uuids(
            self.client.driver,
            episode_ids,
        )
        existing_by_id = {node.uuid: node for node in existing_nodes}
        for node in existing_nodes:
            if node.group_id != group_id:
                raise ValueError(
                    f"evidence {node.uuid} group_id 与 memory edge 不一致"
                )

        for episode_id in episode_ids:
            if episode_id in existing_by_id:
                continue
            # 为旧关系补建缺失的证据节点
            # 沿用原标识并使用关系最早生效时间
            recovered = EpisodicNode(
                uuid=episode_id,
                name=f"l1-evidence-{episode_id}",
                group_id=group_id,
                source=EpisodeType.json,
                source_description="TerrariaFriend recovered L1 evidence provenance",
                content=json.dumps(
                    {
                        "kind": "terrariafriend_l1_evidence_recovered",
                        "episode_id": episode_id,
                        "occurred_at": fallback_occurred_at.isoformat(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                valid_at=fallback_occurred_at,
            )
            await recovered.save(self.client.driver)

        verified = await EpisodicNode.get_by_uuids(
            self.client.driver,
            episode_ids,
        )
        verified_ids = {node.uuid for node in verified}
        missing = [episode_id for episode_id in episode_ids if episode_id not in verified_ids]
        if missing:
            raise RuntimeError(
                "Graphiti evidence EpisodicNode save verification failed: "
                + ", ".join(missing)
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
