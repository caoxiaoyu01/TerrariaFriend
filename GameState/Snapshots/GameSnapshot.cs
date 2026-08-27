namespace TerrariaFriend.GameState.Snapshots
{
	// 智能体一次思考所使用的完整游戏快照
	public sealed record GameSnapshot(
		uint Tick,
		PlayerSnapshot Player,
		InventorySnapshot Inventory,
		WorldSnapshot World,
		ProgressSnapshot Progress,
		SceneSnapshot Scene,
		CombatSnapshot Combat,
		NpcSnapshot Npc);
}
