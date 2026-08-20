namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record BossCombatSummary(
		int TypeId,
		string Name,
		float LifeRatio);
}
