using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;
using Terraria.UI;
using TerrariaFriend.Common.UI;

namespace TerrariaFriend.Common.Systems
{
	/// <summary>
	/// Owns, updates, and draws the Agent message UI on game clients.
	/// </summary>
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

		/// <summary>
		/// Main entry point for future Agent output.
		/// Call this on the game client after a complete message is ready.
		/// </summary>
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
