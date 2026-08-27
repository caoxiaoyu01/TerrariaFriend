using System.Collections.Generic;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 仅稳定且具有探索意义的场景参与世界级首次发现事件
	internal static class DiscoverableSceneFeatures
	{
		private static readonly HashSet<string> Keys = new HashSet<string>
		{
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.Oasis),
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.GraniteCave),
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.MarbleCave),
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.SpiderNest),
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.BeeHive),
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.GlowingMoss),
			CreateKey("MINI_BIOME", SceneFeatureNames.MiniBiome.AshForest),

			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.Dungeon),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.JungleTemple),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.Aether),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.LivingTree),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.LivingMahoganyTree),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.FloatingIsland),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.RuinedHouse),
			CreateKey("SPECIAL_AREA", SceneFeatureNames.SpecialArea.Pyramid)
		};

		public static bool Contains(string category, string feature)
		{
			return Keys.Contains(CreateKey(category, feature));
		}

		public static bool ContainsKey(string featureKey)
		{
			return Keys.Contains(featureKey);
		}

		public static string CreateKey(string category, string feature)
		{
			return $"{category}:{feature}";
		}
	}
}
