using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace TerrariaFriend.GameState.Snapshots
{
	// 当前世界共享的时间、天气与特殊事件状态
	public sealed record WorldSnapshot(
		TimeSnapshot Time,
		WeatherSnapshot Weather,
		IReadOnlyList<WorldEventSnapshot> ActiveEvents);

	public sealed record TimeSnapshot(
		bool IsDay,
		string TimeOfDay,
		string MoonPhase);

	public sealed record WeatherSnapshot(
		bool IsRaining,
		float RainIntensity,
		float WindSpeed,
		bool IsSandstorm);

	public sealed record WorldEventSnapshot(
		string Id,
		string Name,
		WorldEventCategory Category,
		float? Progress = null);

	[JsonConverter(typeof(JsonStringEnumConverter))]

	// 事件分成：天气事件、和平事件和入侵事件
	public enum WorldEventCategory
	{
		Combat,
		Invasion,
		Peaceful
	}
}
