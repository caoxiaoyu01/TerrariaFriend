using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;
using Terraria.UI;
using TerrariaFriend.Common.UI;

namespace TerrariaFriend.Common.Systems
{
	// 管理客户端 Companion UI 的创建 更新和绘制
	[Autoload(Side = ModSide.Client)]
	public class AgentMessageUISystem : ModSystem
	{
		private UserInterface _userInterface;
		private AgentMessageUIState _messageUI;

		public override void Load()
		{
			_messageUI = new AgentMessageUIState();
			_messageUI.Activate();

			_userInterface = new UserInterface();
			_userInterface.SetState(_messageUI);
		}

		public override void Unload()
		{
			_userInterface = null;
			_messageUI = null;
		}

		public override void UpdateUI(GameTime gameTime)
		{
			if (_userInterface?.CurrentState != null)
			{
				_userInterface.Update(gameTime);
			}
		}

		public override void ModifyInterfaceLayers(List<GameInterfaceLayer> layers)
		{
			int mouseTextIndex = layers.FindIndex(layer => layer.Name == "Vanilla: Mouse Text");
			if (mouseTextIndex == -1)
			{
				return;
			}

			layers.Insert(mouseTextIndex, new LegacyGameInterfaceLayer(
				"TerrariaFriend: Agent Message",
				() =>
				{
					if (!Main.gameMenu && _userInterface?.CurrentState != null)
					{
						_userInterface.Draw(Main.spriteBatch, new GameTime());
					}

					return true;
				},
				InterfaceScaleType.UI));
		}

		// Agent 完整消息进入现有显示区域的统一入口
		// 只应在游戏客户端主线程调用
		public static void ShowMessage(string message)
		{
			if (Main.dedServ)
			{
				return;
			}

			AgentMessageUISystem system = ModContent.GetInstance<AgentMessageUISystem>();
			system._messageUI?.SetMessage(message);
			if (system._userInterface?.CurrentState == null)
			{
				system._userInterface.SetState(system._messageUI);
			}
		}

		public static void Hide()
		{
			if (!Main.dedServ)
			{
				ModContent.GetInstance<AgentMessageUISystem>()._userInterface?.SetState(null);
			}
		}
	}
}
