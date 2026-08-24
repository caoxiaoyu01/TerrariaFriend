using Terraria;
using Terraria.Chat;
using Terraria.ID;
using Terraria.ModLoader;
using TerrariaFriend.Triggering;

namespace TerrariaFriend.Common.Systems
{
	// 从 Terraria 原生聊天提交中识别 Agent Query
	[Autoload(Side = ModSide.Client)]
	public sealed class UserQueryChatSystem : ModSystem
	{
		public override void Load()
		{
			// 在原生聊天开关处理完成后设置默认路由标记
			On_Main.DoUpdate_Enter_ToggleChat += DoUpdateEnterToggleChat;

			// 多人游戏在客户端发送消息前经过此入口
			On_ChatHelper.SendChatMessageFromClient += SendChatMessageFromClient;

			// 单人游戏直接在本地处理聊天消息
			On_ChatCommandProcessor.ProcessIncomingMessage += ProcessIncomingMessage;
		}

		public override void Unload()
		{
			On_Main.DoUpdate_Enter_ToggleChat -= DoUpdateEnterToggleChat;
			On_ChatHelper.SendChatMessageFromClient -= SendChatMessageFromClient;
			On_ChatCommandProcessor.ProcessIncomingMessage -= ProcessIncomingMessage;
		}

		private static void DoUpdateEnterToggleChat(On_Main.orig_DoUpdate_Enter_ToggleChat orig)
		{
			bool wasChatOpen = Main.drawingPlayerChat;
			orig();

			// 只在聊天框刚打开且内容为空时补上路由标记
			if (!wasChatOpen && Main.drawingPlayerChat && string.IsNullOrEmpty(Main.chatText))
			{
				Main.chatText = "@";
			}
		}

		private static void SendChatMessageFromClient(
			On_ChatHelper.orig_SendChatMessageFromClient orig,
			ChatMessage message)
		{
			if (!TrySubmitUserQuery(message.Text))
			{
				orig(message);
			}
		}

		private static void ProcessIncomingMessage(
			On_ChatCommandProcessor.orig_ProcessIncomingMessage orig,
			ChatCommandProcessor self,
			ChatMessage message,
			int clientId)
		{
			// 这里只拦截单人游戏的本地提交
			if (Main.netMode != NetmodeID.SinglePlayer || !TrySubmitUserQuery(message.Text))
			{
				orig(self, message, clientId);
			}
		}

		private static bool TrySubmitUserQuery(string text)
		{
			if (string.IsNullOrEmpty(text) || text[0] != '@')
			{
				return false;
			}

			// 去掉路由标记并忽略空 Query
			string query = text[1..].Trim();
			if (query.Length > 0)
			{
				TriggerSystem.SubmitUserQuery(query);
			}

			// 所有以 @ 开头的消息都不再发送到原生聊天
			return true;
		}
	}
}
