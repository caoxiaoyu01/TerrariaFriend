using System.Collections.Generic;
using Terraria;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class PlayerCollector
	{
		private const float PixelsPerTile = 16f;
		private const float TicksPerSecond = 60f;

		// 复制一份玩家状态 避免后台请求读取正在变化的游戏对象
		public static PlayerSnapshot Capture(Player player)
		{
			List<BuffSummary> buffs = new List<BuffSummary>();
			for (int i = 0; i < player.buffType.Length; i++)
			{
				int type = player.buffType[i];
				if (type > 0 && player.buffTime[i] > 0)
				{
					buffs.Add(new BuffSummary(type, Lang.GetBuffName(type), Main.debuff[type], player.buffTime[i]));
				}
			}

			return new PlayerSnapshot(
				player.whoAmI,
				player.name,
				player.dead,
				player.statLife,
				player.statLifeMax2,
				player.statMana,
				player.statManaMax2,
				player.statDefense,
				player.Center.X / PixelsPerTile,
				player.Center.Y / PixelsPerTile,
				player.velocity.X * TicksPerSecond / PixelsPerTile,
				player.velocity.Y * TicksPerSecond / PixelsPerTile,
				player.direction,
				player.mount.Active,
				player.breath,
				player.breathMax,
				InventoryCollector.CreateItemSummary(player.HeldItem),
				buffs);
		}
	}
}
