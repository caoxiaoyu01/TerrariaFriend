using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 只保留智能体经常需要的背包摘要
	public sealed record InventorySnapshot(
		IReadOnlyList<HotbarSlotSummary> Hotbar,
		ArmorSnapshot Armor,
		IReadOnlyList<ItemSummary> Accessories,
		HealingSummary Healing,
		ManaSummary Mana,
		IReadOnlyList<ItemSummary> BossSummons,
		int FreeSlots);
}
