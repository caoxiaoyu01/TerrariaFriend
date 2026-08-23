using System.Collections.Generic;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;

namespace TerrariaFriend.GameState.Tracking
{
	// 记录关键区域并在服务端保存多人探索格网
	public class ExplorationTracker : ModSystem
	{
		private const uint CheckIntervalTicks = 60;
		private const float PixelsPerTile = 16f;
		private readonly Dictionary<int, ExplorationCell> _lastServerCells = new Dictionary<int, ExplorationCell>();

		public override void OnWorldLoad()
		{
			_lastServerCells.Clear();
		}

		public override void OnWorldUnload()
		{
			_lastServerCells.Clear();
		}

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

				if (Main.netMode == NetmodeID.Server)
				{
					TrackServerCell(player, worldState);
				}
			}
		}

		private void TrackServerCell(Player player, CompanionWorldState worldState)
		{
			ExplorationCell cell = new ExplorationCell(
				(int)(player.Center.X / PixelsPerTile / ExplorationGridTracker.ExplorationCellSize),
				(int)(player.Center.Y / PixelsPerTile / ExplorationGridTracker.ExplorationCellSize));

			if (_lastServerCells.TryGetValue(player.whoAmI, out ExplorationCell lastCell)
				&& lastCell == cell)
			{
				return;
			}

			_lastServerCells[player.whoAmI] = cell;
			worldState.MarkCellVisited(cell);
		}
	}
}
