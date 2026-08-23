#nullable enable

namespace TerrariaFriend.AgentCommunication
{
	public sealed record AgentResponse(
		string Action,
		string? Message,
		string? DecisionReason,
		bool Success,
		string? Error);
}
