using System.Text.Json.Serialization;

namespace TerrariaFriend.Triggering
{
	[JsonConverter(typeof(JsonStringEnumConverter))]
	public enum GameEventType
	{
		PlayerDied,
		BossSpawned,
		BossEnded,
		BossDefeated,
		NewAreaDiscovered,
		SceneFeatureEntered,
		SceneFeatureExited,
		WorldEventStarted,
		WorldEventEnded,
		SpecialNpcAppeared,
		ProgressMilestoneChanged,
		EquipmentChanged,
		WorldSessionEnded
	}
}
