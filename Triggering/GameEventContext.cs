#nullable enable

using System.Collections.Generic;

namespace TerrariaFriend.Triggering
{
	// GAME_EVENT 判断所需的轻量即时上下文
	public sealed record GameEventContext(
		int? NearbyEnemyCount = null,
		string? ProgressionStage = null,
		int? OccurrenceCount = null,
		IReadOnlyList<string>? ActiveEvents = null,
		string? Biome = null,
		string? Layer = null,
		string? SpecialScene = null,
		string? PreviousBiome = null,
		string? PreviousLayer = null,
		string? PreviousSpecialScene = null,
		bool? IsNearby = null,
		bool? BossActive = null,
		string? BossName = null,
		int? DamageTakenLast5s = null,
		string? LastDamageSource = null);
}
