namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record HotbarSlotSummary(
		int SlotIndex,
		ItemSummary Item);
}
