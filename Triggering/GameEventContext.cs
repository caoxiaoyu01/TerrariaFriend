#nullable enable

using System.Collections.Generic;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 游戏事件判断所需的轻量即时上下文
	public sealed record GameEventContext(
		int? NearbyEnemyCount = null,
		string? ProgressionStage = null,
		int? OccurrenceCount = null,
		IReadOnlyList<string>? ActiveEvents = null,
		IReadOnlyList<string>? Biomes = null,
		string? Layer = null,
		IReadOnlyList<string>? MiniBiomes = null,
		IReadOnlyList<string>? SpecialAreas = null,
		IReadOnlyList<string>? PreviousBiomes = null,
		string? PreviousLayer = null,
		IReadOnlyList<string>? PreviousMiniBiomes = null,
		IReadOnlyList<string>? PreviousSpecialAreas = null,
		bool? IsNearby = null,
		bool? BossActive = null,
		string? BossName = null,
		int? DamageTakenLast5s = null,
		string? LastDamageSource = null,
		ArmorSnapshot? ArmorBefore = null,
		ArmorSnapshot? ArmorAfter = null,
		IReadOnlyList<ItemSummary>? AccessoriesAdded = null,
		IReadOnlyList<ItemSummary>? AccessoriesRemoved = null);
}
