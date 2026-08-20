#nullable enable

namespace TerrariaFriend.AgentCommunication
{
	public sealed record AgentResponse(
		string Action,
		string? Message,
		bool Success,
		string? Error);
}
