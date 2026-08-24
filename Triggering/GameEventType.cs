using System.Text.Json.Serialization;

namespace TerrariaFriend.Triggering
{
	[JsonConverter(typeof(JsonStringEnumConverter))]
	public enum GameEventType
	{
		PlayerDied,
		BossSpawned,
		BossEnded,
		NewAreaDiscovered,
		SceneFeatureEntered,
		WorldEventStarted,
		WorldEventEnded,
		SpecialNpcAppeared,
		ProgressMilestoneChanged
	}
}
