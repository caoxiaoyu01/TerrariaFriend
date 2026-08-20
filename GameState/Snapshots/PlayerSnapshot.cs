using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 玩家当前属性和移动状态 快照
	public sealed record PlayerSnapshot(
		int PlayerId,
		string Name,
		// 生命，魔力 防御
		bool IsDead,
		int Life,
		int MaxLife,
		int Mana,
		int MaxMana,
		int Defense,
		// 位置
		float PositionTileX,
		float PositionTileY,
		// 速度
		float VelocityTilesPerSecondX,
		float VelocityTilesPerSecondY,
		int Direction,
		// 有没有坐骑
		bool IsMounted,
		// 憋气上限
		int Breath,
		int MaxBreath,
		ItemSummary HeldItem,
		IReadOnlyList<BuffSummary> Buffs);

	public sealed record BuffSummary(
		int TypeId,
		string Name,
		bool IsDebuff,
		int RemainingTicks);
}
