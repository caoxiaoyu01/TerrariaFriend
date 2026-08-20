using System.Text.Json.Serialization;

namespace TerrariaFriend.Triggering
{
	[JsonConverter(typeof(JsonStringEnumConverter))]
	public enum TriggerPriority
	{
		LOW,
		NORMAL,
		HIGH
	}
}
