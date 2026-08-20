using System.Text.Json;
using Terraria;
using TerrariaFriend.GameState.Collectors;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState
{
	// 统一组装所有子快照，提供给 Python Agent JSON
	public static class GameStateCollector
	{
		// 75 格约覆盖常见 1080p 可见区域，并为附近实体留少量余量
		public const float DefaultSceneRadiusTiles = 75f;

		private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
		{
			PropertyNamingPolicy = JsonNamingPolicy.CamelCase
		};

		// 必须在游戏主线程、玩家进入世界后调用
		public static GameSnapshot Capture(float sceneRadiusTiles = DefaultSceneRadiusTiles)
		{
			Player player = Main.LocalPlayer;
			NpcSnapshot npc = NpcCollector.Capture(player, sceneRadiusTiles);

			return new GameSnapshot(
				Main.GameUpdateCount,
				PlayerCollector.Capture(player),
				InventoryCollector.Capture(player),
				WorldCollector.Capture(),
				ProgressCollector.Capture(),
				SceneCollector.Capture(player),
				CombatCollector.Capture(player),
				npc);
		}

		public static string CaptureJson(float sceneRadiusTiles = DefaultSceneRadiusTiles)
		{
			return JsonSerializer.Serialize(Capture(sceneRadiusTiles), JsonOptions);
		}
	}
}
