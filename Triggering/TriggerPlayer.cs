using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

namespace TerrariaFriend.Triggering
{
	// 玩家生命周期 Hook 负责无法从持续状态中精确表达的一次性事件。
	public sealed class TriggerPlayer : ModPlayer
	{
		public override void Kill(
			double damage,
			int hitDirection,
			bool pvp,
			PlayerDeathReason damageSource)
		{
			if (Player.whoAmI != Main.myPlayer) return;

			TriggerSystem.SubmitGameEvent(new GameEvent(
				GameEventType.PlayerDied,
				Player.whoAmI.ToString(),
				Player.name));
		}
	}
}
