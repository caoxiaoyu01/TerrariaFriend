namespace TerrariaFriend.Triggering
{
	public static class BoundaryEventConfig
	{
		// 快照每 10 游戏刻采样 30 游戏刻代表持续约 0.5 秒离开状态
		public const uint SceneFeatureExitDebounceTicks = 30;
	}
}
