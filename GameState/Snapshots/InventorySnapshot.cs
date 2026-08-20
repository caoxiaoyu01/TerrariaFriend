using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 只保留 Agent 高频决策需要的轻量背包摘要
	public sealed record InventorySnapshot(
		IReadOnlyList<HotbarSlotSummary> Hotbar,
		ArmorSnapshot Armor,
		IReadOnlyList<ItemSummary> Accessories,
		HealingSummary Healing,
		ManaSummary Mana,
		IReadOnlyList<ItemSummary> BossSummons,
		int FreeSlots);
}
