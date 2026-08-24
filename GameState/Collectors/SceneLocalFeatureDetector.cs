using System.Collections.Generic;
using Terraria;
using Terraria.ID;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	// 使用玩家附近的有限 tile 范围补充没有 ZoneXXX 的场景
	internal static class SceneLocalFeatureDetector
	{
		private const int ScanRadiusTiles = 30;
		private const int FeatureTileThreshold = 8;
		private const int StructureTileThreshold = 12;
		private const int WallThreshold = 4;
		private const int OasisWaterThreshold = 12;

		public static void Capture(
			Player player,
			string layer,
			List<string> miniBiomes,
			List<string> specialAreas)
		{
			int centerX = (int)(player.Center.X / 16f);
			int centerY = (int)(player.Center.Y / 16f);
			LocalTileCounts counts = Scan(centerX, centerY);

			if (layer == "Surface" && player.ZoneDesert
				&& counts.OasisPlants > 0 && counts.WaterTiles >= OasisWaterThreshold)
			{
				miniBiomes.Add(SceneFeatureNames.MiniBiome.Oasis);
			}

			if (counts.SpiderWalls >= WallThreshold)
				miniBiomes.Add(SceneFeatureNames.MiniBiome.SpiderNest);
			if (counts.GlowingMossTiles >= FeatureTileThreshold)
				miniBiomes.Add(SceneFeatureNames.MiniBiome.GlowingMoss);
			if (layer == "Underworld" && counts.AshForestTiles >= FeatureTileThreshold)
				miniBiomes.Add(SceneFeatureNames.MiniBiome.AshForest);

			if (counts.LivingWoodWalls >= WallThreshold)
				specialAreas.Add(SceneFeatureNames.SpecialArea.LivingTree);
			if (player.ZoneJungle && counts.LivingMahoganyTiles >= FeatureTileThreshold)
				specialAreas.Add(SceneFeatureNames.SpecialArea.LivingMahoganyTree);
			if (layer == "Space" && counts.FloatingIslandTiles >= StructureTileThreshold)
				specialAreas.Add(SceneFeatureNames.SpecialArea.FloatingIsland);
			if (layer == "Underworld" && counts.RuinedHouseWalls >= WallThreshold)
				specialAreas.Add(SceneFeatureNames.SpecialArea.RuinedHouse);
			if (player.ZoneDesert && counts.PyramidTiles >= StructureTileThreshold)
				specialAreas.Add(SceneFeatureNames.SpecialArea.Pyramid);
		}

		private static LocalTileCounts Scan(int centerX, int centerY)
		{
			LocalTileCounts counts = new LocalTileCounts();
			int minX = centerX - ScanRadiusTiles;
			int maxX = centerX + ScanRadiusTiles;
			int minY = centerY - ScanRadiusTiles;
			int maxY = centerY + ScanRadiusTiles;

			for (int x = minX; x <= maxX; x++)
			{
				for (int y = minY; y <= maxY; y++)
				{
					if (!WorldGen.InWorld(x, y, 1)) continue;

					Tile tile = Main.tile[x, y];
					if (tile.LiquidAmount > 0 && tile.LiquidType == LiquidID.Water)
						counts.WaterTiles++;

					if (tile.HasTile) CountTile(tile.TileType, counts);
					CountWall(tile.WallType, counts);
				}
			}

			return counts;
		}

		private static void CountTile(ushort type, LocalTileCounts counts)
		{
			if (type == TileID.OasisPlants) counts.OasisPlants++;
			if (IsGlowingMoss(type)) counts.GlowingMossTiles++;
			if (type is TileID.AshGrass or TileID.TreeAsh or TileID.AshPlants or TileID.AshVines)
				counts.AshForestTiles++;
			if (type is TileID.LivingMahogany or TileID.LivingMahoganyLeaves)
				counts.LivingMahoganyTiles++;
			if (type is TileID.Cloud or TileID.RainCloud or TileID.SnowCloud or TileID.Sunplate)
				counts.FloatingIslandTiles++;
			if (type == TileID.SandstoneBrick) counts.PyramidTiles++;
		}

		private static void CountWall(ushort type, LocalTileCounts counts)
		{
			if (type == WallID.SpiderUnsafe) counts.SpiderWalls++;
			if (type == WallID.LivingWoodUnsafe) counts.LivingWoodWalls++;
			if (type is WallID.ObsidianBackUnsafe or WallID.ObsidianBrickUnsafe or WallID.HellstoneBrickUnsafe)
				counts.RuinedHouseWalls++;
			if (type == WallID.SandstoneBrick) counts.PyramidTiles++;
		}

		private static bool IsGlowingMoss(ushort type)
		{
			return type is TileID.ArgonMoss
				or TileID.KryptonMoss
				or TileID.XenonMoss
				or TileID.VioletMoss
				or TileID.RainbowMoss;
		}

		private sealed class LocalTileCounts
		{
			public int WaterTiles;
			public int OasisPlants;
			public int SpiderWalls;
			public int GlowingMossTiles;
			public int AshForestTiles;
			public int LivingWoodWalls;
			public int LivingMahoganyTiles;
			public int FloatingIslandTiles;
			public int RuinedHouseWalls;
			public int PyramidTiles;
		}
	}
}
