namespace TerrariaFriend.Triggering
{
	// 所有触发共用的简要生命状态
	public sealed record VitalsContext(
		float HpRatio,
		float HpDelta,
		bool InCombat);
}
