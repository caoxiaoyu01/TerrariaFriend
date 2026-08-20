using System.Collections.Generic;
using Terraria;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class SceneCollector
	{
		// 将 Player.ZoneXXX 和 SceneMetrics 转换成场景信息
		public static SceneSnapshot Capture(Player player)
		{
			List<string> biomes = GetBiomes(player);
			List<string> specialScenes = new List<string>();
			List<string> nearbyBuffs = new List<string>();
			SceneMetrics metrics = Main.SceneMetrics;

			if (player.ZoneGraveyard) specialScenes.Add("Graveyard");
			if (metrics.HasCampfire) nearbyBuffs.Add("Campfire");
			if (metrics.HasHeartLantern) nearbyBuffs.Add("Heart Lantern");

			return new SceneSnapshot(
				biomes,
				GetLayer(player),
				specialScenes,
				nearbyBuffs);
		}

		// 一个位置可以同时属于多个生物群落
		private static List<string> GetBiomes(Player player)
		{
			List<string> biomes = new List<string>();
			if (player.ZoneForest) biomes.Add("Forest");
			if (player.ZoneDesert) biomes.Add("Desert");
			if (player.ZoneBeach) biomes.Add("Ocean");
			if (player.ZoneJungle) biomes.Add("Jungle");
			if (player.ZoneSnow) biomes.Add("Snow");
			if (player.ZoneDungeon) biomes.Add("Dungeon");
			if (player.ZoneLihzhardTemple) biomes.Add("Temple");
			if (player.ZoneShimmer) biomes.Add("Shimmer");
			if (player.ZoneCorrupt) biomes.Add("Corruption");
			if (player.ZoneCrimson) biomes.Add("Crimson");
			if (player.ZoneHallow) biomes.Add("Hallow");
			if (player.ZoneGlowshroom) biomes.Add("Glowing Mushroom");
			if (player.ZoneMeteor) biomes.Add("Meteor");
			return biomes;
		}

		// 玩家当前所处的垂直层级
		private static string GetLayer(Player player)
		{
			if (player.ZoneSkyHeight) return "Sky";
			if (player.ZoneOverworldHeight) return "Surface";
			if (player.ZoneDirtLayerHeight) return "Underground";
			if (player.ZoneRockLayerHeight) return "Cavern";
			return "Underworld";
		}
	}
}
