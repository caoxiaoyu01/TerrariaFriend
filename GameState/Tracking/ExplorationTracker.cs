using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;

namespace TerrariaFriend.GameState.Tracking
{
	// 在服务端记录玩家首次到达的关键区域。
	public class ExplorationTracker : ModSystem
	{
		private const uint CheckIntervalTicks = 60;

		public override void PostUpdatePlayers()
		{
			if (Main.netMode == NetmodeID.MultiplayerClient) return;
			if (Main.GameUpdateCount % CheckIntervalTicks != 0) return;

			CompanionWorldState worldState = ModContent.GetInstance<CompanionWorldState>();
			for (int i = 0; i < Main.maxPlayers; i++)
			{
				Player player = Main.player[i];
				if (!player.active) continue;

				if (player.ZoneJungle) worldState.MarkVisited("Jungle");
				if (player.ZoneDungeon) worldState.MarkVisited("Dungeon");
				if (player.ZoneUnderworldHeight) worldState.MarkVisited("Underworld");
				if (player.ZoneSkyHeight) worldState.MarkVisited("Sky");
				if (player.ZoneBeach) worldState.MarkVisited("Ocean");
				if (player.ZoneLihzhardTemple) worldState.MarkVisited("Temple");
				if (player.ZoneShimmer) worldState.MarkVisited("Shimmer");
				if (player.ZoneSnow) worldState.MarkVisited("Snow");
				if (player.ZoneDesert) worldState.MarkVisited("Desert");
			}
		}
	}
}
