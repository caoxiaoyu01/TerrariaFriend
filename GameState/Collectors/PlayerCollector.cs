using System.Collections.Generic;
using Terraria;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class PlayerCollector
	{
		private const float PixelsPerTile = 16f;
		private const float TicksPerSecond = 60f;

		// 复制玩家当前属性，避免异步 Agent 直接读取实时 Player
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
