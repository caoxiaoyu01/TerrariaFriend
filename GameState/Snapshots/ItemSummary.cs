namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record ItemSummary(
		int TypeId,
		string Name,
		int Stack)
	{
		public static readonly ItemSummary Empty = new(0, "Empty", 0);
	}
}
