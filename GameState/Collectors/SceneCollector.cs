using System.Collections.Generic;
using Terraria;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class SceneCollector
	{
		// 把游戏内部的区域标记转换成场景信息
		public static SceneSnapshot Capture(Player player)
		{
			List<string> biomes = GetBiomes(player);
			List<string> miniBiomes = new List<string>();
			List<string> specialAreas = new List<string>();
			List<string> nearbyBuffs = new List<string>();
			SceneMetrics metrics = Main.SceneMetrics;
			string layer = GetLayer(player);

			if (player.ZoneGranite) miniBiomes.Add(SceneFeatureNames.MiniBiome.GraniteCave);
			if (player.ZoneMarble) miniBiomes.Add(SceneFeatureNames.MiniBiome.MarbleCave);
			if (player.ZoneHive) miniBiomes.Add(SceneFeatureNames.MiniBiome.BeeHive);
			if (player.ZoneMeteor) miniBiomes.Add(SceneFeatureNames.MiniBiome.Meteorite);
			if (player.townNPCs > 2f) miniBiomes.Add(SceneFeatureNames.MiniBiome.Town);
			if (player.ZoneGraveyard) miniBiomes.Add(SceneFeatureNames.MiniBiome.Graveyard);

			if (player.ZoneDungeon) specialAreas.Add(SceneFeatureNames.SpecialArea.Dungeon);
			if (player.ZoneLihzhardTemple) specialAreas.Add(SceneFeatureNames.SpecialArea.JungleTemple);
			if (player.ZoneShimmer) specialAreas.Add(SceneFeatureNames.SpecialArea.Aether);

			SceneLocalFeatureDetector.Capture(player, layer, miniBiomes, specialAreas);
			if (metrics.HasCampfire) nearbyBuffs.Add("Campfire");
			if (metrics.HasHeartLantern) nearbyBuffs.Add("Heart Lantern");

			return new SceneSnapshot(
				biomes,
				layer,
				miniBiomes,
				specialAreas,
				nearbyBuffs);
		}

		// 一个位置可以同时属于多个生物群落
		private static List<string> GetBiomes(Player player)
		{
			List<string> biomes = new List<string>();
			if (player.ZoneForest) biomes.Add("Forest");
			if (player.ZoneDesert || player.ZoneUndergroundDesert) biomes.Add("Desert");
			if (player.ZoneBeach) biomes.Add("Ocean");
			if (player.ZoneJungle) biomes.Add("Jungle");
			if (player.ZoneSnow) biomes.Add("Snow");
			if (player.ZoneCorrupt) biomes.Add("Corruption");
			if (player.ZoneCrimson) biomes.Add("Crimson");
			if (player.ZoneHallow) biomes.Add("Hallow");
			if (player.ZoneGlowshroom) biomes.Add("Glowing Mushroom");
			return biomes;
		}

		// 玩家当前所处的垂直层级
		private static string GetLayer(Player player)
		{
			if (player.ZoneSkyHeight) return "Space";
			if (player.ZoneOverworldHeight) return "Surface";
			if (player.ZoneDirtLayerHeight) return "Underground";
			if (player.ZoneRockLayerHeight) return "Cavern";
			return "Underworld";
		}
	}
}
