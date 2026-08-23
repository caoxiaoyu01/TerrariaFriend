namespace TerrariaFriend.Triggering
{
	// 所有 Trigger 共用的轻量生命状态
	public sealed record VitalsContext(
		float HpRatio,
		float HpDelta,
		bool InCombat);
}
