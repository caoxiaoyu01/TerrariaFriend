using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

namespace TerrariaFriend.Triggering
{
	// 玩家生命周期回调用来捕获死亡等一次性事件
	public sealed class TriggerPlayer : ModPlayer
	{
		// 玩家死亡时由模组加载器调用
		public override void Kill(
			double damage,
			int hitDirection,
			bool pvp,
			PlayerDeathReason damageSource)
		{
			// 只提交当前客户端本地玩家的死亡事件
			if (Player.whoAmI != Main.myPlayer) return;

			// 交给统一的触发系统继续处理
			TriggerSystem.SubmitGameEvent(new GameEvent(
				GameEventType.PlayerDied,
				Player.whoAmI.ToString(),
				Player.name));
		}
	}
}
