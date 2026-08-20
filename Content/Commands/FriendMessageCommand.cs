using System;
using Terraria.ModLoader;
using TerrariaFriend.Common.Systems;

namespace TerrariaFriend.Content.Commands
{
	/// <summary>
	/// Temporary development command for checking the message UI in game.
	/// Example: /friend 接下来建议先建造一个工作台。
	/// </summary>
	public class FriendMessageCommand : ModCommand
	{
		public override CommandType Type => CommandType.Chat;

		public override string Command => "friend";

		public override string Usage => "/friend <message>";

		public override string Description => "在 Terraria Friend 面板中显示一条测试消息";

		public override bool IsCaseSensitive => true;

		public override void Action(CommandCaller caller, string input, string[] args)
		{
			string message = args.Length == 0
				? "这是 Terraria Friend 的测试消息。"
				: string.Join(' ', args);

			AgentMessageUISystem.ShowMessage(message);
		}
	}
}
