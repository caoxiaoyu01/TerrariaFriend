using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 玩家当前以及最近五秒的战斗上下文
	public sealed record CombatSnapshot(
		bool InCombat,
		float CombatDurationSeconds,
		bool BossActive,
		IReadOnlyList<BossCombatSummary> ActiveBosses,
		int NearbyEnemyCount,
		// 血条比例
		float HpRatio,
		RecentDamageSnapshot RecentDamage);
}
