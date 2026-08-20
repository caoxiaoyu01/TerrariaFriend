using System.Text.Json.Serialization;

namespace TerrariaFriend.Triggering
{
	[JsonConverter(typeof(JsonStringEnumConverter))]
	public enum TriggerType
	{
		USER_QUERY,
		GAME_EVENT,
		PERIODIC
	}
}
