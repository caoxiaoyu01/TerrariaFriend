using System.Text.Json;
using Terraria;
using TerrariaFriend.GameState.Collectors;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState
{
	// 汇总各部分游戏状态并发送给智能体服务
	public static class GameStateCollector
	{
		// 75 格大致覆盖常见屏幕范围 并多留一点附近实体空间
		public const float DefaultSceneRadiusTiles = 75f;

		private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
		{
			PropertyNamingPolicy = JsonNamingPolicy.CamelCase
		};

		// 只能在玩家进入世界后由游戏主线程调用
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
