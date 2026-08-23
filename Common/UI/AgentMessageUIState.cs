using Microsoft.Xna.Framework;
using Terraria.GameContent.UI.Elements;
using Terraria.UI;

namespace TerrariaFriend.Common.UI
{
	// Companion 消息框只负责显示 Agent 回复
	public class AgentMessageUIState : UIState
	{
		private const float HorizontalMargin = 20f;
		private const float BottomMargin = 20f;
		private const float PanelMinWidth = 240f;
		private const float PanelMaxWidth = 300f;
		private const float PanelHeight = 90f;

		private UIText _messageText;

		public override void OnInitialize()
		{
			UIPanel panel = new UIPanel();

			// 左下角对齐
			// 百分比宽度配合最小最大宽度适配不同分辨率
			panel.HAlign = 0f;
			panel.VAlign = 1f;
			panel.Left.Set(HorizontalMargin, 0f);
			panel.Top.Set(-BottomMargin, 0f);
			panel.Width.Set(-(HorizontalMargin * 2f), 0.25f);
			panel.MinWidth.Set(PanelMinWidth, 0f);
			panel.MaxWidth.Set(PanelMaxWidth, 0f);
			panel.Height.Set(PanelHeight, 0f);
			panel.SetPadding(10f);
			panel.BackgroundColor = new Color(18, 28, 48, 225);
			panel.BorderColor = new Color(74, 144, 196, 255);
			panel.IgnoresMouseInteraction = true;
			Append(panel);

			UIText titleText = new UIText("Terraria Friend", 0.78f);
			titleText.TextColor = new Color(116, 210, 255);
			panel.Append(titleText);

			_messageText = new UIText("UI 已连接。这里将显示 Agent 消息。", 0.72f);
			_messageText.Top.Set(24f, 0f);
			_messageText.Width.Set(0f, 1f);
			_messageText.Height.Set(-24f, 1f);
			_messageText.IsWrapped = true;
			_messageText.TextColor = Color.White;
			panel.Append(_messageText);
		}

		public void SetMessage(string message)
		{
			_messageText?.SetText(string.IsNullOrWhiteSpace(message) ? "（暂无消息）" : message);
		}
	}
}
