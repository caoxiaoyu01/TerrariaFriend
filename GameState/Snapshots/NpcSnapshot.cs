#nullable enable

using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 当前世界中的重要 NPC，以及玩家附近的重要 NPC。
	public sealed record NpcSnapshot(
		int TownNpcCount,
		IReadOnlyList<TownNpcSummary> TownNpcs,
		int NearbyTownNpcCount,
		IReadOnlyList<NearbyTownNpcSummary> NearbyTownNpcs,
		int SpecialNpcCount,
		IReadOnlyList<SpecialNpcSummary> SpecialNpcs,
		bool BossActive,
		int ActiveBossCount,
		IReadOnlyList<BossSummary> ActiveBosses);

	public sealed record TownNpcSummary(
		int TypeId,
		string Name,
		bool IsHomeless,
		int Life,
		int LifeMax);

	public sealed record NearbyTownNpcSummary(
		int TypeId,
		string Name,
		float Distance,
		int Life,
		int LifeMax,
		bool IsHomeless);

	public sealed record SpecialNpcSummary(
		int TypeId,
		string Name,
		bool IsNearby,
		float? Distance,
		int Life,
		int LifeMax);

	public sealed record BossSummary(
		int TypeId,
		string Name,
		int Life,
		int LifeMax,
		float LifeRatio,
		float Distance,
		bool IsNearby);
}
