using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

namespace TerrariaFriend.Triggering
{
	// 玩家生命周期 Hook 负责无法从持续状态中精确表达的一次性事件
	public sealed class TriggerPlayer : ModPlayer
	{
		// 玩家死亡时由 tModLoader 调用
		public override void Kill(
			double damage,
			int hitDirection,
			bool pvp,
			PlayerDeathReason damageSource)
		{
			// 只提交当前客户端本地玩家的死亡事件
			if (Player.whoAmI != Main.myPlayer) return;

			// 统一交给 TriggerSystem 进入后续调度
			TriggerSystem.SubmitGameEvent(new GameEvent(
				GameEventType.PlayerDied,
				Player.whoAmI.ToString(),
				Player.name));
		}
	}
}
